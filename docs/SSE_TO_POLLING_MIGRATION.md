# SSE 迁移到轮询实现报告

**日期**: 2026 年 2 月 23 日  
**迁移类型**: Server-Sent Events (SSE) → HTTP Polling

---

## 迁移概述

将 OopsNote 项目的实时任务更新机制从 SSE (Server-Sent Events) 改为 HTTP 轮询模式。

### 迁移决策

- **轮询间隔**: 1000ms (1 秒)
- **历史流**: 移除历史流加载逻辑
- **SSE 文件**: 完全删除 `sse_service.py` 和 `event_bus.py`
- **前端 Hook**: 删除 `useSimpleSSE`，只保留并改造 `useTaskStream` 为轮询实现

---

## 后端修改

### 1. 删除的文件

- ❌ `backend/app/services/sse_service.py` - SSE 服务实现
- ❌ `backend/app/services/event_bus.py` - 事件总线实现

### 2. 修改的文件

#### `backend/app/services/tasks_service.py`

**变更**:
- 移除 `EventBus` 导入和依赖注入
- 删除 `event_bus` 参数从构造函数
- 移除所有 `event_bus.publish()` 调用
- 简化 `progress_bridge()` 为直接写入流文件
- 删除 `get_task_stream()` 方法（前端不再需要）
- 简化 `_finalize_*()` 方法，移除事件发布
- 重命名 `_legacy_broadcast()` 为 `_write_stream_event()`

**关键代码**:
```python
def _write_stream_event(self, task_id: str, event: str, payload: dict):
    """Write an event to the task stream file for polling."""
    data = {"event": event, "payload": payload, "ts": datetime.now(timezone.utc).isoformat()}
    
    path = self.streams_dir / f"{task_id}.txt"
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("Failed to write stream: %s", e)
```

#### `backend/app/api/tasks.py`

**变更**:
- 删除 `StreamingResponse` 导入
- 删除 `get_sse_service` 导入
- 删除 `_sse_svc()` 辅助函数
- 删除 `GET /tasks/{task_id}/events` 端点（SSE 订阅）
- 删除 `GET /tasks/{task_id}/stream` 端点（历史流回放）
- 更新 `/simulate` 端点，移除 EventBus 调用

#### `backend/app/api/deps.py`

**变更**:
- 删除 `get_sse_service()` 函数

#### `backend/app/builders.py`

**变更**:
- 删除 `EventBus` 和 `SseService` 导入
- 删除 `build_event_bus()` 函数
- 删除 `build_sse_service()` 函数
- 更新 `build_tasks_service()` 移除 `event_bus` 参数

#### `backend/app/bootstrap.py`

**变更**:
- 删除 `build_event_bus` 和 `build_sse_service` 导入
- 删除 event_bus 和 sse_service 的构建代码
- 更新 `build_tasks_service()` 调用移除 `event_bus` 参数
- 从 `BackendState` 移除 `sse` 字段

---

## 前端修改

### 1. 删除的文件

- ❌ `frontend/hooks/useSimpleSSE.ts` - 简化版 SSE Hook

### 2. 修改的文件

#### `frontend/hooks/useTaskStream.ts`

**变更**:
- 完全重写为轮询实现
- 移除 SSE 连接逻辑（fetch + ReadableStream）
- 实现轮询逻辑：
  - 使用 `setInterval` 每 1 秒轮询 `GET /tasks/{task_id}`
  - 比较任务状态变化
  - 状态变化时触发 `onStatusMessage` 和 `onDone`
- 移除 `streamText` 状态（不再需要流式文本）
- 移除 `loadStreamOnce()` 方法
- 保留 `progressLines` 用于显示进度历史
- 保留 `resetStream()` 方法

**关键代码**:
```typescript
const poll = async () => {
  const payload = await fetchJson<TaskResponse>(`/tasks/${taskId}`);
  const task = payload.task;
  const currentStatus = task.status;

  if (currentStatus !== lastStatusRef.current) {
    const message = task.stage_message || task.stage || currentStatus || "处理中";
    onStatusMessage?.(message);
    setProgressLines((prev) => [...prev, message]);
    lastStatusRef.current = currentStatus;

    if (currentStatus === "completed" || currentStatus === "failed" || currentStatus === "cancelled") {
      if (!hasCalledOnDoneRef.current) {
        hasCalledOnDoneRef.current = true;
        await onDone?.();
      }
      // Stop polling
      if (pollingIntervalRef.current) {
        window.clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    }
  }
};

pollingIntervalRef.current = window.setInterval(poll, POLLING_INTERVAL);
```

#### `frontend/components/TaskLiveView.tsx`

**变更**:
- 删除 `LiveStreamRenderer` 导入
- 更新 `useTaskStream` 调用，移除 `streamText` 和 `loadStreamOnce`
- 删除 `<LiveStreamRenderer />` 组件渲染
- 更新 `retryTask()` 移除 `loadStreamOnce()` 调用
- 更新 `useEffect` 移除 `loadStreamOnce` 依赖

#### `frontend/app/debug/page.tsx`

**变更**:
- 删除 `useSimpleSSE` 导入
- 删除所有 SSE 测试相关状态（`sseTaskId`, `sseStatus`, `sseProgressLines` 等）
- 删除所有 SSE 测试函数（`handleSseCreateTask`, `handleSseConnect`, `handleSseSimulate` 等）
- 删除整个 SSE 测试区域 UI

