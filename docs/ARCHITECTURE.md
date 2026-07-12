# OopsNote — 完整产品设计书

> 用户：34LiuNian，高中学生（2024级2班）
> 版本：V2 重构

---

## 一、产品定位

### 一句话

**把做过的作业/试卷/随手题目扔进去，AI 自动把错题变成可检索、可关联、可出卷的个人知识库。**

### 核心价值

| 没有 OopsNote | 有 OopsNote |
|---|---|
| 手抄/剪贴错题，分类靠感觉 | 扫描即入库，AI 自动分类打标，高度可整理可维护 |
| 翻作业本找同类题 | 搜一个知识点，关联题全出来 |
| 不知道自己薄弱在哪 | Obsidian 图谱 + AI 分析一目了然 |
| 复习没针对性 | AI 辅助按知识点抽题，LaTeX 自动出卷 |

---

## 二、设计哲学

### 原则一：工具在需要时出现，不需要时消失

打开 Obsidian 就能看错题。图谱就在那里。AI 不刷存在感——它在你拍照时默默工作，在你复习时安静呈现。没有推送轰炸，没有"今日推荐"弹窗。

AI 薄弱点分析暂由人工触发（自动分析的"度"和"量"很难把握——频繁到什么程度算薄弱？多少题算多？这类产品哲学问题另文讨论，开发时不做参考）。

### 原则二：数据是你的，格式是开放的

- JSON 文件 + Obsidian .md 双向同步，可互相转换，冲突合并（代办）
- 可选云端同步（GitHub 私有仓库 / 云盘）
- 换工具？数据带走。毕业了？题库还在。

数据模型设计需充分考虑：独立于存储格式、方便迁移、便于版本管理。

### 原则三：学生管决策，机器管执行

AI 不做"你应该复习这个"的决定。AI 做的是：
- 把题目切出来、解出来、标好签
- 把知识点关联画出来
- 把统计数据摆出来

**你**决定今天练什么，**你**判断哪些标签不对。AI 是副驾驶，不是自动驾驶。

---

## 三、产品逻辑

### 3.1 输入

| 方式 | 场景 | 格式 |
|------|------|------|
| 批量扫描 | 整本作业/整张试卷 | PDF（默认） |
| 随手拍 | 单道错题 | 图片 |
| 手动录入 | 纯文本题目 | Markdown |

### 3.2 处理流水线

```
输入 → [页面分割 + AI审计] → [并发 OCR] → [并发解题] → [并发打标] → 存储
```

每一步都走 Hermes Agent（skill + delegation）：
- **分割**：segmenter skill 识别题目区域，AI 审计复核
- **OCR**：vision 模型提取题目文本 + LaTeX + 选项，按题目块独立识别学科
- **解题**：solver skill 生成答案 + 解析（Markdown + LaTeX）
- **打标**：tagger skill 标注知识点 + 错因 + 来源

### 3.3 存储

**双写，单向同步**（代办：双向同步 + 冲突合并）：

| 存储层 | 格式 | 用途 |
|--------|------|------|
| OopsNote Core | JSON + 资产文件 | 系统主存储，API 数据源 |
| Obsidian Vault | .md 文件 | 浏览、搜索、图谱、编辑 |

Obsidian vault 直接放在项目目录下，和 JSON 一起做 Git 版本管理 → GitHub 云端同步。

### 3.4 Obsidian 组织方式

**不按章节分文件夹。** 用 wikilink + tag 索引替代层级目录。

```
oopsnote/
├── storage/              ← JSON + 资产（系统主存储）
├── vaults/               ← Obsidian vault（放在项目目录下）
│   ├── maths/
│   │   ├── problems/
│   │   │   ├── 2024-10-15-001.md
│   │   │   └── ...
│   │   ├── indexes/
│   │   │   ├── 二次函数.md
│   │   │   └── ...
│   │   └── reviews/
│   └── physics/
│   └── chemical/
```

每道题目 .md 的结构（极简 frontmatter，wikilink 即标签）：

```markdown
---
source: "2024-10 月考"
date: 2024-10-15
---

# 关联
[[二次函数]]  [[最值问题]]  [[分类讨论]]

# 题目
已知 $f(x) = x^2 - 2ax + 3$，$x \in [1, 3]$，求 $f(x)$ 的最小值。

# 答案
...

# 解析
...

# 错因
忽略定义域
```

