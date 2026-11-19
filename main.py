import asyncio
import csv
import io
import json
import logging
import os
import time
import uuid
from typing import Optional

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from database import init_db, close_db, create_quiz, get_quiz, save_score, get_leaderboard, update_score, IS_POSTGRES
from models import Quiz, Question

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("quizarre")

REDIS_URL = os.getenv("REDIS_URL", "").strip()


class FakeRedis:
    def __init__(self):
        self.data = {}

    async def close(self):
        pass

    async def aclose(self):
        pass

    async def delete(self, key: str):
        if key in self.data:
            del self.data[key]

    async def zadd(self, key: str, mapping: dict = None, **kwargs):
        if mapping is None:
            mapping = kwargs
        if key not in self.data:
            self.data[key] = []
        for member, score in mapping.items():
            self.data[key] = [(s, m) for s, m in self.data[key] if m != member]
            self.data[key].append((score, member))
            self.data[key].sort(key=lambda x: x[0])

    async def zrange(self, key: str, start: int, end: int, withscores: bool = False):
        if key not in self.data:
            return []
        res = self.data[key]
        res_slice = res[start:] if end == -1 else res[start:end+1]
        if withscores:
            return [(m, s) for s, m in res_slice]
        return [m for s, m in res_slice]


app = FastAPI(title="QUIZARRE Real-Time Platform")

# Enable compression for faster file delivery
app.add_middleware(GZipMiddleware, minimum_size=1000)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis connection
redis = None

# In-memory state
active_quizzes: dict = {}  # quiz_id -> quiz state
connections: dict = {}      # quiz_id -> {player_id: websocket}


@app.on_event("startup")
async def startup():
    global redis
    if REDIS_URL:
        try:
            import redis.asyncio as aioredis
            redis = aioredis.from_url(REDIS_URL, decode_responses=True)
            await redis.ping()
            logger.info("Connected to genuine Redis successfully.")
        except Exception as e:
            logger.warning("Failed to connect to Redis (%s). Falling back to FakeRedis.", e)
            redis = FakeRedis()
    else:
        logger.info("REDIS_URL not set. Running with in-memory FakeRedis.")
        redis = FakeRedis()

    await init_db()


@app.on_event("shutdown")
async def shutdown():
    global redis
    if redis:
        if hasattr(redis, "aclose"):
            await redis.aclose()
        elif hasattr(redis, "close"):
            await redis.close()
    await close_db()


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "redis": "connected" if redis and not isinstance(redis, FakeRedis) else "fake_redis",
        "database": "postgres" if IS_POSTGRES else "sqlite",
    }


# ─────────────────────────────────────────────
# CSV Upload & Validation
# ─────────────────────────────────────────────

@app.post("/api/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files are accepted")

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "File encoding must be UTF-8")

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    # Strip header if present
    if rows and rows[0][0].strip().lower() == "question":
        rows = rows[1:]

    if not rows:
        raise HTTPException(400, "CSV has no question rows")

    questions = []
    errors = []
    for i, row in enumerate(rows, 1):
        # Clean whitespace
        row = [c.strip() for c in row]

        if len(row) != 6:
            errors.append(f"Row {i}: expected 6 columns, got {len(row)}")
            continue

        question, o1, o2, o3, o4, correct = row

        if not all([question, o1, o2, o3, o4, correct]):
            errors.append(f"Row {i}: contains empty values")
            continue

        options = [o1, o2, o3, o4]
        if correct not in options:
            errors.append(f"Row {i}: correct answer '{correct}' does not match any option")
            continue

        questions.append({
            "question": question,
            "options": options,
            "correct": correct,
        })

    if errors:
        raise HTTPException(400, {"errors": errors})

    if not questions:
        raise HTTPException(400, "No valid questions found in CSV")

    return {"questions": questions, "count": len(questions)}


# ─────────────────────────────────────────────
# Quiz Management
# ─────────────────────────────────────────────

