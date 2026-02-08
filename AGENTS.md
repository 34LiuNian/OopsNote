# Agent Pipeline Design

本文描述 OopsNote **当前后端实现**的多 Agent/多阶段流程（FastAPI + File storage），覆盖触发条件、输入输出、提示词位置与可观测点。所有阶段都以 `task_id` 贯穿，便于追踪与回放。

## 总览（实现版）

1. **Multi-Problem Detector** – 基于 `notes/mock_problem_count` 生成多题裁剪区域（规则实现）。
2. **OCR Extractor** – 针对每个裁剪块输出结构化题面（含选项与 `latex_blocks`）。
3. **Solver → Tagger** – 对每题逐题解题与打标。
4. **Persistence** – 将任务、流式输出、资产与标签库落盘，供前端回放/编辑。

```text
┌──────────────────────┐    ┌──────────────┐    ┌──────────────────────────┐
│ MultiProblemDetector  │ -> │ OCR Extractor │ -> │ Solver -> Tagger         │
└──────────────────────┘    └──────────────┘    │ (per-problem sequential) │
  │ task_id            │ problems[]                                 │
  └──────────────────────────────────────────────────────────────────┘
          ↓
       File persistence
```

---

## 1. Multi-Problem Detector

| 项目 | 说明 |
| --- | --- |
| 输入 | 原始图片（Base64/S3 URL）、历史裁剪记录（可为空） |
| 输出 | `detections`: `[{bbox, label}]`，label ∈ {`full`, `partial`, `noise`}；`action`: {`multi`, `single-noise`, `single`} |
| 技术 | 规则实现：`backend/app/agents/stages.py` 的 `MultiProblemDetector` 会根据 `notes/mock_problem_count` 生成裁剪区域 |
| 决策 | `multi`/`single-noise` 时返回需要裁剪的坐标；Web 端可直接展示裁剪预览并允许用户调整 |
| 失败策略 | 若检测失败，回退到 `single` 直接进入下一阶段，同时记录告警 |

---

## 2. OCR Extractor（Problem Rebuilder）

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

---

## 3. Solver

| 项目 | 说明 |
| --- | --- |
| 输入 | `problem_text`、可选用户喜好（答案格式、解析语言） |
| 输出 | `solutions[]`: `[ { problem_id, answer, explanation, short_answer? } ]` |
| 技术 | 同 `skid-homework` 中的 `SOLVE_SYSTEM_PROMPT`；可迭代加入“若有多种解法需列出”等需求 |
| 扩展 | 支持流式输出：后端会把 LLM delta 通过 SSE 推给前端，同时落盘供刷新回放 |

提示词位置：

- `backend/app/agents/prompts/solver.txt`

---

## 4. Tagger（多维标签）

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

---

## 5. Persistence（落盘与回放）

| 项目 | 说明 |
| --- | --- |
后端当前使用文件存储（便于本地开发与可回放）：

- 任务：`backend/storage/tasks/{task_id}.json`
- 流式输出：`backend/storage/task_streams/{task_id}.txt`（用于刷新后回放 `GET /tasks/{id}/stream`）
- Trace：`backend/storage/traces/*.jsonl`
- 标签库：`backend/storage/settings/tags.json`、维度样式 `backend/storage/settings/tag_dimensions.json`

---

## 人机协作与再触发（实现点）

- Web 支持题库编辑：题号/来源/题干/三类标签（knowledge/error/custom）可手动覆盖并持久化。
- 支持“作废任务”：`POST /tasks/{id}/cancel`，处理中协作式终止。
- 支持“重新 OCR/重新打标”：`POST /tasks/{id}/problems/{pid}/ocr`、`POST /tasks/{id}/problems/{pid}/retag`。

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
- `POST /latex/compile` LaTeX 论文编译接口（见下方附录）

---

## 待办扩展

1. **增量学习**：将用户最终确认的标签作为 few-shot 示例缓存给 Agent，减少漂移。
2. **多模态裁剪工具**：在前端加入可视化框选，写回 Detector 的输出用于再训练。
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
