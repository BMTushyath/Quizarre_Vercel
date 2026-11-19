import json
import logging
import os

logger = logging.getLogger("quizarre.database")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IS_POSTGRES = DATABASE_URL.startswith("postgresql://")
DB_PATH = os.getenv("SQLITE_DB_PATH", "quiz.db")

pg_pool = None


async def init_db():
    global pg_pool
    if IS_POSTGRES:
        try:
            import asyncpg
            logger.info("Initializing PostgreSQL connection pool...")
            pg_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
            async with pg_pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS quizzes (
                        id TEXT PRIMARY KEY,
                        title TEXT,
                        host TEXT,
                        questions TEXT,
                        created_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW())
                    );
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS scores (
                        quiz_id TEXT,
                        player_id TEXT,
                        player_name TEXT,
                        score INTEGER DEFAULT 0,
                        PRIMARY KEY (quiz_id, player_id)
                    );
                """)
            logger.info("PostgreSQL database initialized successfully.")
            return
        except Exception as e:
            logger.error("Failed to initialize PostgreSQL: %s. Falling back to SQLite.", e)

    import aiosqlite
    logger.info("Using SQLite database at %s", DB_PATH)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS quizzes (
                id TEXT PRIMARY KEY,
                title TEXT,
                host TEXT,
                questions TEXT,
                created_at REAL DEFAULT (unixepoch())
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                quiz_id TEXT,
                player_id TEXT,
                player_name TEXT,
                score INTEGER DEFAULT 0,
                PRIMARY KEY (quiz_id, player_id)
            )
        """)
        await db.commit()
    logger.info("SQLite database initialized successfully.")


async def close_db():
    global pg_pool
    if pg_pool:
        await pg_pool.close()
        logger.info("PostgreSQL connection pool closed.")


async def create_quiz(quiz_id: str, title: str, host: str, questions: list):
    if IS_POSTGRES and pg_pool:
        async with pg_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO quizzes (id, title, host, questions) VALUES ($1, $2, $3, $4)",
                quiz_id, title, host, json.dumps(questions)
            )
        return

    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO quizzes (id, title, host, questions) VALUES (?, ?, ?, ?)",
            (quiz_id, title, host, json.dumps(questions))
        )
        await db.commit()


async def get_quiz(quiz_id: str):
    if IS_POSTGRES and pg_pool:
        async with pg_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, title, host, questions FROM quizzes WHERE id = $1",
                quiz_id
            )
            if row:
                return {
                    "id": row["id"],
                    "title": row["title"],
                    "host": row["host"],
                    "questions": json.loads(row["questions"])
                }
        return None

    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, title, host, questions FROM quizzes WHERE id = ?", (quiz_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return {"id": row[0], "title": row[1], "host": row[2],
                        "questions": json.loads(row[3])}
    return None


async def save_score(quiz_id: str, player_id: str, player_name: str, score: int):
    if IS_POSTGRES and pg_pool:
        async with pg_pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO scores (quiz_id, player_id, player_name, score)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (quiz_id, player_id)
                   DO UPDATE SET score = EXCLUDED.score, player_name = EXCLUDED.player_name""",
                quiz_id, player_id, player_name, score
            )
        return

    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO scores (quiz_id, player_id, player_name, score)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(quiz_id, player_id) DO UPDATE SET score=excluded.score, player_name=excluded.player_name""",
            (quiz_id, player_id, player_name, score)
        )
        await db.commit()


async def update_score(quiz_id: str, player_id: str, player_name: str, score: int):
    await save_score(quiz_id, player_id, player_name, score)


async def get_leaderboard(quiz_id: str):
    if IS_POSTGRES and pg_pool:
        async with pg_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT player_name, score FROM scores WHERE quiz_id = $1 ORDER BY score DESC",
                quiz_id
            )
            return [{"name": r["player_name"], "score": r["score"]} for r in rows]

    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT player_name, score FROM scores WHERE quiz_id = ? ORDER BY score DESC",
            (quiz_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [{"name": r[0], "score": r[1]} for r in rows]