设计要点：
- **文件名即 ID** — 用 `日期-序号.md` 命名，JSON 数据模型中的 uuid 需与此文件名一一对应
- **每个文件夹一个学科** — subject 不需要写在文件里
- **wikilink 即标签** — 不重复维护 frontmatter tags
- **source 可追溯** — 链接到原始 PDF 及页码
- **错因放正文** — 不是元数据，是你要看的内容

Tag 索引文件（OopsNote Core 从数据模型自动生成；AI 参与维护是远期代办）：

`二次函数.md`（文件名即 tag）：
```markdown
---
type: index
ref_count: 12
aliases: ["二次函数与方程", "一元二次函数"]
---

# 二次函数

> 共 12 道相关题目

## 相关题目
- [[2024-10-15-001]]
- [[2024-09-20-003]]
```

优势：
- 一道题可以属于多个知识点（wikilink 天然多对多）
- 图谱自动呈现知识点关联
- 不需要纠结"放哪个文件夹"
- GitHub 可直接做文件管理 + 版本控制

### 3.5 复习与出卷

薄弱点分析暂由人工触发（自动分析的阈值和频率太难把握）。

**按需出卷：**
```bash
oopsnote paper --knowledge "三角函数,最值" --count 10 --output 练习.pdf
```
AI 辅助从题库中按知识点选题 → LaTeX 编译 → PDF。

---

## 四、产品形态

三个入口，两个出口。CLI 是调试/临时工具，不面向日常使用。

### 入口一：Hermes（主入口）

```
hermes --profile oopsnote

> 扫一下这本练透数学选必一
> 帮我找二次函数相关的错题
> 出 10 道三角函数的练习卷
> 上周错了哪些题
```

用自然语言操作。底层调 oopsnote-pipeline skill → MCP → OopsNote Core。

### 入口二：Web 前端（主入口 + 主出口）

| 页面 | 功能 |
|------|------|
| 首页 | 上传区（拖拽/粘贴）+ 最近任务列表 |
| 题目详情 | 题目查看 + 标签编辑 + 答案/解析展示 |
| 题库浏览 | 按学科/标签/时间浏览所有题目 |
| 调试面板 | 空壳即可，相关组件按需加 |
| 外观设置 | 主题/字体（代办） |

不做：登录、注册、账户、模型配置。

### 入口三：CLI（调试/开发用）

```bash
oopsnote scan ./练透数学选必一.pdf --subject 数学
oopsnote search --tags "二次函数,最值"
oopsnote paper --knowledge "三角函数" --count 10 --output 练习.pdf
oopsnote sync
```

做得简单，调试够用就行，不面向日常使用。

### 出口：Obsidian（主出口）

存储本体之一。直接打开就能看题、搜题、看图谱。

---

## 五、架构设计

```
                        hermes --profile oopsnote
                        "扫一下这本" "找二次函数"
                        (主入口 · 自然语言)
                                 │
                           MCP (stdio)
                                 │
  ┌──────────┐                   ▼
  │   CLI    │──────────┐
  │(调试/开发)│         │
  │ oopsnote │          │
  │ scan …  │           ▼
  └──────────┘  ┌───────────────────────────────────────┐
                │            OopsNote Core              │
                │            (Python 库)                 │
                │                                       │
                │  ┌────────────┐   ┌──────────────┐    │
                │  │ MCP Server │   │   REST API   │◄───┼──── POST /tasks (触发扫描)
                │  │ (→Hermes)  │   │ (→Web 前端)  │───►├──── GET (返回结果)
                │  └─────┬──────┘   └──────┬───────┘    │
                │        │                 │            │
                │  ┌─────▼─────────────────▼───────┐    │
                │  │          Core 层              │    │
                │  │                               │    │
                │  │  models · store · tags        │    │
                │  │  search · obsidian/sync       │    │
                │  │  paper  · assets              │    │
                │  └─────────────┬─────────────────┘    │
                │                │                      │
                │  ┌─────────────▼─────────────────┐    │
                │  │          存  储  层            │    │
                │  │                               │    │
                │  │  JSON · 资产文件 · Vault      │────┼──► Obsidian
                │  └───────────────────────────────┘    │    (主出口)
                └───────────────────────────────────────┘    图谱·浏览

                                                               Git → GitHub

                ┌───────────────────────────────────────┐
                │            Web 前端                    │
                │       (主入口 + 主出口)                │
                │                                       │
                │  入口：拖拽/粘贴/拍照 PDF ──POST──────► Core
                │  出口：浏览·翻看·编辑标签 ◄──GET──── Core
                └───────────────────────────────────────┘

图例：
────  MCP (stdio)    ····  REST    ────  Python函数调用    ────  文件读写
```

