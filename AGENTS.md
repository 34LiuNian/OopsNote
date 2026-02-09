# AI 流程说明

本文描述 OopsNote **当前后端实现**的多阶段 AI 流程（FastAPI + 文件存储），覆盖触发条件、输入输出、编排逻辑、提示词位置、失败与重试、流式回放与可观测点。所有阶段都以 `task_id` 贯穿，便于追踪与回放。

## 总览（实现版）

1. **多题检测器** – 当前已暂时弃用（不参与执行）。
2. **OCR 提取器** – 针对每个裁剪块输出结构化题面（含选项与 `latex_blocks`）。
3. **解题 → 打标** – 对每题逐题解题与打标。
4. **持久化** – 将任务、流式输出、资产与标签库落盘，供前端回放/编辑。

```text
┌──────────────┐    ┌──────────────────────────┐
│ OCR 提取器     │ -> │ 解题 -> 打标             │
└──────────────┘    │ (per-problem sequential) │
  │ task_id     │ problems[]                   │
  └────────────────────────────────────────────┘
          ↓
       File persistence
```

---

## 0. 触发与入口（API 与任务生命周期）

| 项目 | 说明 |
| --- | --- |
| 入口 API | `POST /tasks` 创建任务并启动 pipeline（见 `backend/app/api/tasks.py`） |
| 任务标识 | `task_id` 全链路透传，SSE 与持久化均以该 ID 作为主键 |
| 前端触发 | 上传图片或选择历史任务，前端随后订阅 SSE 流 |
| 并发模型 | 当前为 per-task 顺序执行；多题按 `problems[]` 依次处理 |
| 取消任务 | `POST /tasks/{id}/cancel` 终止正在执行的任务 |

任务生命周期简述：

1. 前端请求创建任务 → 后端初始化任务状态并落盘。
2. 启动 AgentOrchestrator 进入多阶段流程，产出流式日志。
3. SSE 实时推送给前端，同时将日志写入 `task_streams` 供回放。
4. 任务完成或被取消，落盘终态，前端可回放与编辑。

---

## 1. 多题检测器（暂时弃用）

| 项目 | 说明 |
| --- | --- |
| 输入 | 原始图片（Base64/S3 URL）、历史裁剪记录（可为空） |
| 输出 | `detections`: `[{bbox, label}]`，label ∈ {`full`, `partial`, `noise`}；`action`: {`multi`, `single-noise`, `single`} |
| 技术 | 规则实现存在但当前不参与 pipeline 执行 |
| 决策 | 统一使用单题默认区域（full frame），不进行多题检测 |
| 失败策略 | 不适用（已跳过该阶段） |

补充说明：

- 暂时使用单题默认裁剪区域作为 OCR 输入。
- 前端仍可通过编辑题面进行纠错，但不会依赖检测框。

---

## 2. OCR 提取器（题面重建）

| 项目 | 说明 |
| --- | --- |
| 输入 | 裁剪后的图片、`action`、用户设置（语言/风格） |
| 输出 | `problems[]`: `[ { problem_id, problem_text, latex_blocks[], options[], ocr_text } ]` |
| 技术 | 多模态 LLM 输出严格 JSON；失败时可走 retry prompt（见 `backend/app/agents/extractor.py`） |
| 特性 | 题面和选项同时产出 `latex_blocks`（列表），便于前端稳定渲染与复用 |
| 校验 | 解析端使用 `DOMParser` + schema 校验；若失败，回退到 OCR + 文本修补策略 |

### 提示词位置

- `backend/app/agents/prompts/ocr.txt`
- `backend/app/agents/prompts/ocr_retry.txt`

补充说明：

- OCR 目标是“结构化题面”，并区分 `problem_text`、`options` 与 `latex_blocks`。
- `latex_blocks` 为列表，供前端稳定渲染，避免重复解析。
- 若 LLM JSON 格式错误，会使用 retry prompt 强化约束。

---

## 3. 解题器