@app.post("/api/quiz/create")
async def create_quiz_endpoint(payload: dict):
    questions = payload.get("questions", [])
    host_name = payload.get("host_name", "Host")
    quiz_title = payload.get("title", "QUIZARRE")
    mode = payload.get("mode", "buzzer")

    if not questions:
        raise HTTPException(400, "No questions provided")

    quiz_id = str(uuid.uuid4())[:8].upper()

    quiz_state = {
        "id": quiz_id,
        "title": quiz_title,
        "host": host_name,
        "mode": mode,
        "questions": questions,
        "current_index": -1,
        "status": "lobby",   # lobby | question | reviewing | finished
        "current_question": None,
        "buzzer_queue": [],
        "answering_player": None,
        "scores": {},
        "players": {},
        "attempted": [],     # players who already tried this question
    }

    active_quizzes[quiz_id] = quiz_state
    connections[quiz_id] = {}

    await create_quiz(quiz_id, quiz_title, host_name, questions)

    return {"quiz_id": quiz_id}


@app.get("/api/quiz/{quiz_id}")
async def get_quiz_info(quiz_id: str):
    quiz = active_quizzes.get(quiz_id)
    if not quiz:
        raise HTTPException(404, "Quiz not found")
    return {
        "id": quiz["id"],
        "title": quiz["title"],
        "host": quiz["host"],
        "status": quiz["status"],
        "player_count": len(quiz["players"]),
        "question_count": len(quiz["questions"]),
    }


# ─────────────────────────────────────────────
# WebSocket
# ─────────────────────────────────────────────

async def broadcast(quiz_id: str, message: dict, exclude: str = None):
    if quiz_id not in connections:
        return
    
    tasks = []
    player_ids = []
    
    for pid, ws in list(connections[quiz_id].items()):
        if pid == exclude:
            continue
        player_ids.append(pid)
        tasks.append(ws.send_json(message))
        
    if not tasks:
        return

    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    dead = []
    for pid, res in zip(player_ids, results):
        if isinstance(res, Exception):
            dead.append(pid)
            
    for pid in dead:
        await handle_disconnect(quiz_id, pid)


async def send_state(quiz_id: str, player_id: str = None):
    quiz = active_quizzes.get(quiz_id)
    if not quiz:
        return

    state_msg = {
        "type": "state",
        "quiz_id": quiz_id,
        "title": quiz["title"],
        "status": quiz["status"],
        "mode": quiz.get("mode", "buzzer"),
        "current_index": quiz["current_index"],
        "total_questions": len(quiz["questions"]),
        "players": quiz["players"],
        "scores": quiz["scores"],
        "buzzer_queue": quiz["buzzer_queue"],
        "answering_player": quiz["answering_player"],
        "question_start_time": quiz.get("question_start_time", 0),
        "attempted": quiz.get("attempted", []),
    }

    if quiz["status"] in ("question", "reviewing") and quiz["current_question"]:
        q = quiz["current_question"]
        state_msg["question"] = {
            "text": q["question"],
            "options": q["options"],
        }
        if quiz["status"] == "reviewing":
            state_msg["question"]["correct"] = q["correct"]

    if player_id:
        ws = connections[quiz_id].get(player_id)
        if ws:
            await ws.send_json(state_msg)
    else:
        await broadcast(quiz_id, state_msg)


async def handle_disconnect(quiz_id: str, player_id: str):
    quiz = active_quizzes.get(quiz_id)
    if not quiz:
        return

    if player_id in connections.get(quiz_id, {}):
        del connections[quiz_id][player_id]

    if player_id in quiz["players"]:
        name = quiz["players"][player_id]["name"]
        del quiz["players"][player_id]
        await broadcast(quiz_id, {"type": "player_left", "player_id": player_id, "name": name})

    # If the disconnecting player was in buzzer queue, remove and potentially advance
    if player_id in quiz["buzzer_queue"]:
        quiz["buzzer_queue"].remove(player_id)
        await broadcast(quiz_id, {"type": "buzzer_queue", "queue": quiz["buzzer_queue"],
                                   "names": {pid: quiz["players"].get(pid, {}).get("name", pid)
                                             for pid in quiz["buzzer_queue"]}})

    if quiz["answering_player"] == player_id:
        quiz["answering_player"] = None
        await advance_buzzer(quiz_id)


async def advance_buzzer(quiz_id: str):
    quiz = active_quizzes.get(quiz_id)
    if not quiz:
        return

    # Remove disconnected players from queue
    quiz["buzzer_queue"] = [p for p in quiz["buzzer_queue"] if p in quiz["players"]]

    if quiz["buzzer_queue"]:
        next_player = quiz["buzzer_queue"][0]
        quiz["answering_player"] = next_player
        await broadcast(quiz_id, {
            "type": "your_turn",
            "player_id": next_player,
            "name": quiz["players"].get(next_player, {}).get("name", next_player),
        })
        await send_state(quiz_id)
    else:
        # Nobody left to answer - reveal answer
        quiz["answering_player"] = None
        await reveal_answer(quiz_id)


