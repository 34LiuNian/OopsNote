# SSE 迁移到轮询 - 快速参考

## 核心变更

### 后端
- ❌ 删除：`sse_service.py`, `event_bus.py`
- ✅ 简化：`tasks_service.py` 直接写入流文件
- ❌ 删除端点：`GET /tasks/{id}/events`, `GET /tasks/{id}/stream`

### 前端
- ❌ 删除：`useSimpleSSE.ts`
- ✅ 重写：`useTaskStream.ts` 使用 `setInterval` 轮询
- ⚙️ 轮询间隔：**1000ms (1 秒)**

## 新 API

### useTaskStream Hook

```typescript
const { progressLines, resetStream } = useTaskStream({
  taskId,
  status: data?.task?.status,  // 仅在 "pending" 或 "processing" 时轮询
  onStatusMessage: (msg) => console.log(msg),
  onDone: () => console.log('任务完成'),
});
```

**返回值变化**:
- ❌ 移除：`streamText` (不再有流式文本)
- ❌ 移除：`loadStreamOnce()` (不再需要加载历史流)
- ✅ 保留：`progressLines` (进度消息历史)
- ✅ 保留：`resetStream()` (重置状态)

## 任务状态流转

```
pending → processing → completed/failed/cancelled
   ↑         ↑              ↓
   └─────────┴──────────────┘
           轮询停止
```

## 轮询逻辑

1. **开始条件**: `status === "pending" || status === "processing"`
2. **轮询端点**: `GET /tasks/{task_id}`
3. **状态检测**: 比较 `task.status` 是否变化
4. **停止条件**: 
   - 状态变为 `completed` / `failed` / `cancelled`
   - 组件卸载
   - 状态不再是 active

## 流文件持久化

后端仍会写入流文件（用于调试和审计），但前端不再读取：

```
backend/storage/task_streams/{task_id}.txt
```

格式：
```json
{"event": "progress", "payload": {"stage": "ocr", "message": "识别题目"}, "ts": "2026-02-23T10:00:00Z"}
{"event": "done", "payload": {"status": "completed"}, "ts": "2026-02-23T10:00:10Z"}
```

## 迁移检查清单

- [ ] 后端无 `StreamingResponse` 引用
- [ ] 后端无 `EventBus` / `SseService` 引用
- [ ] 前端无 `EventSource` 引用
- [ ] 前端无 `useSimpleSSE` 引用
- [ ] 前端无 `ReadableStream` 解析逻辑
- [ ] 轮询间隔 = 1000ms
- [ ] 任务完成后轮询停止

## 常见问题

**Q: 为什么选择 1 秒间隔？**  
A: 平衡实时性和服务器负载。500ms 太快，2 秒太慢。

**Q: 轮询会增加服务器压力吗？**  
A: 会，但 HTTP 短请求比 SSE 长连接更容易管理和扩展。

**Q: 实时性下降多少？**  
A: 平均延迟从 ~100ms 增加到 ~500-1500ms（取决于轮询时机）。

**Q: 能否动态调整轮询间隔？**  
A: 可以，未来可根据任务状态智能调整（pending: 2s, processing: 500ms）。

## 调试技巧

### 前端
```javascript
// 在浏览器控制台查看轮询日志
// 开发模式下会输出：
// [useTaskStream] starting polling for task: xxx status: processing
// [useTaskStream] polled task status: completed last status: processing
```

### 后端
```bash
# 查看流文件
tail -f backend/storage/task_streams/{task_id}.txt

# 查看轮询请求日志（uvicorn access log）
# 应该看到每秒一个 GET /tasks/{id} 请求
```

## 性能优化建议

1. **条件请求**: 使用 `If-Modified-Since` 头减少响应大小
2. **指数退避**: 失败时逐步增加轮询间隔
3. **批量轮询**: 多任务时批量请求状态
4. **WebSocket**: 如需真正实时（<100ms），考虑 WebSocket

## 相关文件

- 详细报告：`docs/SSE_TO_POLLING_MIGRATION.md`
- 前端 Hook: `frontend/hooks/useTaskStream.ts`
- 后端服务：`backend/app/services/tasks_service.py`
