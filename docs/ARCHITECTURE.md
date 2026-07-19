# OopsNote — 完整产品设计书

> 用户：34LiuNian，高中学生（2024级2班）
> 版本：V3 — 分割瓶颈响应（手工分割替代自动分割）

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

| 方式 | 场景 | 格式 | 当前状态 |
|------|------|------|:--------:|
| 随手拍 | 单道错题 | 图片 | 当前主入口 ✅ |
| 手动录入 | 纯文本题目 | Markdown | 当前次入口 ✅ |
| 批量扫描（手动分割） | 整页/整张试卷，人工框选错题 | PDF → Web 裁剪 | Phase 4 🚧 |
| 批量扫描（自动分割） | 全自动页面切题 | PDF | 未来预留 🔮 |

**当前聚焦随手拍和手动录入。** 批量分割依赖 Web 端的交互式裁剪工具，全自动分割在有可靠方案前不做。Core 的 pipeline 设计预留接口，未来可无缝接入。`

### 3.2 处理流水线

**两条流水线，共用解题和打标阶段：**

```
随手拍（单题图片）──→ [OCR 提取] ──→ [解题] ──→ [打标] ──→ 存储
手动录入（纯文本） ────→ [解题] ──→ [打标] ──→ 存储
                                         ↑ 共用 skill
                                    delegate_task 并行
```

**手动批量分割**（Phase 4）：

用户 Web 裁剪后的流程同随手拍，只是从一张图变成批量提交：

```
Web 框选 N 道错题 ──→ Core 建 Task ──→ 对每道题跑 随手拍 流程 ──→ 汇总存储
                        ↑ 阶段复用，Core 无改动
```

每步走 Hermes Agent（skill + delegation）：
- **OCR**（只有随手拍/批量流程有）：vision 模型提取题目文本 + LaTeX + 选项，按题目块独立识别学科
- **解题**：solver skill 生成答案 + 解析（Markdown + LaTeX）
- **打标**：tagger skill 标注知识点 + 错因 + 来源

> **注意**：分段（segment）环节已从产品流水线中移除。自动页面分割经验证不可靠（7 种方案失败），当前策略：
> - 随手拍：用户自己拍单题，天然无需分割
> - 手动批量分割（Phase 4）：用户在 Web 端框选错题，AI 不做分割决策
> - 全自动分割：留接口，未来有可靠方案再接入

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
# 题目
已知 $f(x) = x^2 - 2ax + 3$，$x \in [1, 3]$，求 $f(x)$ 的最小值。

# 答案
...

# 解析
...

# 关联
[[二次函数]]  [[最值问题]]  [[分类讨论]]

# 错因
忽略定义域
```

设计要点：
- **文件名即 ID** — 用 `日期-序号.md` 命名，JSON 数据模型中的 uuid 需与此文件名一一对应
- **每个文件夹一个学科** — subject 不需要写在文件里
- **wikilink 即标签** — 不重复维护 frontmatter tags
- **公式优先行内** — 短公式一律用 `$...$`，仅多行方程（方程组、矩阵、长推导）用 `$$...$$`
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

### 3.5 手动批量分割（Phase 4）

批量扫描的核心瓶颈是**页面分割**——从整页中自动切出单道错题。确认七种方案均不可靠后，V3 将分割环节**从 AI 移交给用户**。

**工作流：**

```
用户上传 PDF/整页图片
        ↓
选择「批量分割」模式
        ↓
Web 端展示图片，用户用鼠标框选每道错题区域
   (可选：AI 预分割作为初始框，用户微调)
        ↓
点击「开始处理」
        ↓
Core 创建 Task，对每道框选区域跑完全流水线（OCR→解题→打标）
        ↓
结果汇总展示
```

**设计要点：**
- **模式选择在上传前** — 随手拍 vs 批量分割，决定上传后的交互行为
- **一次性提交** — 用户框完所有题后一键提交，不要求逐题点击
- **AI 预分割可选** — 未来自动分割方案就绪后作为"辅助框选"嵌入，不改变流程
- **Core 无感知** — 发送到 Core 时已经是单题图片，和随手拍别无二致

### 3.6 复习与出卷

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

**当前支持：**
- 随手拍：「拍一下这道物理题」
- 手动录入：「录入一道三角函数题」
- 搜题、查标签等数据操作

**未来支持（批量分割走 Web，Hermes 只做入口之一）：**
- 搜题：「帮我找二次函数相关的错题」
- 出卷：「出 10 道三角函数的练习卷」

