# OopsMark v1 内容协议

状态：实施中

版本：`oopsmark-v1`

最近更新：2026-07-26

维护范围：题干、选项、答案、解析，以及网页预览、Obsidian 同步和试卷导出

## 1. 目标与边界

OopsNote 只保存一份可编辑的内容源。网页和试卷不是两份内容，而是同一份
OopsMark 内容的两个渲染目标：

```text
OCR / AI / 手工编辑
        |
        v
   OopsMark v1
     |       |
     v       v
 Web 渲染   LaTeX 导出
```

OopsMark 是受约束的 Markdown 方言，不是任意 Markdown，也不是完整 LaTeX 文档。
禁止在保存内容中加入 `\documentclass`、`\usepackage`、`\begin{document}` 等文档级命令。

以下内容不属于 OopsMark 源数据：

- KaTeX、RDKit.js、TikZJax 或 LaTeX 生成的 HTML/SVG/PDF。
- 针对某个渲染端修改后的第二份题目文本。
- 前端为兼容历史数据临时插入的数学分隔符。

## 2. 基础语法

### 2.1 文本与 Markdown

允许普通段落、标题、强调、列表、行内代码和 GFM 表格。实际存在多个小问时，
每个小问独立成段并依次使用全角 `（1）`、`（2）` 标记；单问不得为了排版虚构小问标记，
也不使用 Markdown `1.`/`2.` 或 LaTeX `enumerate` 表示小问。连续的 Markdown
`1.`/`2.` 输入会在 OopsMark 规范化时转换为全角小问标记。

```markdown
（1）求函数的定义域。
（2）求函数的最大值。
```

选择题的 `options` 只保存按原版面顺序排列的选项正文，不保存 `A.`、`A]`、`（A）`
或 `1.` 等印刷标记。选项字母是数组位置的派生标签，依次为 `A`、`B`、`C`、`D`；
网页、Obsidian 和试卷适配器必须从同一顺序派生标签，不得把标签写回选项正文。
整项为公式时仍须写成 `$...$`；Core 的选项规范化边界会把不含自然语言、且含明确
TeX 命令的整项裸公式补成行内数学，以收敛 OCR/模型输出，混合正文不会被猜测性改写。
试卷适配器对四个选项测量最终 LaTeX 排版宽度：四项均适合四分之一行宽时使用
`1 x 4`，否则在适合二分之一行宽时使用 `2 x 2`，再否则使用 `4 x 1`。布局判断不得
依赖源字符串长度或为特定题目写死列数。

### 2.2 数学

- 行内数学：`$...$`
- 独立数学块：单独一行的 `$$...$$`
- 不把普通行内公式为了视觉效果改成 `$$...$$`
- 不在内容中注入 `\displaystyle`；显示样式由渲染端决定

```markdown
由 $a^2+b^2=c^2$ 可得：

$$
c=\sqrt{a^2+b^2}
$$
```

### 2.3 化学方程式和化学式

化学排版统一使用数学环境中的 `mhchem`：

```markdown
反应方程式为 $\ce{2H2 + O2 -> 2H2O}$。
```

`\chemfig` 不属于 OopsMark v1。分子结构使用 molecule 块。

### 2.4 分子结构

标准块名是 `molecule`，内容为 SMILES 或 MolBlock。`smiles` 仅作为历史兼容别名。

````markdown
```molecule
C1=CC=CC=C1
```
````

- 网页：RDKit.js 渲染 SVG。
- 打印/组卷：资产解析器使用相同源数据生成或读取已缓存 SVG/PDF，再由 LaTeX
  `\includegraphics` 引用。
- SMILES/MolBlock 是源数据；SVG 是可重新生成的派生资产。
- 派生资产应记录源内容哈希和 RDKit 版本，避免错误复用缓存。

### 2.5 TikZ

````markdown
```tikz
\begin{tikzpicture}
  \draw[->] (0,0) -- (2,0);
\end{tikzpicture}
```
````

- 网页：使用受控 LaTeX 渲染器生成并缓存的 SVG；编辑预览也请求同一渲染器。
- 组卷：引用同一次编译派生的 PDF，不在试卷编译阶段再次解释 TikZ 源码。
- 块内不得包含 `\documentclass`、`\usepackage` 或 shell escape 命令。

### 2.5.1 题目旁图

题干可以带任务绑定的结构化旁图。`TaskRecord.diagram_items[]` 是唯一持久化来源，不写入 OopsMark
正文或 `metadata`；`problem_text` 仍是唯一题干文本源。当前创建流程最多产生一个 item，但稳定 item id、
顺序和来源区域合同允许后续版面分析一次写入多个 item，而不改变候选版本模型。

