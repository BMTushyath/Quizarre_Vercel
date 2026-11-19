import asyncio
import json
import time
import uuid
import sys
import argparse
import ssl

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

try:
    import websockets
    import httpx
except ImportError:
    print("Error: 'websockets' and 'httpx' libraries are required for this load test.")
    print("Run: pip install websockets httpx")
    sys.exit(1)

API_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

async def simulate_player(room_id, player_index):
    player_id = str(uuid.uuid4())[:8].upper()
    name = f"Player_{room_id}_{player_index}"
    
    ws_url = f"{WS_URL}/ws/{room_id}/{player_id}"
    print(f"[{name}] Connecting to {room_id}...")
    
    try:
        async with websockets.connect(ws_url, ssl=ssl_ctx) as ws:
            # 1. Join
            await ws.send(json.dumps({"type": "join", "name": name, "role": "player"}))
            print(f"[{name}] Joined Room {room_id}")
            
            # 2. Listen for messages
            async for message in ws:
                data = json.loads(message)
                msg_type = data.get("type")
                
                if msg_type == "state":
                    status = data.get("status")
                    if status == "question" and "question" in data:
                        # Question active, simulate thinking and answering
                        options = data["question"].get("options", [])
                        if options:
                            await asyncio.sleep(1 + (player_index % 3)) # simulate thinking delay
                            answer = options[player_index % len(options)]
                            await ws.send(json.dumps({"type": "answer", "answer": answer}))
                            # print(f"[{name}] Answered: {answer}")
                
                elif msg_type == "new_question":
                    # print(f"[{name}] New Question loaded")
                    pass
                    
    except Exception as e:
        print(f"[{name}] Error: {e}")

async def create_room(title, mode="classic"):
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        try:
            res = await client.post(f"{API_URL}/api/quiz/create", json={
                "questions": [
                    {"question": "Test Q1", "options": ["A", "B", "C", "D"], "correct": "A"},
                    {"question": "Test Q2", "options": ["A", "B", "C", "D"], "correct": "B"}
                ],
                "title": title,
                "host_name": "TestHost",
                "mode": mode
            })
            if res.status_code == 200:
                data = res.json()
                return data["quiz_id"]
            else:
                print(f"Failed to create room: {res.text}")
                return None
        except Exception as e:
            print(f"Connection error creating room: {e}")
            import traceback
            traceback.print_exc()
            return None

async def start_game(room_id):
    # Simulate host starting the game
    host_id = "HOST_TEST_" + str(uuid.uuid4())[:4]
    ws_url = f"{WS_URL}/ws/{room_id}/{host_id}"
    
    try:
        async with websockets.connect(ws_url, ssl=ssl_ctx) as ws:
            await ws.send(json.dumps({"type": "join", "name": "Host", "role": "host"}))
            await asyncio.sleep(1) # wait for joins
            await ws.send(json.dumps({"type": "next_question"}))
            print(f"[Host] Game started in {room_id}")
            await asyncio.sleep(5) # Let game run for a bit
    except Exception as e:
         print(f"[Host] Error: {e}")

async def main():
    parser = argparse.ArgumentParser(description="BuzzQuiz Load Tester")
    parser.add_argument("--api", default="http://localhost:8000", help="API URL (e.g. http://localhost:8000)")
    parser.add_argument("--ws", default="ws://localhost:8000", help="WebSocket URL (e.g. ws://localhost:8000)")
    parser.add_argument("--players", type=int, default=100, help="Total players to simulate")
    parser.add_argument("--rooms", type=int, default=2, help="Count of rooms to split players into")
    args = parser.parse_args()

    global API_URL, WS_URL
    API_URL = args.api
    WS_URL = args.ws

    print(f"--- Starting Load Test ---")
    print(f"API: {API_URL}")
    print(f"WS: {WS_URL}")
    print(f"Target: {args.players} players across {args.rooms} rooms")

    # 1. Create Rooms
    room_ids = []
    for i in range(args.rooms):
        r_id = await create_room(f"LoadTest_{i+1}")
        if r_id:
            room_ids.append(r_id)
            print(f"Created Room: {r_id}")
    
    if not room_ids:
        print("Aborting: Could not create any rooms.")
        return

    # 2. Spawn Players
    tasks = []
    players_per_room = args.players // len(room_ids)
    
    for r_idx, r_id in enumerate(room_ids):
        for p_idx in range(players_per_room):
            tasks.append(simulate_player(r_id, p_idx))

    print(f"Connecting remaining clients concurrently...")
    
    # Run parallel client tasks
    player_tasks = asyncio.gather(*tasks)
    
    # Let them connect
    await asyncio.sleep(3)
    
    # 3. Start Game in both rooms
    start_tasks = [start_game(r_id) for r_id in room_ids]
    await asyncio.gather(*start_tasks)
    
    print("Waiting for simulation to stabilize...")
    await asyncio.sleep(10) # Run simulation interval
    print("Load test complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest stopped.")