| 项目 | 说明 |
| --- | --- |
| 输入 | `problem_text`、可选用户喜好（答案格式、解析语言） |
| 输出 | `solutions[]`: `[ { problem_id, answer, explanation, short_answer? } ]` |
| 技术 | 同 `skid-homework` 中的 `SOLVE_SYSTEM_PROMPT`；可迭代加入“若有多种解法需列出”等需求 |
| 扩展 | 支持流式输出：后端会把 LLM delta 通过 SSE 推给前端，同时落盘供刷新回放 |

提示词位置：

- `backend/app/agents/prompts/solver.txt`

补充说明：

- 解题结果在 `solutions[]` 中按 `problem_id` 对齐。
- `short_answer` 可用于前端“答案速览”或列表展示。

---

## 4. 打标器（多维标签）

| 项目 | 说明 |
| --- | --- |
| 输入 | `problem_text + solution`、历史用户标签、错因记录 |
| 输出 | `TaggingResult`：`knowledge_points[] / question_type / skills[] / error_hypothesis[] / recommended_actions[]` |
| 技术 | 纯文本 LLM 即可；可选用分类模型（Zero-shot / Few-shot）或自定义 embedding + KNN |
| 关键逻辑 | 1) 优先从已有 tag 库中选择，避免新造同义标签；2) 若用户在上传时手动选了标签，则必须包含在输出里 |

提示词位置：

- `backend/app/agents/prompts/tagger.txt`

候选标签注入：

- `AgentOrchestrator._build_context` 会从 TagStore 读取候选列表并注入到 tagger prompt

提示词片段：

```text
Return JSON with fields: knowledge_points[], question_type, skills[], error_hypothesis[], recommended_actions[].
Use concise Chinese labels; prefer selecting from the provided candidate lists.
```

备注：`meta_candidates`（题目属性候选）目前仅作为上下文帮助判断题型/来源，不要求写入 `TaggingResult`。

标签候选排序：`GET /tags` 在空 `query` 时会按 `ref_count`（被任务/题目引用次数）降序返回 Top-N，用于前端“未输入也推荐常用标签”。

补充说明：

- Tagger 输出面向后续检索/纠错总结，强制结构化 JSON。
- 若用户上传时指定标签，Tagger 必须包含该标签，避免“覆盖用户意图”。

---

## 5. 持久化（落盘与回放）

| 项目 | 说明 |
| --- | --- |
**后**端当前使用文件存储（便于本地开发与可回放）：

- 任务：`backend/storage/tasks/{task_id}.json`
- 流式输出：`backend/storage/task_streams/{task_id}.txt`（用于刷新后回放 `GET /tasks/{id}/stream`）
- LLM 错误日志：`backend/storage/llm_errors.log`（解析/校验/请求失败细节）
- Trace：`backend/storage/traces/*.jsonl`
- 标签库：`backend/storage/settings/tags.json`、维度样式 `backend/storage/settings/tag_dimensions.json`

写入时机与内容：

- 任务创建：初始化任务元数据并落盘。
- 流式输出：SSE 的 delta 同步写入 `task_streams`。
- 任务完成：写入包含 `problems[] / solutions[] / tags[]` 的终态。
- 任务编辑：前端修改题面或标签会直接更新存储文件。

---

## 6. 编排逻辑与核心类（执行顺序）

| 组件 | 位置 | 作用 |
| --- | --- | --- |
| `AgentOrchestrator` | `backend/app/agents/agent_flow.py` | 统一编排任务流程与上下文注入 |
| `pipeline` | `backend/app/agents/pipeline.py` | 组织多阶段执行与结果聚合 |
| `stages` | `backend/app/agents/stages.py` | Extractor / Solver / Tagger 等阶段实现 |
| `extractor` | `backend/app/agents/extractor.py` | OCR Extractor 的多模态与重试逻辑 |
| `TasksService` | `backend/app/services/tasks_service.py` | 任务执行/队列/SSE/持久化聚合 |

执行顺序（单任务）：