- `DiagramItem.source_asset_path` 指向完整原题图；可选 `source_region` 是归一化 `{x, y, width, height}`，由未来版面分析或保留原图决策写入。
- 位图裁剪在资产层物化为新的 `fallback_image_path`；`source_region` 只保留相对 `source_asset_path` 的来源与编辑坐标。Web 展示投影直接渲染物化资产，不得把来源区域再次应用到 `fallback_image_path`。
- 每个 item 保留 `candidates[]`。候选的 TikZ 源码和源码哈希不可变，`parent_candidate_id` 表示修订关系；选择旧版只更新 `selected_candidate_id`，不删除后续版本。
- TikZ 源码是规范源。一次串行 XeLaTeX 编译从同一 XDV 派生 SVG、PDF、PNG并记录渲染配置版本：SVG用于 Web/Obsidian，PDF用于试卷，PNG只用于模型视觉比较。
- `ready_tikz` 必须选中同时具有 SVG 和 PDF 的候选；`ready_image` 必须指向本地裁剪资产。其他状态不得进入试卷。
- `placement` 是结构化位置合同。缺省为 `{kind: "side", side: "right"}`；低频左侧使用 `side/left`。块级位置使用 `kind: "block"`，其中 `anchor` 为 `after_stem` / `after_options`，`align` 为 `left` / `center` / `right`。右侧空间不足时，渲染端确定性降级为题后同侧对齐，不改写持久化位置。
- TikZ 渲染器显式声明默认字号，并从同源 PDF MediaBox 生成不可变的 `canvas_width_em` / `canvas_height_em`。Web 与试卷分别以最终 CSS / LaTeX 正文字号解释同一 `em` 尺寸，使 TikZ 默认字号自动映射为最终题目字号；源码中的 `\small`、`\large` 和文字节点缩放保留相对差异。
- `scale_adjustment_percent` 范围为 50–200、缺省为 100，表示自动字号基准之上的人工微调，不再相对于题干高度或固定图片栏宽解释。
- 试卷导出另有请求级 `diagram_scale_percent`，范围为 25–200、缺省为 60。它在题目自身
  `scale_adjustment_percent` 之后统一生效，不写回 Task、DiagramItem 或候选。位图以试卷
  正文宽度的 30% 作为无字号校准时的基准宽度，再且只再乘这两个显式比例一次。
- 历史 `scale_percent` 使用旧版题干高度/栏宽语义，不能等价迁移为 `scale_adjustment_percent`；读取旧 item 时统一回到 100 的自动字号基准。只有明确写入的新字段才构成人工微调。
- 位图题图本版本不执行字符识别或字号匹配；`ready_image` 保留为后续独立校准策略的扩展边界。
- `image_tone`: `auto` / `original`。Web 缺省使用 `auto`；打印、试卷和原始资产保留原像素。
- 当前编辑器只提供一个互斥的显示槽位：显示 TikZ 或题图裁剪；隐藏只改变 `DiagramItem.enabled`，不删除来源区域或候选版本。后续多图混排仍以 `diagram_items[]` 为扩展边界，不在当前界面提前引入多图编排。
- 旧的单数 `diagram_*` metadata 只在读取时迁移，此后不得作为第二写入来源。
- 旧 TikZ 候选若缺少标准化尺寸，Web 读取投影只从其 SVG 根节点的物理 `width/height` 一次性推导 `em` 尺寸；该兼容值不回写候选，组卷仍要求用当前渲染器重渲染以取得 PDF MediaBox 指标。
- Web 和试卷优先按结构化位置渲染；侧排空间不足时退化为题干、选项、旁图的题后顺序。Web 题后区域仍不足时保留 TikZ 的自然 `em` 画布并提供横向滚动，不得缩小默认标签；试卷遇到超过可打印宽度的 TikZ 时明确失败，不得静默缩放。Obsidian v1 暂不消费位置合同，仍将题图输出在题目后。

试卷中的 `compact` 答题空间表示不追加垂直留白。单选、填空等非解答题不消费答题空间
设置；只有解答题可按 `standard` / `large` 追加答题区。题目之间不再隐式加入额外间隔，
章节标题自身负责与首题的分隔。

### 2.6 表格

普通表格使用 GFM 表格，单元格可以包含行内数学：

```markdown
| 实验 | 第一次 | 第二次 |
| --- | ---: | ---: |
| 体积/mL | $17.10$ | $18.10$ |
```

网页按 HTML 表格渲染，组卷导出为 `tabularray` 的 `tblr`。`tabular`、`array` 和
`tblr` 原始环境均不写入 OopsMark。需要合并单元格的复杂表格留待后续结构化块版本。

## 3. 渲染责任表

