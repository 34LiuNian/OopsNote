from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import Request

from .event_bus import EventBus

logger = logging.getLogger(__name__)


class SseService:
    """SSE服务，处理客户端连接和事件推送"""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus

    async def subscribe_task_events(self, task_id: str, request: Request) -> AsyncGenerator[str, None]:
        """Subscribe to real-time events for a task via SSE."""
        logger.info("SSE: client subscribing to task_id=%s", task_id)
        
        # Get task status to handle completed tasks
        repo = request.app.state.oops.repository
        try:
            task = repo.get(task_id)
            is_terminal = task.status in ["completed", "failed", "cancelled"]
            logger.info(f"SSE: task {task_id} status={task.status}, is_terminal={is_terminal}")
        except Exception as e:
            logger.warning(f"SSE: failed to get task status for {task_id}: {e}")
            is_terminal = False
        
        # Get queue pair from event bus
        async_queue, sync_queue = self.event_bus.get_sse_queues(task_id)
        
        # Adapter task: sync -> async
        async def adapter():
            try:
                logger.info(f"SSE adapter started for task {task_id}")
                while True:
                    logger.info(f"SSE adapter waiting for sync_queue.get() for task {task_id}")
                    data = await asyncio.get_event_loop().run_in_executor(None, sync_queue.get)
                    logger.info(f"SSE adapter received data: {data}")
                    if data is None:
                        logger.info(f"SSE adapter received sentinel for task {task_id}")
                        break
                    await async_queue.put(data)
                    logger.info(f"SSE adapter put data to async_queue for task {task_id}")
            except Exception as e:
                logger.error(f"SSE adapter error for task {task_id}: {e}", exc_info=True)
        
        adapter_task = asyncio.create_task(adapter())
        logger.info(f"SSE adapter task created for task {task_id}")
        
        # Register queues with event bus
        self.event_bus.register_sse_queues(task_id, async_queue, sync_queue, adapter_task)
        
        # If task is already completed, send done event and sentinel immediately
        if is_terminal:
            logger.info(f"SSE: task {task_id} already completed, sending done event and sentinel")
            # Send pending events first
            await asyncio.sleep(0.05)  # Give time for pending events to be delivered
            # Send done event
            done_event = {
                "event": "done",
                "payload": {"status": task.status, "error": getattr(task, 'last_error', None)},
                "ts": datetime.now(timezone.utc).isoformat()
            }
            sync_queue.put_nowait(done_event)
            logger.info(f"SSE: sent done event for completed task {task_id}")
            # Send sentinel
            sync_queue.put_nowait(None)
            logger.info(f"SSE: sent sentinel for completed task {task_id}")
        
        logger.info("SSE: registered connection for task_id=%s", task_id)
        
        try:
            while True:
                data = await async_queue.get()
                if data is None:
                    logger.info("SSE: received sentinel for task_id=%s", task_id)
                    break
                # Standard SSE format with proper line endings
                event_line = f"event: {data['event']}\r\ndata: {json.dumps(data['payload'], ensure_ascii=False)}\r\n\r\n"
                logger.info(f"SSE: sending event: {data['event']} - {data['payload']}")
                yield event_line
        finally:
            # Unregister queues and cleanup
            self.event_bus.unregister_sse_queues(task_id, async_queue, sync_queue, adapter_task)
            logger.info("SSE: client unsubscribed from task_id=%s", task_id)