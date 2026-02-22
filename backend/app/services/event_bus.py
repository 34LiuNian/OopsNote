from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventBus:
    """事件总线，用于解耦核心处理逻辑和事件推送"""
    
    def __init__(self, streams_dir: Path):
        self.streams_dir = streams_dir
        self.streams_dir.mkdir(parents=True, exist_ok=True)
        
        # 事件订阅者
        self._subscribers: Dict[str, List[Callable[[str, Dict], None]]] = {}
        self._subscribers_lock = threading.Lock()
        
        # 同步队列（用于SSE）
        self._sync_queues: Dict[str, List[queue.Queue]] = {}
        self._sync_queues_lock = threading.Lock()
        
        # 异步队列（用于SSE）
        self._async_queues: Dict[str, List[asyncio.Queue]] = {}
        self._async_queues_lock = threading.Lock()
        
        # 适配器任务
        self._adapter_tasks: Dict[str, List[asyncio.Task]] = {}
        
        # 待处理事件（客户端连接前的事件缓存）
        self._pending_events: Dict[str, List[Dict]] = {}
        self._pending_events_lock = threading.RLock()
        
        # 事件TTL（秒），避免内存泄漏
        self._event_ttl = 3600  # 1小时

    def subscribe(self, task_id: str, callback: Callable[[str, Dict], None]) -> None:
        """订阅任务事件"""
        with self._subscribers_lock:
            if task_id not in self._subscribers:
                self._subscribers[task_id] = []
            self._subscribers[task_id].append(callback)

    def unsubscribe(self, task_id: str, callback: Callable[[str, Dict], None]) -> None:
        """取消订阅任务事件"""
        with self._subscribers_lock:
            if task_id in self._subscribers:
                try:
                    self._subscribers[task_id].remove(callback)
                    if not self._subscribers[task_id]:
                        del self._subscribers[task_id]
                except ValueError:
                    pass

    def publish(self, task_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        """发布事件到所有订阅者"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Publishing event: task_id={task_id}, event_type={event_type}")
        
        # 清理过期的pending events
        self._cleanup_pending_events(task_id)
        
        # 构建完整事件数据
        event_data = {
            "event": event_type,
            "payload": payload,
            "ts": datetime.now(timezone.utc).isoformat()
        }
        
        # 持久化到文件
        self._persist_to_file(task_id, event_data)
        
        # 检查是否有活跃订阅者
        has_subscribers = self._has_active_subscribers(task_id)
        logger.info(f"Task {task_id} has active subscribers: {has_subscribers}")
        
        # 通知同步订阅者（SSE）
        self._notify_sync_subscribers(task_id, event_data)
        
        # 通知异步订阅者
        self._notify_async_subscribers(task_id, event_type, payload)
        
        # 如果没有活跃订阅者，缓存事件
        if not has_subscribers:
            self._cache_pending_event(task_id, event_data)
            logger.info(f"Event cached as pending for task {task_id}")
        else:
            logger.info(f"Event delivered to active subscribers for task {task_id}")

    def _has_active_subscribers(self, task_id: str) -> bool:
        """检查是否有活跃的订阅者"""
        with self._sync_queues_lock:
            has_sync = task_id in self._sync_queues and len(self._sync_queues[task_id]) > 0
        
        with self._subscribers_lock:
            has_async = task_id in self._subscribers and len(self._subscribers[task_id]) > 0
            
        return has_sync or has_async

    def _persist_to_file(self, task_id: str, event_data: Dict) -> None:
        """持久化事件到文件"""
        try:
            path = self.streams_dir / f"{task_id}.txt"
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event_data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("Failed to write stream to file %s: %s", task_id, e)

    def _notify_sync_subscribers(self, task_id: str, event_data: Dict) -> None:
        """通知同步订阅者（SSE队列）"""
        with self._sync_queues_lock:
            sync_queues = self._sync_queues.get(task_id, [])
            for q in sync_queues:
                try:
                    q.put_nowait(event_data)
                except queue.Full:
                    logger.warning("Sync queue full for task %s", task_id)
                except Exception as e:
                    logger.debug("Error notifying sync subscriber: %s", e)

    def _notify_async_subscribers(self, task_id: str, event_type: str, payload: Dict) -> None:
        """通知异步订阅者"""
        with self._subscribers_lock:
            subscribers = self._subscribers.get(task_id, [])
            for callback in subscribers[:]:  # 使用副本避免修改时的并发问题
                try:
                    callback(event_type, payload)
                except Exception as e:
                    logger.error("Error in async subscriber callback: %s", e)

    def _cache_pending_event(self, task_id: str, event_data: Dict) -> None:
        """缓存待处理事件"""
        with self._pending_events_lock:
            if task_id not in self._pending_events:
                self._pending_events[task_id] = []
            self._pending_events[task_id].append(event_data)

    def _cleanup_pending_events(self, task_id: str) -> None:
        """清理过期的pending events"""
        with self._pending_events_lock:
            if task_id not in self._pending_events:
                return
                
            current_time = datetime.now(timezone.utc)
            valid_events = []
            for event in self._pending_events[task_id]:
                try:
                    event_time = datetime.fromisoformat(event["ts"].replace("Z", "+00:00"))
                    if (current_time - event_time).total_seconds() < self._event_ttl:
                        valid_events.append(event)
                except (ValueError, KeyError):
                    # 无效的时间戳，保留事件以防丢失重要信息
                    valid_events.append(event)
            
            if valid_events:
                self._pending_events[task_id] = valid_events
            else:
                del self._pending_events[task_id]

    # ==================== SSE 相关方法 ====================
    
    def get_sse_queues(self, task_id: str) -> tuple[asyncio.Queue, queue.Queue]:
        """获取SSE队列对（异步+同步）"""
        async_queue = asyncio.Queue(maxsize=1000)
        sync_queue = queue.Queue(maxsize=1000)
        return async_queue, sync_queue

    def register_sse_queues(self, task_id: str, async_queue: asyncio.Queue, sync_queue: queue.Queue, adapter_task: asyncio.Task) -> None:
        """注册SSE队列"""
        with self._async_queues_lock:
            if task_id not in self._async_queues:
                self._async_queues[task_id] = []
            self._async_queues[task_id].append(async_queue)
        
        with self._sync_queues_lock:
            if task_id not in self._sync_queues:
                self._sync_queues[task_id] = []
                self._adapter_tasks[task_id] = []
            self._sync_queues[task_id].append(sync_queue)
            self._adapter_tasks[task_id].append(adapter_task)
        
        # 发送pending events
        self._deliver_pending_events(task_id, sync_queue)

    def unregister_sse_queues(self, task_id: str, async_queue: asyncio.Queue, sync_queue: queue.Queue, adapter_task: asyncio.Task) -> None:
        """注销SSE队列"""
        with self._async_queues_lock:
            if task_id in self._async_queues:
                try:
                    self._async_queues[task_id].remove(async_queue)
                    if not self._async_queues[task_id]:
                        del self._async_queues[task_id]
                except ValueError:
                    pass
        
        with self._sync_queues_lock:
            if task_id in self._sync_queues:
                try:
                    self._sync_queues[task_id].remove(sync_queue)
                    if not self._sync_queues[task_id]:
                        del self._sync_queues[task_id]
                        if task_id in self._adapter_tasks:
                            del self._adapter_tasks[task_id]
                except ValueError:
                    pass
        
        # 取消适配器任务
        try:
            adapter_task.cancel()
        except Exception:
            pass

    def _deliver_pending_events(self, task_id: str, sync_queue: queue.Queue) -> None:
        """向新连接的客户端发送pending events"""
        with self._pending_events_lock:
            if task_id in self._pending_events:
                for event in self._pending_events[task_id]:
                    try:
                        sync_queue.put_nowait(event)
                    except queue.Full:
                        logger.warning("Queue full while delivering pending events")
                        break
                del self._pending_events[task_id]

    def finish_broadcast(self, task_id: str) -> None:
        """发送结束信号"""
        sentinel = None
        with self._sync_queues_lock:
            sync_queues = self._sync_queues.get(task_id, [])
            for q in sync_queues:
                try:
                    q.put_nowait(sentinel)
                except Exception:
                    pass

    def get_task_stream(self, task_id: str, max_chars: int = 200000) -> str:
        """读取历史流"""
        path = self.streams_dir / f"{task_id}.txt"
        if not path.exists():
            return ""
        try:
            content = path.read_text(encoding="utf-8")
            if len(content) > max_chars:
                return content[-max_chars:]
            return content
        except Exception as e:
            logger.warning("Failed to read task stream %s: %s", task_id, e)
            return ""