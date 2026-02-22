# SSE 问题排查与解决方案

## 问题总结

### 现象
- ✅ 后端 SSE 架构完全正常（通过 Python 脚本测试验证）
- ❌ 通过 Next.js 代理 (`/api`) 连接时无法接收事件
- ✅ 直接连接后端 (`http://localhost:8000`) 正常工作

### 根本原因

**Next.js 开发服务器的代理层不适合 SSE 长连接**

1. **流缓冲问题**
   - Next.js Webpack DevServer 会缓冲响应数据
   - SSE 需要实时推送，缓冲会破坏实时性
   - Network 面板显示 `Content-Encoding: gzip` 证明数据被压缩

2. **连接管理问题**
   - SSE 是持久连接（keep-alive）
   - Next.js 代理对长连接支持不完善
   - 可能导致连接建立但数据无法传输

3. **响应头处理**
   - 即使后端设置 `X-Accel-Buffering: no`
   - Next.js 代理层可能忽略或覆盖这些头部

### 验证方法

```bash
# 1. 测试后端 SSE（绕过 Next.js）
curl -N http://localhost:8000/tasks/{task_id}/events

# 2. 测试 Next.js 代理
curl -N http://localhost:3000/api/tasks/{task_id}/events

# 3. 比较两者输出
# 直接连接：实时显示事件
# 通过代理：无输出或延迟很大
```

## 解决方案

### 方案一：开发环境直连后端（已采用）✅

**优点**：
- 简单可靠
- 实时性好
- 无需复杂配置

**缺点**：
- 需要配置 CORS
- 开发/生产环境不一致

**实现**：
```typescript
const isDev = process.env.NODE_ENV === 'development';
const baseUrl = isDev ? 'http://localhost:8000' : '/api';
const eventSource = new EventSource(`${baseUrl}/tasks/${taskId}/events`);
```

### 方案二：使用独立 API 网关（生产环境推荐）

在生产环境中，使用 Nginx 或其他 API 网关：

```nginx
location /api/ {
    proxy_pass http://backend:8000/;
    proxy_buffering off;
    proxy_cache off;
    chunked_transfer_encoding on;
}
```

### 方案三：WebSocket（未来优化）

如果 SSE 问题持续，可以考虑迁移到 WebSocket：

**优点**：
- 双向通信
- 更好的浏览器支持
- 不受代理影响

**缺点**：
- 需要重构后端
- 需要额外的连接管理

## 架构决策

### 当前架构

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Frontend  │ ──────> │   Backend    │         │   Python    │
│ useSimpleSSE │  HTTP   │ FastAPI +    │ <────>  │   Agents    │
│  (EventSource)│  SSE   │ EventBus     │         │  (OCR/Solve)│
└─────────────┘         └──────────────┘         └─────────────┘
      │                        │
      │                        │
      v                        v
┌─────────────┐         ┌──────────────┐
│   Browser   │         │  File Store  │
│  Console    │         │  (Tasks/Tags)│
└─────────────┘         └──────────────┘
```

### 组件职责

1. **useSimpleSSE Hook**
   - 纯粹的 SSE 连接管理
   - 不关心业务逻辑
   - 提供事件订阅接口

2. **EventBus (后端)**
   - 解耦核心逻辑和事件推送
   - 支持多个订阅者
   - 提供 pending events 缓存

3. **SseService (后端)**
   - 专门处理 SSE 连接
   - 格式转换（Python → SSE 协议）
   - 连接生命周期管理

## 测试验证

### 后端测试
```bash
cd backend
uv run python test_http_sse.py
# 结果：✅ 所有事件正常接收
```

### 前端测试
```bash
# 访问测试页面
http://localhost:3000/sse-simple-test

# 控制台应该显示：
# [useSimpleSSE] Using direct connection
# [useSimpleSSE] ✅ Connection opened
# [useSimpleSSE] 📩 Received progress event: ...
```

## 经验教训

1. **SSE 不适合通过 Next.js 代理**
   - 开发环境使用直连
   - 生产环境使用专业 API 网关

2. **解耦是关键**
   - 后端：EventBus 解耦业务和推送
   - 前端：Hook 解耦连接和业务逻辑

3. **测试驱动开发**
   - 先写脚本验证后端
   - 再集成到前端
   - 快速定位问题层次

## 未来优化

1. **添加连接状态监控**
   - 重连机制
   - 连接质量指标

2. **错误恢复**
   - 自动重连
   - 断线续传

3. **性能优化**
   - 事件批处理
   - 节流/防抖

4. **可观测性**
   - 连接指标
   - 事件延迟监控