| 内容 | 唯一源数据 | 网页 | 试卷 |
| --- | --- | --- | --- |
| 数学 | `$...$` / `$$...$$` | KaTeX | amsmath |
| 化学式/方程式 | `\ce{...}` | KaTeX mhchem | LaTeX mhchem |
| 分子结构 | SMILES/MolBlock | RDKit.js | RDKit 派生资产 + graphicx |
| TikZ | `tikz` fenced block或题图候选源码 | 缓存 SVG | 同源缓存 PDF + graphicx |
| 普通表格 | GFM table | HTML table | tabularray |
| Mermaid | `mermaid` fenced block | Mermaid | 派生资产 + graphicx |

网页图形必须显式声明主题颜色策略：后端 TikZ SVG 与 RDKit SVG 在共享 SVG
展示边界把纯黑映射为 `currentColor`、纯白映射为当前画布背景，其他颜色保持不变；不得对整张 SVG
使用 `invert()`，以免破坏曲线、曲面和分子高亮的颜色语义。Mermaid 由自身渲染器根据已解析的
`light` / `dark` 主题重新生成 SVG。KaTeX 使用继承的文本颜色，不生成第二份主题内容。

注：网页 KaTeX 渲染行内公式（`$...$`）时，`MarkdownRenderer` 在 `rehype-katex` 前仅转换 OopsMark 的 `math-inline` 节点，注入 `\displaystyle`，使行内公式按展示样式（display style）渲染但保持行内布局。该转换不改写 KaTeX 全局 API，也不影响块公式或其他渲染器。

## 4. 数据模型

每道题必须携带格式版本：

```json
{
  "content_format": "oopsmark-v1",
  "problem_text": "...",
  "options": [],
  "answer": "...",
  "explanation": "..."
}
```

历史 JSON 没有 `content_format` 时按 `legacy-markdown-latex` 读取。旧内容只能经过兼容
渲染或显式迁移，不能在读取时悄悄覆盖原文。

## 5. 验证规则

写入 `oopsmark-v1` 前至少检查：

- 数学分隔符和 fenced block 闭合。
- fence 类型属于允许集合。
- 正文不含 `tabular`、`array`、`enumerate`、`tikzpicture` 等原始环境。
- `\ce` 位于数学环境内。
- `molecule`、`tikz` 块非空。
- 不含文档级命令和危险 TeX 命令。

## 6. 迁移计划

- [x] 定义 OopsMark v1 语法和两端责任。
- [x] Core 增加 `content_format`、解析、验证和 LaTeX 导出接口。
- [x] Web 渲染显式接收格式；旧正则仅用于 legacy 内容。
- [x] OCR、解题和 orchestrator 输出 `content_format: "oopsmark-v1"`。
- [x] 试卷模板补齐 `mhchem`、TikZ，内容可通过 OopsMark 导出器生成 LaTeX 片段。
- [x] 建立数学、化学、表格、TikZ、RDKit 黄金样例测试。
- [x] 为历史数据提供只预览、不覆盖的迁移报告和显式迁移命令。
- [ ] 为 molecule/Mermaid 建立带版本和源哈希的派生资产缓存。

## 7. 变更纪律

后续遇到新的渲染差异时，先更新本协议和黄金样例，再修改适配器。禁止在页面组件、
API 路由或 LaTeX 模板中新增无法由协议解释的字符串替换。

## 8. 当前接入状态

已接通：

- Core 模型格式版本、OopsMark 块解析、统一校验和 LaTeX 片段导出。
- REST 返回字段和 Web 渲染格式透传。
- legacy 内容只读兼容；`oopsmark-v1` 不再执行自动包公式、`tabular -> array`
  或强制 `\displaystyle` 等历史改写。
- AI 最终写入必须显式声明 `content_format: "oopsmark-v1"`。
- 试卷模板具备 `mhchem`、TikZ、tabularray 和 graphicx 依赖。
- `/papers/compile` 和 `/papers/{draft_id}/compile` 通过 Core 的 OopsMark 导出器构建 PDF；路由层不得重新实现字符串替换。

尚未接通：

- molecule/Mermaid 的后端派生资产服务和版本化缓存尚未实现。没有派生资产时，
  LaTeX 导出器会明确报错，不会静默漏图。
- 使用 `scripts/migrate_oopsmark.py` 先生成只读报告；仅传入 `--apply` 时，才会原子地迁移已经通过 v1 校验的记录。无法无损迁移的记录保留为 `legacy-markdown-latex`，并在报告中列出阻塞原因。

当前验证：Python 全量回归、前端类型检查和 lint 是变更前的最低验证面。浏览器 E2E 与凭据化模型行为必须通过实际运行验证，不能从静态检查推断。
