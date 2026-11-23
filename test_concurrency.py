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
    print("Error: 'websockets' and 'httpx' libraries are required.")
    print("Install with: pip install websockets httpx")
    sys.exit(1)

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE


async def run_concurrency_and_penalty_test(base_url: str):
    print("=" * 60)
    print(f"⚡ QUIZARRE: CONCURRENCY & BUZZER PENALTY TEST")
    print(f"Target: {base_url}")
    print("=" * 60)

    http_url = base_url.rstrip("/")
    if http_url.startswith("https"):
        ws_url = "wss://" + http_url[8:]
    elif http_url.startswith("http"):
        ws_url = "ws://" + http_url[7:]
    else:
        ws_url = "ws://" + http_url

    # 1. Health check & wake up
    print("\n[Step 1] Checking backend health...")
    async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
        try:
            res = await client.get(f"{http_url}/health")
            print(f"Health response ({res.status_code}): {res.text}")
        except Exception as e:
            print(f"Could not reach {http_url}/health: {e}")
            return False

    # 2. Create quiz with buzzer mode
    print("\n[Step 2] Creating test quiz room in BUZZER mode...")
    quiz_payload = {
        "title": "Buzzer Penalty Test",
        "host_name": "TestHost",
        "mode": "buzzer",
        "questions": [
            {
                "question": "What is the capital of France?",
                "options": ["London", "Berlin", "Paris", "Rome"],
                "correct": "Paris"
            }
        ]
    }

    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        res = await client.post(f"{http_url}/api/quiz/create", json=quiz_payload)
        if res.status_code != 200:
            print(f"Failed to create quiz: {res.text}")
            return False
        quiz_id = res.json()["quiz_id"]
        print(f"Created Quiz Room: {quiz_id}")

    # 3. Connect Host and 2 Players
    print("\n[Step 3] Connecting Host, Player 1 (Alice), and Player 2 (Bob)...")
    host_id = "HOST_" + str(uuid.uuid4())[:6]
    p1_id = "P1_" + str(uuid.uuid4())[:6]
    p2_id = "P2_" + str(uuid.uuid4())[:6]

    host_ws_url = f"{ws_url}/ws/{quiz_id}/{host_id}"
    p1_ws_url = f"{ws_url}/ws/{quiz_id}/{p1_id}"
    p2_ws_url = f"{ws_url}/ws/{quiz_id}/{p2_id}"

    async with websockets.connect(host_ws_url, ssl=ssl_ctx) as host_ws, \
               websockets.connect(p1_ws_url, ssl=ssl_ctx) as p1_ws, \
               websockets.connect(p2_ws_url, ssl=ssl_ctx) as p2_ws:

        # Join room
        await host_ws.send(json.dumps({"type": "join", "name": "Host", "role": "host"}))
        await p1_ws.send(json.dumps({"type": "join", "name": "Alice", "role": "player"}))
        await p2_ws.send(json.dumps({"type": "join", "name": "Bob", "role": "player"}))
        print("All 3 clients joined room successfully.")
        await asyncio.sleep(1)

        # 4. Host starts quiz
        print("\n[Step 4] Host starts quiz...")
        await host_ws.send(json.dumps({"type": "start_quiz"}))
        await asyncio.sleep(1)

        # 5. Alice buzzes in
        print("\n[Step 5] Alice presses the buzzer...")
        await p1_ws.send(json.dumps({"type": "buzz"}))
        await asyncio.sleep(0.5)

        # 6. Alice submits a WRONG answer
        print("\n[Step 6] Alice submits WRONG answer ('London')...")
        await p1_ws.send(json.dumps({"type": "answer", "answer": "London"}))
        await asyncio.sleep(1)

        # Read state on Bob's socket
        state = None
        while True:
            try:
                msg_raw = await asyncio.wait_for(p2_ws.recv(), timeout=2.0)
                msg = json.loads(msg_raw)
                if msg.get("type") == "state":
                    state = msg
                    break
            except asyncio.TimeoutError:
                break

        if not state:
            print("ERROR: Did not receive updated state after Alice's wrong answer.")
            return False

        alice_score = state.get("scores", {}).get(p1_id, 0)
        print(f"Alice's Score after wrong answer: {alice_score}")

        # Verification 1: Score must be -1 (Jeopardy penalty)
        if alice_score == -1:
            print("PASSED: -1 negative penalty correctly applied to Alice!")
        else:
            print(f"FAILED: Expected Alice's score to be -1, got {alice_score}")
            return False

        # 7. Bob buzzes in and gives CORRECT answer
        print("\n[Step 7] Bob presses the buzzer...")
        await p2_ws.send(json.dumps({"type": "buzz"}))
        await asyncio.sleep(0.5)

        print("[Step 8] Bob submits CORRECT answer ('Paris')...")
        await p2_ws.send(json.dumps({"type": "answer", "answer": "Paris"}))
        await asyncio.sleep(1)

        # Read final state
        final_state = None
        while True:
            try:
                msg_raw = await asyncio.wait_for(p1_ws.recv(), timeout=2.0)
                msg = json.loads(msg_raw)
                if msg.get("type") == "state":
                    final_state = msg
                    break
            except asyncio.TimeoutError:
                break

        bob_score = final_state.get("scores", {}).get(p2_id, 0)
        final_alice_score = final_state.get("scores", {}).get(p1_id, 0)
        print(f"\nFinal Scores: Alice = {final_alice_score}, Bob = {bob_score}")

        if bob_score == 1 and final_alice_score == -1:
            print("=" * 60)
            print("TEST COMPLETED SUCCESSFULLY!")
            print("  1. Real-time WebSocket broadcasting verified.")
            print("  2. Turn advancement on wrong answer verified.")
            print("  3. +1 for correct answer verified.")
            print("  4. -1 Jeopardy-style penalty for wrong answer verified.")
            print("=" * 60)
            return True
        else:
            print(f"FAILED: Scores mismatch. Expected Alice: -1, Bob: 1.")
            return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quizarre Concurrency & Penalty Tester")
    parser.add_argument("--url", default="https://quizarre-vercel.onrender.com", help="Backend base URL")
    args = parser.parse_args()

    try:
        success = asyncio.run(run_concurrency_and_penalty_test(args.url))
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nTest cancelled.")