1. OCR Extractor 逐块生成 `problems[]`。
2. Solver 逐题生成 `solutions[]`。
3. Tagger 逐题生成标签结构。
4. 持久化与流式回放。

---

## 7. 流式输出与前端回放（SSE）

| 项目 | 说明 |
| --- | --- |
| SSE 路由 | `GET /tasks/{id}/stream` |
| 内容 | LLM delta、阶段状态、错误信息、进度提示（含 `error_detail` traceback） |
| 回放 | 前端刷新后可读取 `task_streams` 重放已输出内容 |
| 目的 | 低延迟反馈、可视化“解题过程”与日志 |

---

## 8. 失败与重试策略（当前实现）

| 阶段 | 失败模式 | 行为 |
| --- | --- | --- |
| Detector | 已禁用 | 不参与执行 |
| OCR Extractor | JSON 格式错误 | retry prompt + 解析修复 |
| Solver | 模型异常 | 记录错误并进入任务失败态 |
| Tagger | JSON 格式错误 | 以重试或降级策略输出最小结构 |

---

## 人机协作与再触发（实现点）

- Web 支持题库编辑：题号/来源/题干/三类标签（knowledge/error/custom）可手动覆盖并持久化。
- 支持“作废任务”：`POST /tasks/{id}/cancel`，处理中协作式终止。
- 支持“重新 OCR/重新打标”：`POST /tasks/{id}/problems/{pid}/ocr`、`POST /tasks/{id}/problems/{pid}/retag`。

补充说明：

- 前端可在任一阶段后“人工纠正”，并直接写回持久化文件。
- 重新 OCR/重新打标会重用原始资产与任务上下文，减少重复上传。

---

## 可观测与调试

| 指标 | 说明 |
| --- | --- |
| Detection Accuracy | 多题检测的精确/召回；可人工抽样校验裁剪框 |
| OCR Fidelity | 题面 LaTeX 与原题对比的差异率 |
| Solution Correctness | 人类抽检 + 与标准答案比对 |
| Tag Consistency | 相同题目的标签一致性；人工修改次数 |
| Turnaround Time | 单题全链路耗时；为并发/缓存优化提供依据 |

调试入口：

- `GET /health` 查看后端状态
- `GET /models` 查看可用模型（前端设置页会用）
- `GET /settings/agent-models` / `GET /settings/agent-enabled` 查看 agent 配置与启用状态
- `POST /latex/chemfig` chemfig 结构式渲染为 SVG（前端显示用）
- `POST /latex/compile` LaTeX 论文编译接口（见下方附录）

补充建议（可选）：

- 在 `trace` 中记录 `model_name / latency / token_usage`，便于后续性能追踪。
- 给每个阶段增加 `started_at / finished_at` 字段，用于生成流水线甘特图。

---

## 待办扩展

1. **增量学习**：将用户最终确认的标签作为 few-shot 示例缓存给 Agent，减少漂移。
2. **多模态裁剪工具**：在前端加入可视化框选，写回裁剪结果用于再训练。
3. **协同模式**：支持多人共享错题集，基于角色管理编辑/打标权限。
4. **评测框架**：构建自动化 benchmark（真实题图 + 标准答案 + 标签）来回归测试各 Agent。

---

## 附录：LaTeX 论文编译接口

该接口用于将 LaTeX 内容编译为 PDF，供前端“论文版式测试”页面预览。

| 项目 | 说明 |
| --- | --- |
| 路由 | `POST /latex/compile` |
| 输入 | `content`（正文或完整 LaTeX 文档），可选 `title` / `author` |
| 输出 | `application/pdf`（成功）；失败返回结构化 JSON 错误 |
| 引擎 | `xelatex`（可通过 `XELATEX_PATH` 或 PATH 查找） |
| 模板 | 未包含 `\documentclass` 时自动包裹 `ctexart` 模板 |

错误响应示例：

```json
{
  "detail": {
    "message": "LaTeX 编译失败。",
    "log": "...LaTeX log tail...",
    "exit_code": 1
  }
}
```