### 三条通信路径

```
CLI     ──Python函数调用──►  Core
前端    ──REST───────────►  Core      (入口: POST /tasks)
前端    ◄──REST────────────  Core      (出口: GET 拿结果)
Hermes  ──MCP────────────►  Core
Obsidian◄──文件写入─────────  Core
```

### 两条触发路径（汇合于 Core）

```
路径 A：Hermes 入口（当前会话接着跑）
  Hermes ──MCP──► Core create_task() ──► 同会话加载 skill ──► 干活

路径 B：Web / CLI 入口（Core spawn Hermes）
  前端/CLI ──► Core 创建 Task ──► spawn hermes --profile oopsnote ──► 干活

两条路径用的同一个 full-pipeline skill，只是谁起 Hermes 不同。
```

### 入口/出口职责

| | 角色 | 干什么 | 怎么通信 |
|---|---|---|---|
| **Hermes** | 主入口 | 扫描、搜题、出卷（自然语言） | MCP → Core |
| **Web 前端** | 主入口 + 主出口 | 上传触发 / 浏览翻看编辑 | REST ↔ Core |
| **Obsidian** | 主出口 | 知识图谱、深度浏览、阅读 | ← Core 写文件 |
| **CLI** | 调试/开发 | 快速验证、脚本自动化 | Python → Core |

### 各层职责

#### OopsNote Core（Python 库）

```
oopsnote/
├── core/
│   ├── models.py        # Problem, Task, Tag 数据模型
│   ├── store.py         # JSON 文件存储
│   ├── assets.py        # PDF/图片资产管理
│   ├── tags.py          # 标签库管理
│   └── search.py        # 多维度搜索（HERMES + 前端都用）
├── obsidian/
│   ├── writer.py        # .md 文件生成
│   ├── indexer.py       # tag 索引文件自动生成
│   ├── syncer.py        # JSON ↔ Obsidian 双向同步+冲突合并
│   └── templates/       # 笔记模板
├── paper/
│   ├── compiler.py      # LaTeX 试卷编译
│   └── selector.py      # AI 辅助选题
├── mcp/
│   └── server.py        # MCP Server（Hermes 调用入口）
├── api/
│   ├── tasks.py         # REST 路由（前端用）
│   └── health.py
└── cli/
    ├── main.py          # CLI 入口（调试/临时，做得简单）
```

说明：tags 和 search 放在 core 层而非 api 层，因为 MCP（Hermes）和 REST（前端）都需要它们。

#### Hermes Agent（AI 引擎）

```
~/.hermes/profiles/oopsnote/skills/
├── oopsnote-segment/
│   └── SKILL.md                   # 页面分割 + AI 审计
├── oopsnote-ocr-extract/
│   ├── SKILL.md                   # OCR 提取结构化题目
│   └── references/
│       └── chemfig.md             # 化学结构式知识
├── oopsnote-solve-problem/
│   └── SKILL.md                   # 单题解题
├── oopsnote-tag-problem/
│   └── SKILL.md                   # 单题打标
├── oopsnote-full-pipeline/
│   └── SKILL.md                   # 编排：加载上面四个，delegation 并行
├── oopsnote-knowledge/
│   ├── SKILL.md                   # 被其他 skill 引用
│   └── references/
│       ├── subjects.md            # 学科知识体系
│       └── exam-format.md         # 答题规范
└── oopsnote-weakness/             # （远期）
    └── SKILL.md                   # 薄弱点分析
```

每个 skill 一个标准目录（`SKILL.md` + 可选 `references/`）。

#### 数据流

**Hermes 入口：当前会话接着跑**

