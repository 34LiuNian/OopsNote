# OopsNote 架构与解耦重构指南（现状 -> 目标）

本文基于当前代码实现（2026-02-11）整理 OopsNote 的前后端结构、数据流与主要耦合点，并给出可渐进落地的重构路线。

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
  - `storage/llm_errors.log`：LLM 请求/解析/校验失败明细
  - `backend/app/services/tasks_service.py`：任务处理/队列/SSE/持久化聚合
- 应用装配与可观测：
  - `backend/app/bootstrap.py`：应用装配（依赖构建、路由与启动钩子）
  - `backend/app/builders.py`：依赖构建与装配辅助函数
  - `backend/app/config.py`：环境配置集中读取
  - `backend/app/gateway.py`：网关探测与模型列表访问
  - `backend/app/http_logging.py`：请求日志与访问日志过滤
  - `backend/app/startup_hooks.py`：启动期钩子（网关探测/LLM 日志探针）

### 2.1 后端主要耦合点

1) `bootstrap.py` 仍包含较多装配逻辑：依赖构建与启用策略集中在一个模块，后续可进一步拆分为 builder 与配置层。

2) “依赖”以全局变量形式存在：repository/pipeline/tag_store 等隐式依赖难以替换。

3) 路由层直接操作 repository/pipeline：缺少 service 层边界，难以集中处理幂等、权限、错误映射等。

## 3. 前端模块划分（现状）

- 页面：`frontend/app/*/page.tsx`
- 组件：`frontend/components/*`
- API：`frontend/lib/api.ts` + `frontend/types/api.ts`
- Domain hooks：`frontend/features/tasks`、`frontend/features/tags`、`frontend/features/settings`
- 数学渲染：KaTeX（rehype-katex + mhchem），chemfig 通过后端 `POST /latex/chemfig` 生成 SVG
- 题面渲染复用：`ProblemContent` 统一题干 + 选项渲染；`OptionsList` 负责选项布局
- LaTeX 资产渲染：`useLatexAsset` + `LatexAssetRenderer` 负责请求与缓存（预留 tikz）

### 3.1 前端主要耦合点

1) 题面/LaTeX 资产渲染仍分散在多个组件内，统一层已建立但还有覆盖空间（如 tikz、更多题型卡片）。
2) domain hooks 已建立，但仍可能存在页面级逻辑偏重、可继续下沉的空间。
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
- `components/renderers`：集中 LaTeX/化学结构式/未来 tikz 的渲染与缓存
- `components/problem`：统一题目卡片/题干/选项布局与展示

## 5. 渐进式重构路线（不大爆炸）

1) 后端：引入 `app.state` 承载依赖 + 抽离路由到 `APIRouter`
- 本次已落地示例：`/health`、`/tags`、`/settings/tag-dimensions` 抽到 `backend/app/api/*`，依赖通过 `app.state.oops` 传递。

2) 后端：抽出 TaskService
- 将 `_process_task/_cancel/_retry/_override` 等业务用例收敛进 service
- 路由层只做：request -> service -> response

3) 后端：把 pipeline 初始化封装为 builder
- 根据 env/config 生成 AI client + orchestrator + deps
- 测试时可注入 stub/fake pipeline

4) 前端：为 tasks/tags/settings 建立 hooks 层（已落地）
- 统一 loading/error/refresh
- 降低页面组件对 API 细节的感知

5) 前端：统一题目显示层级
- 将题干、选项、题型/来源展示沉到 `ProblemCard/ProblemContent`
- 列表/详情页只负责数据拼装和交互

6) 最后再做“目录级重排”
- 先稳定边界与依赖注入方式，再移动文件；否则容易引入大量无意义 diff。

## 6. 验收标准（解耦是否成功）

- 后端：路由文件不再 import 具体实现的全局变量（通过 app.state 或 Depends 注入）
- 后端：pipeline 可以在测试中替换（无需改 main.py）
- 前端：page.tsx 中 fetch/状态逻辑显著减少（主要通过 hooks）

