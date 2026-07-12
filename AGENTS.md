# OopsNote — 项目上下文

> 用户：34LiuNian，高中学生（2024级2班）
> 版本：V2 · 分支 `hermes`

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
├── cli/main.py            # CLI 调试入口（scan/search/paper/sync）
├── mcp/                   # MCP Server（→ Hermes）— Phase 2
├── obsidian/              # Obsidian .md 同步 — Phase 3
├── paper/templates/       # LaTeX 试卷模板
├── storage/               # 运行时数据
│   ├── {task_id}.json
│   ├── assets/
│   └── settings/
│       ├── tags_builtin.json   ← 1510 条内置标签
│       └── tags_user.json
└── vaults/                # Obsidian vault（各学科 .md 文件）— Phase 3
```

---

## 架构

```
Hermes (主入口·自然语言)     Web 前端 (主入口+出口)     Obsidian (主出口)
       │ MCP                       │ REST                    ▲ 文件
       ▼                           ▼                        │
  ┌─────────────────────────────────────────────┐            │
  │              OopsNote Core                   │────────────┘
  │  MCP Server · REST API · models · store · tags · search │
  └─────────────────────────────────────────────┘
```

CLI 直接调 Core 函数，不经过网络。

---

## 数据模型

- **Problem**：id, subject, question_type, problem_text (Markdown+LaTeX), options, answer, explanation, knowledge_points, error_hypothesis, source, source_page
- **TaskRecord**：id, subject, status (pending/processing/completed/failed), problems[], asset_path
- **TagItem**：id, dimension (knowledge/error/meta/custom), value, aliases[], subject, ref_count, source

---

## Hermes 集成

- 唯一通道：MCP (stdio JSON-RPC)
- Profile 隔离：`hermes profile create oopsnote`
- Skills 目录：`~/.hermes/profiles/oopsnote/skills/oopsnote-*/SKILL.md`
- Hermes 入口：当前会话接着跑，不 spawn
- Web/CLI 入口：Core spawn `hermes --profile oopsnote chat -q "..." -s oopsnote-pipeline`

---

## 实施 Phase

| Phase | 状态 |
|-------|------|
| 1 — 清理 + 骨架 | ✅ 完成 |
| 2 — Hermes 集成 | 待开始 |
| 3 — Obsidian + 搜索 | 待开始 |
| 4 — 前端 | 待开始 |
| 5 — 智能 | 待开始 |