```
你: "扫一下这本练透数学"
    │
Hermes (当前会话):
    ├── MCP: create_task()              ← 建交接单
    ├── 加载 oopsnote-full-pipeline skill
    ├── vision_analyze → OCR            ← 同一个会话继续
    ├── delegation: 并发解题/打标
    ├── MCP: 逐题写回 + sync_obsidian
    └── "完成，共 12 道题"
```

**Web 入口：Core spawn Hermes**

```
前端 POST /tasks
    │
Core: 创建 Task ──► 起 MCP Server ──► spawn hermes --profile oopsnote
    │
Hermes (新会话):
    ├── MCP: 读 Task
    ├── 加载 oopsnote-full-pipeline
    ├── 干活 → 写回
    └── 退出
    │
Core: 更新 Task 状态 ──► 前端轮询拿到结果
```

**CLI 入口：同 Web，只是 Core 在本进程内**

---

## 六、Hermes 集成方案

### 唯一通道：MCP

```
┌─────────────────────────────────────┐
│          OopsNote Core              │
│                                     │
│  FastMCP Server (stdio)             │
│  ├── create_problem(...)            │
│  ├── list_tags(...)                 │
│  ├── get_asset(...)                 │
│  ├── sync_to_obsidian(...)          │
│  └── ...                            │
└──────────┬──────────────────────────┘
           │ JSON-RPC over stdio
           │
┌──────────▼──────────────────────────┐
│        Hermes Agent                 │
│        (profile: oopsnote)          │
│                                     │
│  skills/                            │
│  ├── oopsnote-segment/SKILL.md      │
│  ├── oopsnote-ocr-extract/SKILL.md  │
│  ├── oopsnote-solve-problem/SKILL.md│
│  ├── oopsnote-tag-problem/SKILL.md  │
│  ├── oopsnote-full-pipeline/SKILL.md│
│  └── oopsnote-knowledge/SKILL.md    │
│                                     │
│  memory/   ← 标签偏好、prompt 经验  │
│  SOUL.md   ← "错题处理专用 AI"      │
└─────────────────────────────────────┘
```

### Profile 隔离

```bash
# 一次创建，永久隔离
hermes profile create oopsnote
```

| | 默认 profile | oopsnote profile |
|---|---|---|
| SOUL.md | 34LiuNian 的助手 | 错题处理专用 AI |
| memory | 你是谁、喜欢啥 | 标签偏好、prompt 经验 |
| skills | 各种日常 skill | 只有 oopsnote-* |
| sessions | 日常聊天 | 每次 scan 的任务日志 |

### 调用方式

```bash
# Hermes 入口（主）：当前会话直接干活，不需要 spawn
hermes --profile oopsnote
> 扫一下这本练透数学选必一

# Web / CLI 底层：Core spawn Hermes 新会话
hermes --profile oopsnote chat -q "处理任务 task_id=abc123" -s oopsnote-pipeline
```

### MCP 工具

OopsNote Core 暴露给 Hermes 的工具。纯数据操作，跟 AI 无关。

```python
# 标签
list_tags(dimension, query, limit) -> list[TagItem]
create_tag(dimension, value, aliases) -> TagItem

# 题目/任务
create_problem(problem_text, subject, ...) -> str    # 返回 problem_id
get_task(task_id) -> TaskRecord
update_task(task_id, **fields)

# 资产
get_asset_bytes(asset_id) -> bytes

# Obsidian
sync_to_obsidian(task_id)

# 搜索
search_problems(tags, subject, since, ...) -> list[ProblemSummary]
```

### 隔离保证

| 维度 | OopsNote 不知道 | Hermes 不知道 |
|------|:--:|:--:|
| 模型选什么、API key | ✅ | |
| OCR prompt 怎么迭代 | ✅ | |
| memory 怎么存、标签怎么积累 | ✅ | |
| 数据文件存哪个路径 | | ✅ |
| LaTeX 编译器在哪 | | ✅ |
| Obsidian vault 在哪 | | ✅ |

Hermes 升级、换模型、改 prompt —— OopsNote 不受影响。
OopsNote 改存储格式、换 LaTeX 引擎 —— Hermes skill 不受影响。

---

## 七、删除清单