async def reveal_answer(quiz_id: str):
    quiz = active_quizzes.get(quiz_id)
    if not quiz or not quiz["current_question"]:
        return

    quiz["status"] = "reviewing"
    await broadcast(quiz_id, {
        "type": "reveal_answer",
        "correct": quiz["current_question"]["correct"],
        "reason": "no_correct",
    })
    await send_state(quiz_id)


@app.websocket("/ws/{quiz_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, quiz_id: str, player_id: str):
    quiz = active_quizzes.get(quiz_id)
    if not quiz:
        await websocket.close(code=4004)
        return

    await websocket.accept()

    if quiz_id not in connections:
        connections[quiz_id] = {}
    connections[quiz_id][player_id] = websocket

    try:
        # Send current state immediately
        await send_state(quiz_id, player_id)

        async for data in websocket.iter_json():
            try:
                await handle_message(quiz_id, player_id, data)
            except Exception as e:
                print(f"Error handling message: {e}")
                import traceback
                traceback.print_exc()

    except WebSocketDisconnect:
        pass
    finally:
        await handle_disconnect(quiz_id, player_id)


async def handle_message(quiz_id: str, player_id: str, data: dict):
    quiz = active_quizzes.get(quiz_id)
    if not quiz:
        return

    msg_type = data.get("type")

    # ── Join ──
    if msg_type == "join":
        name = data.get("name", "Anonymous")[:20]
        role = data.get("role", "player")
        quiz["players"][player_id] = {"name": name, "role": role}
        if player_id not in quiz["scores"]:
            quiz["scores"][player_id] = 0

        await broadcast(quiz_id, {
            "type": "player_joined",
            "player_id": player_id,
            "name": name,
            "role": role,
        })
        await send_state(quiz_id)

    # ── Host: start quiz ──
    elif msg_type == "start_quiz":
        if quiz["players"].get(player_id, {}).get("role") != "host":
            return
        
        # If already started, ignore.
        if quiz["status"] != "lobby":
            return

        quiz["status"] = "question"
        quiz["current_index"] = 0
        quiz["current_question"] = quiz["questions"][0] if quiz["questions"] else None
        quiz["buzzer_queue"] = []
        quiz["answering_player"] = None
        quiz["attempted"] = []

        await redis.delete(f"quiz:{quiz_id}:buzzer")

        if quiz["current_question"]:
            await broadcast(quiz_id, {
                "type": "new_question",
                "index": 0,
                "total": len(quiz["questions"]),
                "start_time": quiz["question_start_time"],
                "question": {
                    "text": quiz["current_question"]["question"],
                    "options": quiz["current_question"]["options"],
                },
            })
        await send_state(quiz_id)

    # ── Host: next question ──
    elif msg_type == "next_question":
        if quiz["players"].get(player_id, {}).get("role") != "host":
            return

        next_idx = quiz["current_index"] + 1
        if next_idx >= len(quiz["questions"]):
            quiz["status"] = "finished"
            await broadcast(quiz_id, {"type": "quiz_finished", "scores": quiz["scores"]})
            await send_state(quiz_id)
            return

        quiz["current_index"] = next_idx
        quiz["current_question"] = quiz["questions"][next_idx]
        quiz["status"] = "question"
        quiz["question_start_time"] = time.time()
        quiz["buzzer_queue"] = []
        quiz["answering_player"] = None
        quiz["attempted"] = []

        # Clear Redis buzzer key
        await redis.delete(f"quiz:{quiz_id}:buzzer")

        await broadcast(quiz_id, {
            "type": "new_question",
            "index": next_idx,
            "total": len(quiz["questions"]),
            "start_time": quiz["question_start_time"],
            "question": {
                "text": quiz["current_question"]["question"],
                "options": quiz["current_question"]["options"],
            },
        })
        await send_state(quiz_id)

    # ── Player: buzz ──
    elif msg_type == "buzz":
        if quiz.get("mode") == "classic":
            return
        if quiz["status"] != "question":
            return
        if player_id in quiz["attempted"]:
            return
        if player_id in quiz["buzzer_queue"]:
            return
        if player_id == quiz.get("answering_player"):
            return

        # Store in Redis sorted set with timestamp as score
        ts = time.time()
        await redis.zadd(f"quiz:{quiz_id}:buzzer", {player_id: ts})
        
        # Broadcast single buzz event for Host Activity Feed
        await broadcast(quiz_id, {
            "type": "buzz_event",
            "name": quiz["players"].get(player_id, {}).get("name", player_id)
        })

        # Rebuild queue from Redis (timestamp order)
        raw = await redis.zrange(f"quiz:{quiz_id}:buzzer", 0, -1, withscores=False)
        # Filter only players still connected
        quiz["buzzer_queue"] = [p for p in raw if p in quiz["players"] and p not in quiz["attempted"]]

        queue_names = {pid: quiz["players"].get(pid, {}).get("name", pid)
                       for pid in quiz["buzzer_queue"]}

        await broadcast(quiz_id, {
            "type": "buzzer_update",
            "queue": quiz["buzzer_queue"],
            "names": queue_names,
        })

        # If nobody is currently answering, give turn to first in queue
        if not quiz["answering_player"] and quiz["buzzer_queue"]:
            first = quiz["buzzer_queue"][0]
            quiz["answering_player"] = first
            await broadcast(quiz_id, {
                "type": "your_turn",
                "player_id": first,
                "name": quiz["players"].get(first, {}).get("name", first),
            })
            await send_state(quiz_id)

    # ── Player: submit answer ──
    elif msg_type == "answer":
        if quiz.get("mode") == "classic":
            if quiz["status"] != "question":
                return
            if player_id in quiz["attempted"]:
                return

            chosen = data.get("answer")
            correct_answer = quiz["current_question"]["correct"]
            is_correct = chosen == correct_answer

            quiz["attempted"].append(player_id)

            if is_correct:
                elapsed = time.time() - quiz.get("question_start_time", time.time())
                score_to_add = max(500, int((1 - (elapsed / 30) / 2) * 1000))
                quiz["scores"][player_id] = quiz["scores"].get(player_id, 0) + score_to_add

            await broadcast(quiz_id, {
                "type": "classic_answer_received",
                "player_id": player_id,
                "name": quiz["players"].get(player_id, {}).get("name", player_id),
            })
            await send_state(quiz_id)

            # Send feedback back to the player immediately
            ws = connections.get(quiz_id, {}).get(player_id)
            if ws:
                await ws.send_json({
                    "type": "answer_feedback",
                    "correct": None,
                    "is_correct": is_correct
                })

            # Auto-reveal if all active players have answered
            active_players = [p for p, pd in quiz["players"].items() if pd.get("role") == "player"]
            if len(quiz["attempted"]) >= len(active_players) and len(active_players) > 0:
                await reveal_answer(quiz_id)

            return

        if quiz["answering_player"] != player_id:
            return
        if quiz["status"] != "question":
            return

        chosen = data.get("answer")
        correct_answer = quiz["current_question"]["correct"]
        is_correct = chosen == correct_answer

        quiz["attempted"].append(player_id)
        quiz["buzzer_queue"] = [p for p in quiz["buzzer_queue"] if p != player_id]
        quiz["answering_player"] = None

        if is_correct:
            quiz["scores"][player_id] = quiz["scores"].get(player_id, 0) + 1
            quiz["status"] = "reviewing"
            name = quiz["players"].get(player_id, {}).get("name", player_id)
            await broadcast(quiz_id, {
                "type": "correct_answer",
                "player_id": player_id,
                "name": name,
                "answer": chosen,
                "correct": correct_answer,
                "scores": quiz["scores"],
            })
            await send_state(quiz_id)
        else:
            name = quiz["players"].get(player_id, {}).get("name", player_id)
            await broadcast(quiz_id, {
                "type": "wrong_answer",
                "player_id": player_id,
                "name": name,
                "guess": chosen
            })
            # Advance to next in queue without revealing answer
            await advance_buzzer(quiz_id)

    # ── Player: malpractice ──
    elif msg_type == "malpractice":
        if player_id in quiz["players"]:
            quiz["players"][player_id]["malpractice"] = quiz["players"][player_id].get("malpractice", 0) + 1
            await send_state(quiz_id)
    # ── Host: skip question ──
    elif msg_type == "skip_question":
        if quiz["players"].get(player_id, {}).get("role") != "host":
            return
        await reveal_answer(quiz_id)

if os.path.exists("index.html"):
    app.mount("/", StaticFiles(directory=".", html=True), name="static")
