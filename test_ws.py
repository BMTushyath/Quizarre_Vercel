import asyncio
import websockets

async def test():
    try:
        async with websockets.connect('ws://localhost:8000/ws/123/456') as ws:
            print('connected')
    except Exception as e:
        print('Error:', e)

asyncio.run(test())