| 模块 | 文件 | 原因 |
|------|------|------|
| 认证 | `app/auth/`, `app/api/auth.py` | 本地工具不需要 |
| 用户管理 | `app/services/user_store.py`, `app/api/users.py`, `app/api/account.py` | 单人 |
| AI 客户端 | `app/clients/` | Hermes 替代 |
| AI Agent | `app/agents/` | Hermes skill 替代 |
| Agent 设置 | `app/agent_settings.py`, `app/services/agent_settings.py`, `app/api/agent_settings.py` | Hermes 管理 |
| 模型服务 | `app/services/models_service.py`, `app/api/models.py` | 同上 |
| Pipeline 编排 | `app/services/tasks_service.py`（AI 部分） | Hermes 编排 |
| 调试端点 | `app/api/debug_tasks.py` | 产品不需要 |
| 网关 | `app/gateway.py` | 不需要 |
| 前端登录 | `frontend/app/login/` | 去掉认证 |
| 前端账户 | `frontend/app/account/` | 同上 |
| 前端用户 | `frontend/app/users/` | 同上 |
| 前端设置(Agent) | `frontend/app/settings/`, `frontend/features/settings/` | Hermes 管 |
| SSE | （没实现过） | 不需要 |

## 八、保留清单

| 模块 | 用途 |
|------|------|
| `app/models/`（精简） | 数据模型 |
| `app/storage.py` | 资产文件 |
| `app/repository.py`（精简） | JSON 存储 |
| `app/tags.py` | 标签库 |
| `app/api/tasks.py`（精简） | 前端 REST API |
| `app/api/latex.py` | chemfig + LaTeX 编译 |
| `app/api/papers.py` | LaTeX 试卷生成 |
| `app/api/health.py` | 健康检查 |
| 前端 Markdown/KaTeX | 题目展示 |
| 前端 ProblemCard/Edit | 题目编辑 |
| 前端 TagPicker/Chip | 标签交互 |
| 前端 UploadForm | 上传 |
| 前端 Library 页面 | 题库浏览 |

---

## 九、实施计划

### Phase 1 — 清理 + 骨架（立即）

- [ ] 执行删除清单（砍掉 auth/agents/clients/settings）
- [ ] 搭建 OopsNote Core 目录结构
- [ ] 数据模型设计（充分考虑格式独立性 + 可迁移性 + JSON uuid ↔ 文件名映射）
- [ ] JSON 存储层 + 资产存储
- [ ] 标签库管理
- [ ] 搜索引擎（core/search.py，内存过滤即可）
- [ ] REST API 桩（`/health`、`/tasks` 空路由，前端后续接）
- [ ] CLI 骨架（调试用，简单够用即可）

### Phase 2 — Hermes 集成

- [ ] 创建 oopsnote profile（`hermes profile create oopsnote`）
- [ ] 创建 oopsnote skills（segment / ocr / solve / tag / pipeline）
- [ ] 配置 SOUL.md + memory
- [ ] segmenter 加强 + AI 审计
- [ ] OopsNote Core MCP Server（stdio JSON-RPC）
- [ ] `hermes mcp add oopsnote` 连接
- [ ] 端到端：PDF → 完整结果（Hermes 主入口测试）

### Phase 3 — Obsidian + 搜索

- [ ] Obsidian .md 格式生成（极简 frontmatter + wikilink）
- [ ] Tag 索引文件自动生成（Core 从数据模型导出）
- [ ] JSON → Obsidian 单向同步
- [ ] 搜索 API 完善（tags + 时间 + 正则，暴露给 MCP + REST）
- [ ] 云端同步（GitHub 私有仓库，含 Obsidian vault）

### Phase 4 — 前端

- [ ] REST API 补全（对接前端页面需求）
- [ ] 首页 + 详情 + 题库 + 调试面板（空壳）+ 外观设置（代办）

### Phase 5 — 知识体系 + 智能（持续 / 远期）

- [ ] 学科应试知识体系整理（数学/物理/化学）
- [ ] JSON ↔ Obsidian 双向同步 + 冲突合并
- [ ] 通知推送（QQ/Telegram/桌面）
- [ ] AI 薄弱点分析（人工触发 → 自动周期）
- [ ] AI 辅助选题 + LaTeX 自动出卷
- [ ] AI 参与 tag 索引维护
