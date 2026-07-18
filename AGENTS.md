# OopsNote — 项目上下文

> 用户：34LiuNian，高中学生（2024级2班）
> 版本：V3 — 分割瓶颈响应（手工分割替代自动分割）

---

## 项目结构

```
oopsnote/
├── core/                  ← 数据层（独立于 UI）
│   ├── models.py          # Problem, Task, Tag, SearchQuery
│   ├── store.py           # JSON 文件存储（每 Task 一个 .json）
│   ├── assets.py          # 图片/PDF 资产落盘
│   ├── tags.py            # 标签库（内置 + 用户，按 ref_count 排序）
│   └── search.py          # 内存多维度搜索（tags/时间/正则）
├── api/main.py            # FastAPI REST 桩（/health, /tasks）
├── cli/main.py            # CLI 调试入口（search/paper/sync，scan 实验性）
├── mcp/                   # MCP Server（→ Hermes）— Phase 2 实现中
├── skills/                # Hermes skill 源文件（同步到 profile）
│   ├── oopsnote-orchestrator/
│   ├── oopsnote-ocr-extract/
│   ├── oopsnote-solve-problem/
│   ├── oopsnote-tag-problem/
│   ├── oopsnote-knowledge/
│   └── oopsnote-segment/    # [闲置] 未来自动分割用
├── obsidian/              # Obsidian .md 同步 — Phase 3
├── paper/templates/       # LaTeX 试卷模板
├── storage/               # 运行时数据
│   ├── {task_id}.json
│   ├── assets/
│   └── settings/
│       ├── tags_builtin.json   ← 18299 条内置标签
│       └── tags_user.json
└── vaults/                # Obsidian vault（各学科 .md 文件）— Phase 3
```

---

## 架构

```
Hermes (随手拍/手动录入)     Web 前端 (主入口+出口)     Obsidian (主出口)
       │ MCP                       │ REST                    ▲ 文件
       ▼                           ▼                        │
  ┌─────────────────────────────────────────────┐            │
  │              OopsNote Core                   │────────────┘
  │  MCP Server · REST API · models · store · tags · search │
  └─────────────────────────────────────────────┘
```

**入口：** 随手拍（单题图片→OCR+解题+打标）和手动录入（纯文本→解题+打标）
**核心瓶颈：** 页面分割不可靠，批量扫描推迟到 Phase 4（Web 端手动框选）
**三条通信路径：** Hermes─MCP→Core, 前端─REST→Core, CLI 直接调 Core

---

## 数据模型

- **Problem**：id, subject, question_type, problem_text (Markdown+LaTeX), options, answer, explanation, knowledge_points, error_hypothesis, source, source_page
- **TaskRecord**：id, subject, status (pending/processing/completed/failed), problems[], asset_path
- **TagItem**：id, dimension (knowledge/error/meta/custom), value, aliases[], subject, ref_count, source

---

## Hermes 集成

- 唯一通道：MCP (stdio JSON-RPC)
- Profile 隔离：`hermes profile create oopsnote`
- Skills 目录：`~/.hermes/profiles/oopsnote/skills/oopsnote-*/SKILL.md`（源文件在仓库 `skills/`）
- Hermes 入口：当前会话接着跑，不 spawn（随手拍/手动录入）
- Web 入口：Core spawn `hermes --profile oopsnote chat -q "..." -s oopsnote-orchestrator`
- 批量扫描未来走 Web 手动分割，Hermes 不直接处理 PDF

---

## 实施 Phase

| Phase | 状态 |
|-------|------|
| 1 — 清理 + 骨架 | ✅ 完成 |
| 2 — Hermes 集成（MCP Server + 随手拍/手动录入） | 🔄 进行中 |
| 3 — Obsidian + 搜索 | ⏳ 待开始 |
| 4 — 前端（含手动批量分割） | ⏳ 待开始 |
| 5 — 知识体系 + 智能出卷 | 📅 远期 |
