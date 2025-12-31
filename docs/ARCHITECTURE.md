# OopsNote 架构与解耦重构指南（现状 -> 目标）

本文基于当前代码实现（2025-12-31）整理 OopsNote 的前后端结构、数据流与主要耦合点，并给出可渐进落地的重构路线。

## 1. 当前系统概览

- 前端：Next.js App Router（`frontend/app/`）+ Primer React 组件（`@primer/react`）
- 后端：FastAPI 单体入口（`backend/app/main.py`）+ agents 流水线（`backend/app/agents/`）+ 本地文件存储（`backend/storage/`）
- 任务链路：Upload/TaskCreate -> Pipeline(Detector/OCR/Solver/Tagger) -> Persistence(Tasks/Streams/Tags)

## 2. 后端模块划分（现状）

- HTTP 入口与路由：`backend/app/main.py`
  - 路由、依赖初始化（repository/storage/AI clients/pipeline）、SSE、任务处理线程、错误处理等都集中在一个文件
- Agents 流水线：
  - `backend/app/agents/pipeline.py`：串联 detector/ocr/solver/tagger/archiver
  - `backend/app/agents/agent_flow.py`：LLMAgent + solver->tagger 编排
  - `backend/app/agents/stages.py`：各 stage 的实现
- 存储：
  - `backend/app/repository.py`：任务记录（内存 / 文件）与归档存根
  - `backend/app/storage.py`：资产文件落盘
  - `backend/app/tags.py`：标签库与维度样式

### 2.1 后端主要耦合点

1) `main.py` 过大：路由 + 业务编排 + 后台线程 + 存储/模型初始化紧耦合，导致：
- 单元测试/注入替换困难
- 新增功能容易引入循环依赖
- 复用 pipeline 的能力弱（只能通过 main 全局变量调用）

2) “依赖”以全局变量形式存在：repository/pipeline/tag_store 等隐式依赖难以替换。

3) 路由层直接操作 repository/pipeline：缺少 service 层边界，难以集中处理幂等、权限、错误映射等。

## 3. 前端模块划分（现状）

- 页面：`frontend/app/*/page.tsx`
- 组件：`frontend/components/*`
- API：`frontend/lib/api.ts` + `frontend/types/api.ts`

### 3.1 前端主要耦合点

1) 页面直接拉 API 并做数据整形：可复用性差、重复 loading/error 状态。
2) 缺少明确的“domain hooks/service”：例如 tasks/tags/settings 的请求逻辑散落。
3) 主题/渲染与业务组件交织（例如 layout 中引入多种 provider）。

## 4. 目标架构（建议）

### 4.1 后端目标边界（从外到内）

- API 层（FastAPI routers）：只做参数校验 + HTTP 错误映射 + 调用 service
- Service 层（业务用例）：任务创建/处理/取消/重试；聚合 repository + pipeline + assets
- Domain/Agents 层：pipeline + agent orchestration（尽量不依赖 FastAPI）
- Infrastructure 层：文件存储、AI clients、settings store

### 4.2 前端目标边界

- `lib/api`：只负责 fetch + baseURL + 错误标准化
- `features/<domain>/`：每个域（tasks/tags/settings）有 hooks + API 封装
- pages 只负责组装 UI，不直接写复杂请求逻辑

## 5. 渐进式重构路线（不大爆炸）

1) 后端：引入 `app.state` 承载依赖 + 抽离路由到 `APIRouter`
- 本次已落地示例：`/health`、`/tags`、`/settings/tag-dimensions` 抽到 `backend/app/api/*`，依赖通过 `app.state.oops` 传递。

2) 后端：抽出 TaskService
- 将 `_process_task/_cancel/_retry/_override` 等业务用例收敛进 service
- 路由层只做：request -> service -> response

3) 后端：把 pipeline 初始化封装为 builder
- 根据 env/config 生成 AI client + orchestrator + deps
- 测试时可注入 stub/fake pipeline

4) 前端：为 tasks/tags/settings 建立 hooks 层
- 统一 loading/error/refresh
- 降低页面组件对 API 细节的感知

5) 最后再做“目录级重排”
- 先稳定边界与依赖注入方式，再移动文件；否则容易引入大量无意义 diff。

## 6. 验收标准（解耦是否成功）

- 后端：路由文件不再 import 具体实现的全局变量（通过 app.state 或 Depends 注入）
- 后端：pipeline 可以在测试中替换（无需改 main.py）
- 前端：page.tsx 中 fetch/状态逻辑显著减少（主要通过 hooks）

