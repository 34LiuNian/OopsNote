# OopsNote 架构基线（高内聚 / 低耦合）

本文定义 OopsNote 当前重构基线（2026-02-14），目标是：

1) 模块职责单一（高内聚）
2) 依赖方向稳定（低耦合）
3) OCR 问题可定位、可复盘、可量化

---

## 1. 分层与依赖方向（后端）

统一采用 4 层：

- API 层（`backend/app/api`）
  - 只负责：参数校验、HTTP 错误映射、调用应用服务。
  - 禁止：直接访问 pipeline 内部依赖对象。

- 应用层（`backend/app/services`）
  - 只负责：任务用例编排（创建、处理、取消、重试、单题重跑）。
  - 只依赖：仓储接口 + pipeline 端口 + 资产/标签服务。

- 领域层（`backend/app/agents`）
  - 只负责：OCR / 解题 / 打标 / 归档的领域流程与规则。
  - 对应用层暴露稳定端口（`AgentPipeline` 公共方法）。

- 基础设施层（`backend/app/repository.py`、`storage.py`、`clients/*`）
  - 只负责：文件持久化、模型请求、日志落盘。

关键约束（强制）：

- `clients/*` 只能提供通用能力（如 `structured_chat` / `structured_chat_with_image`）。
- 禁止在 `clients/*` 中出现业务用例方法（如 `generate_solution`、`classify_problem`）。
- 解题/打标业务逻辑必须放在 Domain 层（`agents/*`）实现。

依赖方向固定为：API -> Application -> Domain -> Infrastructure。

---

## 2. 已落地重构（Phase-1）

### 2.1 独立取消终态

- `TaskStatus` 新增 `cancelled`，不再用 `failed + cancelled stage` 伪装取消。
- 仓储新增 `mark_cancelled`，取消语义在存储层与服务层保持一致。
- SSE `done` 终止条件包含 `cancelled`。

涉及文件：

- `backend/app/models.py`
- `backend/app/repository.py`
- `backend/app/services/tasks_service.py`

### 2.2 服务层与 pipeline 内部解耦

`TasksService` 不再直接访问 `pipeline.deps` / `pipeline.orchestrator`。

`AgentPipeline` 对外新增稳定方法：

- `rerun_ocr_for_problem`
- `retag_problem`
- `solve_and_tag_single`
- `classify_problem`

这样应用层只依赖 pipeline 端口，不依赖其内部实现细节。

涉及文件：

- `backend/app/agents/pipeline.py`
- `backend/app/services/tasks_service.py`

### 2.3 OCR 可观测增强（排错重点）

OCR 增量日志统一为结构化事件：

- 事件结构：`{"type":"ocr_event","v":1,...}`
- 关键字段：`event / region / attempt / model / ms / error / traceback`

此外：

- OCR 输出 schema 临时放宽（`extra=ignore`）
- 增加 `latex_blocks`、`ocr_text` 字段对齐实际消费
- 首次 schema 校验失败时自动触发 retry prompt

涉及文件：

- `backend/app/agents/extractor.py`
- `backend/app/llm_schemas.py`

---

## 3. 运行时契约

### 3.1 任务状态机

状态集合：

- `pending`
- `processing`
- `completed`
- `failed`
- `cancelled`

合法终态：`completed / failed / cancelled`。

### 3.2 任务流事件（SSE）

当前事件类型：

- `progress`：阶段状态
- `llm_snapshot`：历史流快照
- `llm_delta`：增量内容（含 OCR 结构化事件）
- `done`：终态结束
- `error`：流通道错误

约束：

- 业务终态到达后必须发 `done`
- `llm_delta` 允许文本与 `ocr_event` JSON 共存，但推荐前端按 `type=ocr_event` 解析

---

## 4. OCR 排错手册（快速定位病因）

当 OCR 异常时，按以下顺序定位：

1) 看 `llm_delta` 中 `ocr_event.start` 是否出现
   - 没有：通常是路由未进入 OCR 分支或任务提前终止。

2) 看 `ocr_event.request_done` 是否出现
   - 没有：请求阶段失败，查 `error/code=request_failed`。

3) 看是否进入 `schema_invalid_first_pass`
   - 出现：模型有响应，但结构不符合预期，已自动 retry。

4) 看 `schema_invalid_retry` 或 `retry_failed`
   - 出现：重试仍失败，重点检查 prompt、模型能力、输入图像质量。

5) 查落盘日志
   - `backend/storage/llm_errors.log`：错误细节
   - `backend/storage/task_streams/{task_id}.txt`：完整流回放

---

## 5. 代码注释规范（本轮执行）

要求：所有新增函数必须包含注释（docstring），最少说明：

- 职责
- 输入/输出语义
- 失败行为（是否抛错）

本次新增方法均按该规范补齐。

---

## 6. 后续两期计划

### Phase-2：事件协议化

- 将 `llm_delta` 拆为 typed payload，避免文本与 JSON 混流
- 前端 `useTaskStream` 按事件类型渲染 OCR 调试卡片

### Phase-3：装配中心瘦身

- `bootstrap.py` 仅保留 wiring
- 构建逻辑按模块拆分，支持更细粒度测试注入

---

## 7. 架构验收标准

- 模块内：函数围绕单一职责组织，避免“一个服务做全部事情”。
- 模块间：只通过端口交互，不跨层读取内部字段。
- 调试面：任一 OCR 错误都能定位到请求/解析/重试中的具体阶段。

