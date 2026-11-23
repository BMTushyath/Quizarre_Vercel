import asyncio
import json
import ssl
import sys
import time
import uuid
import argparse

try:
    import websockets
    import httpx
except ImportError:
    print("Error: 'websockets' and 'httpx' libraries are required for load testing.")
    print("Install with: pip install websockets httpx")
    sys.exit(1)

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE


class LoadTestMetrics:
    def __init__(self):
        self.connected_count = 0
        self.connection_errors = 0
        self.messages_received = 0
        self.answers_submitted = 0
        self.latencies = []
        self.start_time = None
        self.end_time = None


async def simulate_player(ws_url: str, quiz_id: str, player_num: int, metrics: LoadTestMetrics, duration: int):
    player_id = f"P{player_num:03d}_" + str(uuid.uuid4())[:4]
    name = f"Player_{player_num:02d}"
    url = f"{ws_url}/ws/{quiz_id}/{player_id}"

    t0 = time.time()
    try:
        async with websockets.connect(url, ssl=ssl_ctx) as ws:
            connect_latency = (time.time() - t0) * 1000
            metrics.latencies.append(connect_latency)
            metrics.connected_count += 1
            if metrics.connected_count % 10 == 0:
                print(f"  -> {metrics.connected_count} players connected (last join: {connect_latency:.1f}ms)...")

            # Join room
            await ws.send(json.dumps({"type": "join", "name": name, "role": "player"}))

            end_at = time.time() + duration
            while time.time() < end_at:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    msg = json.loads(raw)
                    metrics.messages_received += 1

                    msg_type = msg.get("type")
                    if msg_type == "state":
                        status = msg.get("status")
                        answering = msg.get("answering_player")

                        # If buzzer round and it's this player's turn to answer
                        if status == "question" and answering == player_id:
                            q = msg.get("question", {})
                            opts = q.get("options", ["A", "B", "C", "D"])
                            ans = opts[player_num % len(opts)]
                            await asyncio.sleep(0.3)
                            await ws.send(json.dumps({"type": "answer", "answer": ans}))
                            metrics.answers_submitted += 1

                    elif msg_type == "new_question":
                        # Simulate hitting buzzer with a slight human stagger (100ms - 800ms)
                        delay = 0.1 + ((player_num % 10) * 0.08)
                        await asyncio.sleep(delay)
                        await ws.send(json.dumps({"type": "buzz"}))

                except asyncio.TimeoutError:
                    continue

    except Exception as e:
        metrics.connection_errors += 1
        print(f"  [Player {player_num}] Disconnect/Error: {e}")


async def run_load_test(base_url: str, total_players: int = 70, duration: int = 15):
    print("=" * 65)
    print(f"⚡ QUIZARRE: HIGH-CONCURRENCY LOAD TEST ({total_players} USERS)")
    print(f"Target: {base_url}")
    print(f"Duration: {duration} seconds")
    print("=" * 65)

    http_url = base_url.rstrip("/")
    if http_url.startswith("https"):
        ws_url = "wss://" + http_url[8:]
    elif http_url.startswith("http"):
        ws_url = "ws://" + http_url[7:]
    else:
        ws_url = "ws://" + http_url

    # 1. Wake up server
    print("\n[Phase 1] Waking up backend and checking health...")
    async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
        try:
            t_health = time.time()
            res = await client.get(f"{http_url}/health")
            print(f"Server alive in {(time.time() - t_health)*1000:.1f}ms! Details: {res.text}")
        except Exception as e:
            print(f"FAILED: Backend unreachable at {http_url}: {e}")
            return False

    # 2. Create room
    print(f"\n[Phase 2] Creating test quiz for {total_players} players...")
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        res = await client.post(f"{http_url}/api/quiz/create", json={
            "title": f"Load Test {total_players} Players",
            "host_name": "LoadHost",
            "mode": "buzzer",
            "questions": [
                {
                    "question": "Q1: What is 10 + 10?",
                    "options": ["15", "20", "25", "30"],
                    "correct": "20"
                },
                {
                    "question": "Q2: Which planet is known as the Red Planet?",
                    "options": ["Venus", "Mars", "Jupiter", "Saturn"],
                    "correct": "Mars"
                }
            ]
        })
        if res.status_code != 200:
            print(f"Failed to create room: {res.text}")
            return False
        quiz_id = res.json()["quiz_id"]
        print(f"Quiz Room Created: {quiz_id}")

    # 3. Connect Host
    metrics = LoadTestMetrics()
    metrics.start_time = time.time()

    host_id = "HOST_" + str(uuid.uuid4())[:6]
    host_ws_url = f"{ws_url}/ws/{quiz_id}/{host_id}"

    async with websockets.connect(host_ws_url, ssl=ssl_ctx) as host_ws:
        await host_ws.send(json.dumps({"type": "join", "name": "LoadHost", "role": "host"}))

        # 4. Ramp up all 60-70 players concurrently
        print(f"\n[Phase 3] Launching {total_players} concurrent WebSocket connections...")
        player_tasks = [
            simulate_player(ws_url, quiz_id, i + 1, metrics, duration)
            for i in range(total_players)
        ]

        # Let all players connect
        ramp_up = asyncio.gather(*player_tasks, return_exceptions=True)

        # Wait 3 seconds for everyone to join
        await asyncio.sleep(3)

        # 5. Host starts quiz
        print("\n[Phase 4] Host triggers Question 1 broadcast...")
        await host_ws.send(json.dumps({"type": "start_quiz"}))

        # Let the buzzer simulation run for 6 seconds
        await asyncio.sleep(6)

        # Host advances to Question 2
        print("[Phase 5] Host advances to Question 2 broadcast...")
        await host_ws.send(json.dumps({"type": "next_question"}))

        # Await remaining duration
        await ramp_up

    metrics.end_time = time.time()
    total_elapsed = metrics.end_time - metrics.start_time

    # 6. Report Metrics
    avg_latency = (sum(metrics.latencies) / len(metrics.latencies)) if metrics.latencies else 0
    p95_latency = sorted(metrics.latencies)[int(len(metrics.latencies) * 0.95)] if metrics.latencies else 0

    print("\n" + "=" * 65)
    print("📊 LOAD TEST RESULTS & BENCHMARK SUMMARY")
    print("=" * 65)
    print(f"  Target Users Configured:      {total_players}")
    print(f"  Successfully Connected:       {metrics.connected_count} / {total_players}")
    print(f"  Connection Drop / Errors:     {metrics.connection_errors}")
    print(f"  Total WS Messages Broadcast:  {metrics.messages_received}")
    print(f"  Average Connect Latency:      {avg_latency:.1f} ms")
    print(f"  95th Percentile Latency:      {p95_latency:.1f} ms")
    print(f"  Total Test Time:              {total_elapsed:.1f} s")
    print("=" * 65)

    success_rate = (metrics.connected_count / total_players) * 100
    if success_rate >= 95.0 and metrics.connection_errors == 0:
        print("✅ VERDICT: PASS! Backend handles 60-70 concurrent users smoothly.")
        return True
    else:
        print(f"⚠️ VERDICT: Noticeable packet drops or connection errors ({metrics.connection_errors}).")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quizarre 60-70 User Load Tester")
    parser.add_argument("--url", default="https://quizarre-vercel.onrender.com", help="Backend base URL")
    parser.add_argument("--players", type=int, default=70, help="Total players to simulate (default: 70)")
    parser.add_argument("--duration", type=int, default=15, help="Simulation duration in seconds")
    args = parser.parse_args()

    try:
        success = asyncio.run(run_load_test(args.url, args.players, args.duration))
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nLoad test interrupted by user.")
