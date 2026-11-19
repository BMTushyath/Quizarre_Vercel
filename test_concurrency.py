import asyncio
import subprocess
import time
import websockets
import json

def start_server():
    return subprocess.Popen(
        ["venv/Scripts/python.exe", "-m", "uvicorn", "main:app", "--port", "8005", "--host", "127.0.0.1"],
        cwd="c:/Users/Tushyath/Documents/projects/BuzzQuiz"
    )

async def test_broadcast():
    server_process = start_server()
    await asyncio.sleep(3)  # Wait for server to boot
    
    BASE_URL = "http://localhost:8005"
    WS_URL = "ws://localhost:8005/ws"
    
    quiz_id = None
    try:
        questions = [
            {"question": "What is 2+2?", "options": ["3", "4", "5", "6"], "correct": "4"}
        ]
        import urllib.request
        req = urllib.request.Request(
            f"{BASE_URL}/api/quiz/create",
            data=json.dumps({
                "questions": questions,
                "host_name": "Host",
                "title": "Test Quiz",
                "mode": "classic"
            }).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req) as res:
            res_content = res.read().decode('utf-8')
            print("Create Quiz Status:", res.status)
            print("Create Quiz Response:", res_content)
            data = json.loads(res_content)
        quiz_id = data["quiz_id"]
        print(f"Quiz Created: {quiz_id}")
        
        # 2. Connect 3 clients
        # 1 Host, 2 Players
        async def connect_client(player_id, name, role):
            url = f"{WS_URL}/{quiz_id}/{player_id}"
            print(f"Connecting {name} ({role}) to {url}")
            async with websockets.connect(url) as ws:
                # Join message
                await ws.send(json.dumps({"type": "join", "name": name, "role": role}))
                print(f"{name} joined.")
                
                # Receive messages
                count = 0
                while count < 3:  # Listen for a few broadcast updates
                    msg_txt = await ws.recv()
                    msg = json.loads(msg_txt)
                    print(f"[{name}] Recv:", msg.get("type"))
                    count += 1
                await asyncio.sleep(1)
                
        # Run clients concurrently
        print("Starting concurrent clients...")
        await asyncio.gather(
            connect_client("host1", "HostName", "host"),
            connect_client("player1", "Alice", "player"),
            connect_client("player2", "Bob", "player"),
            return_exceptions=False
        )
        print("Test passed successfully!")
                
    except Exception as e:
        print("Test failed with exception:", e)
        import traceback
        traceback.print_exc()
    finally:
        print("Terminating server...")
        server_process.terminate()
        server_process.wait()

if __name__ == "__main__":
    asyncio.run(test_broadcast())
