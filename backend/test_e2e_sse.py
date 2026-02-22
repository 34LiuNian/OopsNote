"""End-to-end test for SSE functionality."""
import asyncio
import json
import threading
import time
from app.bootstrap import create_app

async def test_e2e_sse():
    """Test end-to-end SSE functionality."""
    print("Creating app...")
    app = create_app()
    state = app.state.oops
    tasks_svc = state.tasks
    sse_svc = state.sse
    
    # Create a test task
    from app.models import TaskCreateRequest
    payload = TaskCreateRequest(
        subject="test",
        content="test content", 
        image_url="http://example.com/test.jpg",
        problems=[],
        tags=[],
        detection=None
    )
    task = tasks_svc.create_task(payload, auto_process=False)
    task_id = task.id
    print(f"Created task: {task_id}")
    
    # Start SSE subscription
    print("Starting SSE subscription...")
    sse_generator = sse_svc.subscribe_task_events(task_id)
    
    # Start simulation in background
    def simulate_processing():
        stages = [
            ("starting", "开始处理"),
            ("ocr", "OCR 提取中..."),
            ("solver", "解题中..."),
            ("done", "处理完成"),
        ]
        
        for stage, message in stages:
            time.sleep(0.5)
            if hasattr(tasks_svc, 'event_bus') and tasks_svc.event_bus:
                tasks_svc.event_bus.publish(task_id, "progress", {"stage": stage, "message": message})
                print(f"Published event: {stage}")
        
        if hasattr(tasks_svc, 'event_bus') and tasks_svc.event_bus:
            tasks_svc.event_bus.finish_broadcast(task_id)
    
    sim_thread = threading.Thread(target=simulate_processing, daemon=True)
    sim_thread.start()
    
    # Consume SSE events
    print("Consuming SSE events...")
    received_events = []
    try:
        async for event in sse_generator:
            print(f"Received SSE event: {event[:100]}...")
            received_events.append(event)
            if len(received_events) >= 4:  # We expect 4 progress events + done
                break
    except Exception as e:
        print(f"SSE consumption error: {e}")
    
    sim_thread.join(timeout=2)
    
    print(f"Test completed. Received {len(received_events)} events.")
    return len(received_events) > 0

if __name__ == "__main__":
    result = asyncio.run(test_e2e_sse())
    print(f"E2E Test {'PASSED' if result else 'FAILED'}")