```bash
hermes --profile oopsnote
> 拍一下这道物理错题
> 帮我录入：已知 f(x) = x^2...
> 找最值问题相关的题
```

底层调 oopsnote-orchestrator skill → MCP → OopsNote Core。

### 入口二：Web 前端（主入口 + 主出口）

| 页面 | 功能 | 状态 |
|------|------|:----:|
| 首页 | 上传区（拖拽/粘贴）+ 模式选择（随手拍/批量分割）+ 最近任务列表 | Phase 4 |
| 批量分割页 | 图片展示 + 框选工具 + 确认提交 | Phase 4 |
| 题目详情 | 题目查看 + 标签编辑 + 答案/解析展示 | Phase 4 |
| 题库浏览 | 按学科/标签/时间浏览所有题目 | Phase 4 |
| 调试面板 | 空壳即可，相关组件按需加 | Phase 4 |
| 外观设置 | 主题/字体（代办） | 代办 |

**手动批量分割是 Web 端的核心差异化功能，优先于随手拍上传。**

不做：登录、注册、账户、模型配置。

### 入口三：CLI（调试/开发用）

```bash
oopsnote search --tags "二次函数,最值"
oopsnote paper --knowledge "三角函数" --count 10 --output 练习.pdf
oopsnote sync
```

```bash
# ⚠ 实验性 — 保留给未来批量扫描
oopsnote scan ./练透数学选必一.pdf --subject 数学
```

做得简单，调试够用就行，不面向日常使用。scan 命令保留但标记为实验性，等待自动分割方案就绪。

### 出口：Obsidian（主出口）

存储本体之一。直接打开就能看题、搜题、看图谱。

---

## 五、架构设计

```
                        hermes --profile oopsnote
                         "拍一下这道" "录入一道题"
                        (主入口 · 自然语言)
                                 │
                           MCP (stdio)
                                 │
  ┌──────────┐                   ▼
  │   CLI    │──────────┐
  │(调试/开发)│         │
  │ oopsnote │          │
  │ search … │           ▼
  └──────────┘  ┌───────────────────────────────────────┐
                │            OopsNote Core              │
                │            (Python 库)                 │
                │                                       │
                │  ┌────────────┐   ┌──────────────┐    │
                │  │ MCP Server │   │   REST API   │◄───┼──── POST /tasks
                │  │ (→Hermes)  │   │ (→Web 前端)  │───►├──── GET (结果)
                │  └─────┬──────┘   └──────┬───────┘    │
                │        │                 │            │
                │  ┌─────▼─────────────────▼───────┐    │
                │  │          Core 层              │    │
                │  │                               │    │
                │  │  models · store · tags        │    │
                │  │  search · assets              │    │
                │  │  paper  · obsidian/(sync)     │    │
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
                │            Web 前端 ← Phase 4          │
                │       (主入口 + 主出口)                │
                │                                       │
                │ 随手拍：拖拽/粘贴图片 ──POST───► Core  │
                │ 批量分割：PDF → 框选 → 提交 ─► Core   │
                │ 浏览·编辑标签 ◄──GET──── Core         │
                └───────────────────────────────────────┘

图例：
────  MCP (stdio)    ····  REST/Core调用  ────  文件读写
```

### 三条通信路径

```
CLI     ──Python函数调用──►  Core
前端    ──REST───────────►  Core      (入口: POST /tasks)
前端    ◄──REST────────────  Core      (出口: GET 拿结果)
Hermes  ──MCP────────────►  Core
Obsidian◄──文件写入─────────  Core
```

### 两条触发路径

```
路径 A：Hermes 入口（当前会话接着跑）
  Hermes ──MCP──► Core create_problem()/update_task() ──► 同会话加载 skill ──► 干活

路径 B：Web 入口（Core spawn Hermes）
  前端 ──REST──► Core 创建 Task ──► spawn hermes --profile oopsnote ──► 干活
    (Web 上传随手拍 / 提交批量分割 → 统一走此路径)

两条路径用的同一个 oopsnote-orchestrator skill，只是谁起 Hermes 不同。
```

### 入口/出口职责

| | 角色 | 干什么 | 怎么通信 |
|---|---|---|---|
| **Hermes** | 主入口 | 随手拍、手动录题、搜题、出卷（自然语言） | MCP → Core |
| **Web 前端** | 主入口 + 主出口 | 随手拍上传 / 批量分割框选 / 浏览翻看编辑 | REST ↔ Core |
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

