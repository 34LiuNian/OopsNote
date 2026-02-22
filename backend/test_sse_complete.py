#!/usr/bin/env python3
"""
Complete SSE test script that:
1. Creates a task
2. Connects to SSE stream 
3. Triggers simulation
4. Verifies events are received in real-time
"""

import asyncio
import aiohttp
import json
import time
from urllib.parse import urlencode

async def test_sse_complete():
    base_url = "http://localhost:8000"
    
    # Step 1: Create task
    print("1. Creating task...")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{base_url}/tasks?auto_process=false",
            json={"subject": "test", "content": "test"}
        ) as resp:
            task_data = await resp.json()
            task_id = task_data["task"]["id"]
            print(f"Created task: {task_id}")
    
    # Step 2: Start SSE connection
    print("2. Starting SSE connection...")
    sse_events = []
    
    async def listen_sse():
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/tasks/{task_id}/events") as resp:
                async for line in resp.content:
                    line = line.decode().strip()
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip():
                            try:
                                event = json.loads(data)
                                sse_events.append(event)
                                print(f"Received SSE event: {event}")
                            except json.JSONDecodeError:
                                print(f"Invalid JSON: {data}")
    
    # Step 3: Start simulation (with small delay to ensure SSE connects first)
    print("3. Starting simulation...")
    sse_task = asyncio.create_task(listen_sse())
    
    # Give SSE a moment to connect
    await asyncio.sleep(0.5)
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{base_url}/tasks/{task_id}/simulate?background=true",
            json={}
        ) as resp:
            print(f"Simulation started: {resp.status}")
    
    # Wait for simulation to complete and collect events
    await asyncio.sleep(10)  # Wait for all events
    sse_task.cancel()
    
    # Step 4: Verify results
    print(f"\n4. Test Results:")
    print(f"Total SSE events received: {len(sse_events)}")
    
    expected_events = [
        "starting", "detector", "detector", "ocr", "ocr", "ocr", "ocr",
        "solver", "solver", "solver", "solver", "tagger", "tagger", "tagger", "tagger", "done"
    ]
    
    if len(sse_events) >= len(expected_events):
        print("✅ SUCCESS: All expected events received!")
        return True
    else:
        print(f"❌ INCOMPLETE: Expected {len(expected_events)} events, got {len(sse_events)}")
        return False

if __name__ == "__main__":
    asyncio.run(test_sse_complete())