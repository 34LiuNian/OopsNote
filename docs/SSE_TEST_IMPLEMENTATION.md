# SSE 进度条测试完整实现文档

本文档整理了 OopsNote 项目中 SSE（Server-Sent Events）进度条测试功能的全部相关代码，包括前端测试页面、后端服务和 API 路由。

---

## 目录

1. [前端测试页面](#1-前端测试页面)
2. [后端任务服务](#2-后端任务服务)
3. [后端 API 路由](#3-后端 API 路由)
4. [核心组件](#4-核心组件)
5. [测试流程](#5-测试流程)

---

## 1. 前端测试页面

**文件位置**: `frontend/app/sse-test/page.tsx`

### 1.1 页面功能

- 创建测试任务（不调用真实处理）
- 连接 SSE 实时事件流
- 模拟处理（发送虚假进度事件）
- 真实处理（调用实际 AI 流程）
- 进度条可视化展示
- 进度日志实时显示

### 1.2 核心状态

```typescript
const [taskId, setTaskId] = useState<string>("");           // 任务 ID
const [isConnected, setIsConnected] = useState(false);       // SSE 连接状态
const [statusMessage, setStatusMessage] = useState<string>(""); // 当前状态消息
const [progressLines, setProgressLines] = useState<string[]>([]); // 进度日志
const [streamText, setStreamText] = useState<string>("");    // 原始流文本
```

### 1.3 主要函数

#### `connectSSE()` - 连接 SSE 事件流

```typescript
const connectSSE = useCallback(async () => {
  if (!taskId) return;
  
  // 清理之前的连接
  if (abortControllerRef.current) {
    abortControllerRef.current.abort();
    abortControllerRef.current = null;
  }

  const abortController = new AbortController();
  abortControllerRef.current = abortController;

  try {
    const response = await fetch(`/api/tasks/${taskId}/events`, {
      method: "GET",
      signal: abortController.signal,
    });
    
    if (!response.ok) {
      throw new Error(`SSE 连接失败：${response.status}`);
    }
    
    setIsConnected(true);
    setStatusMessage("已连接到 SSE");
    
    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error("ReadableStream 不可用");
    }
    
    const decoder = new TextDecoder();
    let buffer = "";
    let currentEvent = "";
    
    const readStream = async () => {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        
        for (const line of lines) {
          const trimmedLine = line.trim();
          if (!trimmedLine) continue;
          
          if (trimmedLine.startsWith("event:")) {
            currentEvent = trimmedLine.slice(6).trim();
            continue;
          }
          
          if (trimmedLine.startsWith("data:")) {
            const data = trimmedLine.slice(5).trim();
            
            if (currentEvent === "progress") {
              const fullPayload = JSON.parse(data);
              const payload = fullPayload.payload || fullPayload;
              const message = 
                payload.message || 
                payload.stage || 
                payload.status || 
                "处理中";
              
              setStatusMessage(message);
              setProgressLines((prev) => {
                if (prev.length > 0 && prev[prev.length - 1] === message) return prev;
                return [...prev, message];
              });
            } else if (currentEvent === "done") {
              setIsConnected(false);
              setStatusMessage("任务完成");
            }
            
            currentEvent = "";
          }
        }
      }
    };
    
    readStream();
  } catch (error) {
    if (error instanceof Error && error.name !== "AbortError") {
      console.error('[SSE Test] connection error:', error);
      setStatusMessage("无法连接到 SSE: " + error.message);
      setIsConnected(false);
    }
  }
}, [taskId]);
```

#### `generateTestTask()` - 创建测试任务

```typescript
const generateTestTask = useCallback(async () => {
  try {
    const response = await fetch('/api/tasks?auto_process=false', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        image_url: 'https://via.placeholder.com/800x600.png?text=Test+Task',
        subject: 'math',
      }),
    });
    
    if (response.ok) {
      const data = await response.json();
      const newTaskId = data.task?.id || data.id;
      setTaskId(newTaskId);
      setStatusMessage('任务已创建，请点击"连接 SSE"');
      return newTaskId;
    } else {
      const errorData = await response.json();
      setStatusMessage('创建任务失败：' + (errorData.detail || '未知错误'));
    }
  } catch (error) {
    setStatusMessage('创建任务异常：' + error.message);
  }
  return null;
}, []);
```

#### `simulateProcessing()` - 模拟处理（测试 SSE）

```typescript
const simulateProcessing = useCallback(async () => {
  if (!taskId) return;
  
  try {
    const response = await fetch(`/api/tasks/${taskId}/simulate?background=true`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });
    
    if (response.ok) {
      setStatusMessage('模拟处理已启动，请连接 SSE 查看进度');
    } else {
      const errorData = await response.json();
      setStatusMessage(`启动模拟失败：${response.status} - ${errorData.detail}`);
    }
  } catch (error) {
    setStatusMessage(`启动模拟错误：${error.message}`);
  }
}, [taskId]);
```

#### `createAndConnect()` - 一键测试（核心功能）

```typescript
const createAndConnect = useCallback(async () => {
  // Step 1: 创建任务
  setStatusMessage('正在创建任务...');
  const newTaskId = await generateTestTask();
  if (!newTaskId) return;
  
  // Step 2: 等待任务初始化
  await new Promise(resolve => setTimeout(resolve, 500));
  
  // Step 3: 连接 SSE
  setStatusMessage('正在连接 SSE...');
  await connectSSE();
  
  // Step 4: 等待连接建立
  await new Promise(resolve => setTimeout(resolve, 500));
  
  // Step 5: 启动模拟处理
  if (isConnected) {
    setStatusMessage('开始模拟处理...');
    await simulateProcessing();
  }
}, [generateTestTask, connectSSE, isConnected, simulateProcessing]);
```

### 1.4 UI 布局

```tsx
return (
  <Box sx={{ p: 4 }}>
    {/* 标题区 */}
    <Box sx={{ mb: 4 }}>
      <Text sx={{ fontSize: 0, color: "fg.muted", textTransform: "uppercase" }}>SSE Test</Text>
      <Heading as="h2" sx={{ fontSize: 3 }}>SSE 进度条测试</Heading>
      <Text sx={{ color: "fg.muted", mt: 1 }}>
        测试后端 SSE 事件推送是否正常
      </Text>
    </Box>

    {/* 控制区 */}
    <Box sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2, mb: 3 }}>
      <Box sx={{ display: "flex", gap: 2, mb: 3, flexWrap: "wrap" }}>
        <Button onClick={createAndConnect} disabled={isConnected || !!taskId} variant="primary">
          一键测试（创建→连接→模拟）
        </Button>
        <Button onClick={generateTestTask} disabled={isConnected || !!taskId}>
          创建测试任务
        </Button>
        <Button onClick={connectSSE} disabled={isConnected || !taskId}>
          连接 SSE
        </Button>
        <Button onClick={simulateProcessing} disabled={!taskId || isConnected}>
          模拟处理（测试 SSE）
        </Button>
        <Button onClick={startProcessing} disabled={!taskId || isConnected}>
          真实处理
        </Button>
        <Button onClick={disconnectSSE} disabled={!isConnected} variant="danger">
          断开连接
        </Button>
        <Button 
          onClick={() => { setTaskId(''); setStatusMessage('已重置'); }} 
          disabled={isConnected || !taskId} 
          variant="danger"
        >
          重置
        </Button>
      </Box>

      {/* 状态显示 */}
      <Box sx={{ mb: 2 }}>
        <Text sx={{ fontSize: 0, fontWeight: "bold" }}>当前任务 ID:</Text>
        <Text sx={{ fontSize: 0, fontFamily: "mono", ml: 2 }}>{taskId || "无任务"}</Text>
      </Box>

      <Box sx={{ mb: 2 }}>
        <Text sx={{ fontSize: 0, fontWeight: "bold" }}>连接状态:</Text>
        <Text sx={{ fontSize: 0, ml: 2, color: isConnected ? "success.fg" : "danger.fg" }}>
          {isConnected ? "已连接" : "未连接"}
        </Text>
      </Box>

      <Box sx={{ mb: 2 }}>
        <Text sx={{ fontSize: 0, fontWeight: "bold" }}>当前状态:</Text>
        <Text sx={{ fontSize: 0, ml: 2 }}>{statusMessage || "无"}</Text>
      </Box>
    </Box>

    {/* 进度条 */}
    <Box sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2, mb: 3 }}>
      <Heading as="h3" sx={{ fontSize: 2, mb: 2 }}>进度条</Heading>
      <TaskProgressBar
        progressState={progressState}
        latestLine={progressLines.length > 0 ? progressLines[progressLines.length - 1] : statusMessage}
        statusMessage={statusMessage}
      />
    </Box>

    {/* 进度日志 */}
    <Box sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2 }}>
      <Heading as="h3" sx={{ fontSize: 2, mb: 2 }}>进度日志</Heading>
      <Box 
        sx={{ 
          fontFamily: "mono", 
          fontSize: 0,
          // ... 日志显示样式
        }}
      >
        {progressLines.map((line, index) => (
          <Box key={index}>{line}</Box>
        ))}
      </Box>
    </Box>
  </Box>
);
```

---

## 2. 后端任务服务

**文件位置**: `backend/app/services/tasks_service.py`

### 2.1 核心字段

```python
class TasksService:
    def __init__(self, *, repository, pipeline, asset_store, tag_store) -> None:
        self.repository = repository
        self.pipeline = pipeline
        self.asset_store = asset_store
        self.tag_store = tag_store

        # 线程安全锁
        self._task_cancel_lock = threading.Lock()
        self._task_cancelled: set[str] = set()
        self._processing_lock = threading.Lock()
        self._processing_inflight: set[str] = set()

        # SSE 事件队列
        self._event_queues: dict[str, list[asyncio.Queue]] = {}
        self._event_lock = threading.Lock()
        
        # 存储主事件循环（用于跨线程通信）
        self._event_loop: asyncio.AbstractEventLoop | None = None
        try:
            self._event_loop = asyncio.get_running_loop()
            logger.info("TasksService: captured main event loop")
        except RuntimeError:
            logger.warning("TasksService: no running event loop at initialization")

        # 流式输出目录
        self.streams_dir = (
            Path(repository.base_dir).parent / "task_streams"
            if hasattr(repository, "base_dir") and repository.base_dir
            else Path("storage/task_streams")
        )
        self.streams_dir.mkdir(parents=True, exist_ok=True)
```

### 2.2 SSE 核心方法

#### `subscribe_task_events()` - 订阅实时事件

```python
async def subscribe_task_events(self, task_id: str):
    """Subscribe to real-time events for a task."""
    logger.info("SSE: client subscribing to task_id=%s", task_id)
    queue = asyncio.Queue()
    
    # 注册队列
    with self._event_lock:
        if task_id not in self._event_queues:
            self._event_queues[task_id] = []
        self._event_queues[task_id].append(queue)
        logger.info("SSE: registered queue for task_id=%s, total queues=%d", 
                   task_id, len(self._event_queues[task_id]))

    try:
        logger.info("SSE: starting to wait for events for task_id=%s", task_id)
        while True:
            logger.debug("SSE: waiting for next event for task_id=%s", task_id)
            data = await queue.get()
            logger.info("SSE: received event for task_id=%s: %s", 
                       task_id, data.get('event') if isinstance(data, dict) else 'unknown')
            
            if data is None:  # Sentinel for end of stream
                logger.info("SSE: received sentinel for task_id=%s", task_id)
                break
            
            logger.debug("SSE: yielding event %s for task_id=%s", data['event'], task_id)
            yield f"event: {data['event']}\ndata: {json.dumps(data['payload'], ensure_ascii=False)}\n\n"
    finally:
        # 清理队列
        with self._event_lock:
            if task_id in self._event_queues:
                self._event_queues[task_id].remove(queue)
                if not self._event_queues[task_id]:
                    del self._event_queues[task_id]
                logger.info("SSE: client unsubscribed from task_id=%s, remaining queues=%d", 
                           task_id, len(self._event_queues.get(task_id, [])))
```

#### `_broadcast()` - 广播事件（跨线程通信）

```python
def _broadcast(self, task_id: str, event: str, payload: dict):
    """Broadcast an event to all subscribers and write to disk."""
    # 构建事件数据
    data = {"event": event, "payload": payload, "ts": datetime.now(timezone.utc).isoformat()}
    
    # 1. 写入磁盘（用于回放）
    path = self.streams_dir / f"{task_id}.txt"
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
        logger.debug("Broadcast: wrote to disk %s", task_id)
    except Exception as e:
        logger.warning("Failed to write to stream file %s: %s", task_id, e)

    # 2. 通知活跃监听器
    with self._event_lock:
        queues = self._event_queues.get(task_id, [])
        logger.debug("Broadcast: task_id=%s has %d active listeners", task_id, len(queues))
        
        if not queues:
            logger.debug("Broadcast: no active listeners for task_id=%s", task_id)
            return
        
        # 使用存储的事件循环进行跨线程通信
        if self._event_loop is None:
            logger.warning("Broadcast: no event loop available")
            return
        
        for q in queues:
            try:
                # 从同步线程安全地推送到 asyncio 队列
                future = asyncio.run_coroutine_threadsafe(q.put(data), self._event_loop)
                future.add_done_callback(lambda f: None)  # 抑制异常
                logger.debug("Broadcast: sent event %s to queue", event)
            except Exception as e:
                logger.debug("Failed to broadcast event to queue: %s", e)
```

#### `_finish_broadcast()` - 结束广播

```python
def _finish_broadcast(self, task_id: str):
    """Send sentinel to all subscribers to close connection."""
    with self._event_lock:
        queues = self._event_queues.get(task_id, [])
        for q in queues:
            try:
                q.get_loop().call_soon_threadsafe(q.put_nowait, None)
            except Exception:
                pass
```

#### `get_task_stream()` - 读取历史流

```python
def get_task_stream(self, task_id: str, max_chars: int = 200000) -> str:
    """Read historical stream from disk."""
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
```

---

## 3. 后端 API 路由

**文件位置**: `backend/app/api/tasks.py`

### 3.1 SSE 事件订阅端点

```python
@router.get("/tasks/{task_id}/events")
async def task_events(request: Request, task_id: str):
    """Subscribe to real-time task events (SSE)."""
    origin = request.headers.get("origin", "")
    
    return StreamingResponse(
        _svc(request).subscribe_task_events(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            # CORS headers for SSE
            "Access-Control-Allow-Origin": origin if origin else "*",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Headers": "Content-Type, Accept",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
        },
    )
```

### 3.2 历史流读取端点

```python
@router.get("/tasks/{task_id}/stream")
def get_task_stream(request: Request, task_id: str, max_chars: int = 200000):
    """Fetch historical stream content."""
    text = _svc(request).get_task_stream(task_id, max_chars=max_chars)
    return {"task_id": task_id, "text": text}
```

### 3.3 模拟处理端点（测试专用）

```python
@router.post("/tasks/{task_id}/simulate", response_model=TaskResponse)
def simulate_processing(
    request: Request, task_id: str, background: bool = True
) -> TaskResponse:
    """Simulate task processing with fake progress events for testing."""
    import threading
    import time
    
    svc = _svc(request)
    
    # 标记为处理中
    svc.repository.patch_task(task_id, stage="simulating", stage_message="模拟处理中")
    
    def send_fake_progress():
        """Send fake progress events to test SSE."""
        stages = [
            ("starting", "开始处理"),
            ("detector", "多题检测中..."),
            ("detector", "检测到 3 个题目区域"),
            ("ocr", "OCR 提取中..."),
            ("ocr", "题目 1: 提取完成"),
            ("ocr", "题目 2: 提取完成"),
            ("ocr", "题目 3: 提取完成"),
            ("solver", "解题中..."),
            ("solver", "题目 1: 解题完成"),
            ("solver", "题目 2: 解题完成"),
            ("solver", "题目 3: 解题完成"),
            ("tagger", "打标中..."),
            ("tagger", "题目 1: 打标完成"),
            ("tagger", "题目 2: 打标完成"),
            ("tagger", "题目 3: 打标完成"),
            ("done", "处理完成"),
        ]
        
        for stage, message in stages:
            time.sleep(0.5)  # 模拟工作
            svc._broadcast(task_id, "progress", {"stage": stage, "message": message})
        
        time.sleep(0.3)
        svc._finish_broadcast(task_id)
        
        # 标记为完成
        svc.repository.patch_task(task_id, stage="done", stage_message="模拟完成")
    
    if background:
        # 在后台线程中运行
        thread = threading.Thread(
            target=send_fake_progress,
            name=f"simulate-{task_id}",
            daemon=True,
        )
        thread.start()
    else:
        send_fake_progress()
    
    return TaskResponse(task=svc.get_task(task_id))
```

---

## 4. 核心组件

### 4.1 TaskProgressBar 组件

**文件位置**: `frontend/components/task/TaskProgressBar.tsx`

```typescript
// 使用 useTaskProgress hook 管理进度状态
const progressState = useTaskProgress({
  status: isConnected ? "processing" : "pending",
  streamProgress: progressLines,
  statusMessage,
});

// 渲染进度条
<TaskProgressBar
  progressState={progressState}
  latestLine={progressLines.length > 0 ? progressLines[progressLines.length - 1] : statusMessage}
  statusMessage={statusMessage}
/>
```

### 4.2 useTaskProgress Hook

**文件位置**: `frontend/hooks/useTaskProgress.ts`

```typescript
// 管理进度状态的 hook
export function useTaskProgress({
  status,
  streamProgress,
  statusMessage,
}: {
  status: TaskStatus;
  streamProgress: string[];
  statusMessage: string;
}) {
  // ... 进度状态管理逻辑
}
```

---

## 5. 测试流程

### 5.1 完整测试步骤

1. **访问测试页面**
   - URL: `http://localhost:3000/sse-test`

2. **点击"一键测试"按钮**
   - 自动执行：创建任务 → 连接 SSE → 启动模拟

3. **观察进度变化**
   - 状态栏显示当前阶段
   - 进度条显示整体进度
   - 日志区显示详细步骤

### 5.2 预期输出

```
开始处理
多题检测中...
检测到 3 个题目区域
OCR 提取中...
题目 1: 提取完成
题目 2: 提取完成
题目 3: 提取完成
解题中...
题目 1: 解题完成
题目 2: 解题完成
题目 3: 解题完成
打标中...
题目 1: 打标完成
题目 2: 打标完成
题目 3: 打标完成
处理完成
```

### 5.3 后端日志验证

```
TasksService: captured main event loop
SSE: client subscribing to task_id=xxx
SSE: registered queue for task_id=xxx, total queues=1
Broadcast: wrote to disk xxx
Broadcast: task_id=xxx has 1 active listeners
Broadcast: sent event progress to queue
SSE: received event for task_id=xxx: progress
```

### 5.4 文件存储验证

**流式输出文件**: `backend/storage/task_streams/{task_id}.txt`

```json
{"event": "progress", "payload": {"stage": "starting", "message": "开始处理"}, "ts": "2026-02-21T09:10:34.876828+00:00"}
{"event": "progress", "payload": {"stage": "detector", "message": "多题检测中..."}, "ts": "2026-02-21T09:10:35.387802+00:00"}
...
```

---

## 6. 关键技术点

### 6.1 跨线程通信

**问题**: Python 3.12+ 中，工作线程无法通过 `asyncio.get_event_loop()` 获取事件循环

**解决方案**: 在 `TasksService.__init__()` 中捕获主事件循环

```python
# 初始化时捕获
self._event_loop = asyncio.get_running_loop()

# 工作线程中使用
asyncio.run_coroutine_threadsafe(q.put(data), self._event_loop)
```

### 6.2 SSE 流式解析

**前端解析逻辑**:
```typescript
// 1. 按行分割
buffer += decoder.decode(value, { stream: true });
const lines = buffer.split("\n");
buffer = lines.pop() || "";

// 2. 解析 event 和 data
if (line.startsWith("event:")) {
  currentEvent = line.slice(6).trim();
}
if (line.startsWith("data:")) {
  const data = line.slice(5).trim();
  const payload = JSON.parse(data);
}
```

**后端输出格式**:
```
event: progress
data: {"event": "progress", "payload": {"stage": "ocr", "message": "提取完成"}, "ts": "..."}

event: done
data: {"event": "done", "payload": {}, "ts": "..."}
```

### 6.3 实时 vs 历史

- **实时事件**: 通过 `subscribe_task_events()` 推送给已连接的客户端
- **历史回放**: 通过 `get_task_stream()` 读取磁盘文件

**重要**: SSE 是实时流，不会自动回放历史事件。必须先连接 SSE，再触发事件。

---

## 7. 故障排查

### 7.1 常见问题

#### 问题 1: 前端收不到事件

**检查点**:
1. 后端日志是否有 `Broadcast: sent event`
2. 后端日志是否有 `no active listeners`（表示连接前就触发了事件）
3. 前端控制台是否有 `[SSE Test] progress event:` 日志

**解决方案**: 使用"一键测试"按钮，确保先连接 SSE 再触发事件

#### 问题 2: CORS 错误

**检查点**:
1. 浏览器控制台是否有 CORS 相关错误
2. 后端是否配置了 `CORSMiddleware`
3. SSE 端点是否返回了 CORS headers

**解决方案**: 检查 `backend/app/main.py` 的 CORS 配置和 `tasks.py` 的 SSE 端点 headers

#### 问题 3: 事件循环不可用

**检查点**:
1. 后端启动日志是否有 `TasksService: captured main event loop`
2. 如果显示 `no running event loop at initialization`，说明初始化时机不对

**解决方案**: 确保 `TasksService` 在 async 上下文中初始化

### 7.2 调试技巧

1. **查看后端日志**: 关注 `Broadcast:` 和 `SSE:` 前缀的日志
2. **查看前端控制台**: 关注 `[SSE Test]` 前缀的日志
3. **查看流式文件**: `backend/storage/task_streams/{task_id}.txt`
4. **使用网络面板**: 检查 `/api/tasks/{id}/events` 请求状态

---

## 8. 扩展建议

### 8.1 功能增强

1. **历史回放**: 连接 SSE 时先读取历史文件，再订阅实时事件
2. **多任务支持**: 允许同时测试多个任务的 SSE
3. **事件过滤**: 支持按阶段或关键词过滤事件
4. **导出日志**: 将进度日志导出为文本文件

### 8.2 性能优化

1. **事件节流**: 高频事件进行节流处理
2. **内存管理**: 限制 `_event_queues` 的大小
3. **文件轮转**: 流式文件过大时进行轮转

### 8.3 测试增强

1. **自动化测试**: 编写 E2E 测试验证 SSE 流程
2. **压力测试**: 模拟大量并发连接
3. **错误注入**: 测试网络中断、后端重启等场景

---

## 9. 相关文件清单

### 前端文件
- `frontend/app/sse-test/page.tsx` - SSE 测试页面
- `frontend/components/task/TaskProgressBar.tsx` - 进度条组件
- `frontend/hooks/useTaskProgress.ts` - 进度状态 hook
- `frontend/next.config.mjs` - Next.js 配置（API 代理）

### 后端文件
- `backend/app/services/tasks_service.py` - 任务服务（SSE 核心）
- `backend/app/api/tasks.py` - API 路由（包含 simulate 端点）
- `backend/app/api/deps.py` - 依赖注入
- `backend/app/main.py` - FastAPI 应用（CORS 配置）

### 存储文件
- `backend/storage/task_streams/{task_id}.txt` - 流式输出文件
- `backend/storage/tasks/{task_id}.json` - 任务元数据

---

## 10. 总结

SSE 进度条测试功能完整实现了前后端的实时通信，关键技术点包括：

1. **跨线程事件推送**: 使用 `asyncio.run_coroutine_threadsafe` 实现线程安全的事件推送
2. **实时流式传输**: 使用 SSE 协议实现服务器到客户端的单向实时通信
3. **双重存储**: 同时支持实时推送和历史回放
4. **一键测试**: 简化测试流程，避免时序问题

该功能不仅用于测试，也为真实 AI 处理流程提供了进度反馈的基础架构。