### 数据流

**Hermes 入口：当前会话接着跑**

```
你: "拍一下这道物理错题"
    │
Hermes (当前会话):
    ├── MCP: create_task()              ← 建交接单，存图片
    ├── 加载 oopsnote-orchestrator skill
    ├── 模式选择：随手拍（单张图片）或手动录入（纯文本）
    ├── delegation: 并发 OCR+解题+打标  ← 随手拍三条，手动录入两条
    ├── MCP: 逐题写回 + sync_obsidian
    └── "完成：共收录 1 道题"
```

**Web 入口（随手拍 / 批量分割）：Core spawn Hermes**

```
前端 POST /tasks（含图片/框选数据）
    │
Core: 创建 Task ──► 起 MCP Server ──► spawn hermes --profile oopsnote
    │
Hermes (新会话):
    ├── MCP: 读 Task
    ├── 加载 oopsnote-orchestrator
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
|  skills/                            │
│  ├── oopsnote-orchestrator/SKILL.md│  ← 编排：随手拍/手动录入/单题更新
│  ├── oopsnote-ocr-extract/SKILL.md │  ← OCR 提取结构化题面
│  ├── oopsnote-solve-problem/SKILL.md│ ← 解题+解析
│  ├── oopsnote-tag-problem/SKILL.md │  ← 多维度打标
│  ├── oopsnote-knowledge/SKILL.md   │  ← 学科知识引用
│  └── oopsnote-segment/SKILL.md     │  ← [闲置] 未来自动分割实验用
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
> 拍一下这道物理错题
> 录入一道三角函数题
> 找最值问题相关的题

# Web 底层：Core spawn Hermes 新会话
hermes --profile oopsnote chat -q "处理随手拍 task_id=abc123" -s oopsnote-orchestrator

# CLI 调试（实验性）
hermes --profile oopsnote chat -q "处理任务 task_id=abc123" -s oopsnote-orchestrator
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

### Phase 1 — 清理 + 骨架 ✅ 已完成

- [x] 执行删除清单（砍掉 auth/agents/clients/settings）
- [x] 搭建 OopsNote Core 目录结构
- [x] 数据模型设计
- [x] JSON 存储层 + 资产存储
- [x] 标签库管理（18K 内置标签）
- [x] 搜索引擎（core/search.py，内存过滤）
- [x] REST API 桩（`/health`、`/tasks` 空路由）
- [x] CLI 骨架

### Phase 2 — Hermes 集成（当前）

- [ ] 创建 oopsnote profile（`hermes profile create oopsnote`）
- [ ] OopsNote Core MCP Server（FastMCP stdio）
  - create_problem / update_task / get_task
  - list_tags / create_tag
  - get_asset_bytes
  - sync_to_obsidian
- [ ] 配置 SOUL.md + memory
- [ ] 随手拍 pipeline（Hermes 入口）
  - orchestrator skill 编排：OCR → solve → tag
  - leaf skills（ocr-extract / solve-problem / tag-problem）细化 prompt
- [ ] 手动录入 pipeline（Hermes 入口）
  - 无 OCR 阶段，直接 solve → tag
- [ ] `hermes mcp add oopsnote` 连接
- [ ] 端到端：拍照 → OCR → 解题 → 打标 → 存储（Hermes 主入口）

### Phase 3 — Obsidian + 搜索

- [ ] Obsidian .md 格式生成（极简 frontmatter + wikilink）
- [ ] Tag 索引文件自动生成（Core 从数据模型导出）
- [ ] JSON → Obsidian 单向同步
- [ ] 搜索 API 完善，暴露给 MCP + REST
- [ ] oopsnote-knowledge 学科知识填充

### Phase 4 — 前端

- [ ] REST API 补全（对接前端页面需求）
- [ ] 首页 + 模式选择（随手拍 / 批量分割）
- [ ] 批量分割页：图片展示 + 框选工具 + 提交
- [ ] 题目详情 + 标签编辑 + 答案/解析
- [ ] 题库浏览
- [ ] 调试面板（空壳）

### Phase 5 — 知识体系 + 智能（远期）

- [ ] 全自动分割（AI 预分割作为辅助框选）
- [ ] JSON ↔ Obsidian 双向同步 + 冲突合并
- [ ] 通知推送（QQ/Telegram/桌面）
- [ ] AI 薄弱点分析（人工触发 → 自动周期）
- [ ] AI 辅助选题 + LaTeX 自动出卷
- [ ] AI 参与 tag 索引维护