---

## 架构对比

### 原 SSE 架构

```
┌─────────────────┐
│ TasksService    │
│ process_task()  │
└────────┬────────┘
         │
         │ publish()
         ↓
┌─────────────────┐
│ EventBus        │
└────────┬────────┘
         │
         │ 1. 持久化到文件
         │ 2. 推送到 sync_queue
         │ 3. 推送到 async_queue
         ↓
┌─────────────────┐
│ SseService      │
│ subscribe()     │
└────────┬────────┘
         │
         │ yield SSE 格式
         ↓
┌─────────────────┐
│ StreamingResponse│
│ text/event-stream│
└─────────────────┘
         │
         │ HTTP 长连接
         ↓
┌─────────────────┐
│ useTaskStream   │
│ fetch + Reader  │
└─────────────────┘
```

### 新轮询架构

```
┌─────────────────┐
│ TasksService    │
│ process_task()  │
└────────┬────────┘
         │
         │ _write_stream_event()
         ↓
┌─────────────────┐
│ 文件存储        │
│ task_streams/   │
└─────────────────┘

┌─────────────────┐
│ useTaskStream   │
│ setInterval()   │
└────────┬────────┘
         │
         │ 每 1 秒 GET /tasks/{id}
         ↓
┌─────────────────┐
│ TasksService    │
│ get_task()      │
└─────────────────┘
```

---

## 影响分析

### ✅ 优势

1. **简化架构**: 删除 EventBus 和 SseService，减少代码复杂度
2. **更好的兼容性**: HTTP 轮询穿透防火墙/NAT 更容易
3. **资源可控**: 避免 SSE 长连接的并发限制
4. **调试简单**: 标准 HTTP 请求，易于抓包和日志记录
5. **前端简化**: 移除复杂的流式解析逻辑

### ⚠️ 劣势

1. **实时性下降**: 最多 1 秒延迟（轮询间隔）
2. **请求数量增加**: 每秒一个 HTTP 请求
3. **无效轮询**: 任务状态未变化时也会请求

### 📊 性能对比

| 指标 | SSE | 轮询 (1s) |
|-----|-----|----------|
| 实时性 | ~100ms | ~500-1500ms |
| 连接数 | 1 个长连接 | N 个短请求 |
| 服务器压力 | 低（保持连接） | 中（频繁请求） |
| 网络流量 | 低（增量推送） | 中（完整响应） |
| 兼容性 | 中（需要 SSE 支持） | 高（标准 HTTP） |

---

## 验证步骤

### 后端验证

```bash
# 1. 启动后端服务
cd backend
uv run uvicorn app.main:app --reload

# 2. 验证 SSE 端点已删除（应返回 404）
curl http://localhost:8000/tasks/test-123/events

# 3. 创建测试任务
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"image_url": "data:image/png;base64,..."}'

# 4. 验证任务处理正常
curl http://localhost:8000/tasks/{task_id}
```

### 前端验证

```bash
# 1. 启动前端服务
cd frontend
npm run dev

# 2. 打开浏览器开发者工具 - Network 标签

# 3. 创建新任务，观察：
#    - 每 1 秒一个 GET /tasks/{id} 请求
#    - 没有 text/event-stream 连接
#    - 任务状态更新正常
#    - 进度显示正常
#    - 任务完成后轮询停止
```

### 代码检查

```bash
# 1. 确认文件已删除
ls backend/app/services/sse_service.py  # 应不存在
ls backend/app/services/event_bus.py    # 应不存在
ls frontend/hooks/useSimpleSSE.ts       # 应不存在

# 2. 确认没有 SSE 相关引用
grep -r "StreamingResponse" backend/app/
grep -r "text/event-stream" backend/
grep -r "EventSource" frontend/
grep -r "useSimpleSSE" frontend/

# 3. Python 类型检查
cd backend
uv run pyright

# 4. TypeScript 类型检查
cd frontend
npm run lint
```

---

## 后续优化建议

1. **智能轮询**: 根据任务状态动态调整轮询间隔
   - pending: 2 秒
   - processing: 500ms
   - completed: 停止

2. **条件请求**: 使用 `If-Modified-Since` 或 ETag 减少无效响应

3. **WebSocket 备选**: 如需真正实时，可考虑 WebSocket（但复杂度更高）

4. **监控告警**: 添加轮询失败率和延迟监控

---

## 迁移检查清单

- [x] 删除 `backend/app/services/sse_service.py`
- [x] 删除 `backend/app/services/event_bus.py`
- [x] 更新 `backend/app/services/tasks_service.py`
- [x] 更新 `backend/app/api/tasks.py`
- [x] 更新 `backend/app/api/deps.py`
- [x] 更新 `backend/app/builders.py`
- [x] 更新 `backend/app/bootstrap.py`
- [x] 重写 `frontend/hooks/useTaskStream.ts`
- [x] 删除 `frontend/hooks/useSimpleSSE.ts`
- [x] 更新 `frontend/components/TaskLiveView.tsx`
- [x] 更新 `frontend/app/debug/page.tsx`
- [x] 清理未使用的导入
- [x] 验证无编译错误

---

**迁移完成时间**: 2026 年 2 月 23 日  
**迁移状态**: ✅ 完成
