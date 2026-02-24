# 试卷模板系统说明

本文档描述 OopsNote 的 LaTeX 试卷模板系统架构和使用方法。

## 模板文件结构

```
backend/app/templates/
├── paper.tex              # 主模板文件（文档结构和占位符）
├── section_headers.tex    # 章节标题模板（大题标题）
└── question_formats.tex   # 题目格式模板（小题环境）
```

## 模板文件说明

### 1. paper.tex（主模板）

**作用**：定义试卷的整体结构、宏包引用和占位符

**占位符**：
- `{{TITLE}}` - 试卷标题（如 "2 月 24 日数学作业"）
- `{{SUBTITLE}}` - 试卷副标题/类型（如 "数学试题"）
- `{{SHOW_ANSWERS}}` - 是否显示答案（`true`/`false`）
- `{{SECTION_HEADERS}}` - 章节标题（由 Python 代码动态生成）
- `{{SECTIONS}}` - 题目内容（由 Python 代码动态生成）

**宏包**：
- `exam-zh-*` 系列：试题环境支持
- `ctex`：中文支持
- `amsmath`, `amssymb`：数学公式
- `chemfig`：化学结构式
- 其他：排版和符号支持

### 2. section_headers.tex（章节标题模板）

**作用**：定义各大题章节的标题格式

**支持的题型**：
- `\sectionSingleChoice[题目数量]` - 单选题（8 小题×5 分=40 分）
- `\sectionMultipleChoice[题目数量]` - 多选题（3 小题×6 分=18 分）
- `\sectionFillIn[题目数量]` - 填空题（3 小题×5 分=15 分）
- `\sectionProblem[题目数量]{总分}` - 解答题
- `\sectionOther[题目数量]` - 其它题型

**特性**：
- 自动计算总分（使用 `\the\numexpr`）
- 支持动态题目数量
- 包含标准考试提示语

**示例**：
```latex
\sectionSingleChoice[8]
% 输出：一、选择题：本题共 8 小题，每小题 5 分，共 40 分。在每小题给出的四个选项中，只有一项是符合题目要求的。

\sectionProblem[5]{77}
% 输出：四、解答题：本题共 5 小题，共 77 分。解答应写出文字说明、证明过程或演算步骤。
```

### 3. question_formats.tex（题目格式模板）

**作用**：定义具体题目的 LaTeX 环境

**提供的环境和命令**：

1. **选择题环境**（使用 `exam-zh` 的 `question` + `choices`）
   ```latex
   \begin{question}
       题干内容
       \begin{choices}
           \item 选项 A
           \item 选项 B
           \item 选项 C
           \item 选项 D
       \end{choices}
   \end{question}
   ```

2. **填空题命令**
   ```latex
   \fillinBlank{答案}
   % 展开为：\fillin[width=5em][答案]
   ```

3. **解答题环境**
   - `problemWithPoints{分值}` - 标准间距（80pt）
   - `problemWithLargeSpace{分值}` - 大间距（104pt，用于最后几题）
   
   ```latex
   \begin{problemWithPoints}{15}
       题干内容
   \end{problemWithPoints}
   ```

## Python 代码集成

### 核心函数（`backend/app/api/papers.py`）

1. **模板加载**
   ```python
   _load_paper_template()         # 加载主模板
   _load_section_headers_template()  # 加载章节模板
   _load_question_formats_template() # 加载题目格式模板
   ```

2. **题目构建**
   ```python
   _build_question_block(text, options)     # 构建选择题/填空题
   _build_problem_block(text, points, is_last)  # 构建解答题
   ```

3. **章节渲染**
   ```python
   _get_section_header(question_type, count, total_points)  # 生成章节标题
   _render_section(question_type, blocks, count, total_points)  # 渲染完整章节
   ```

4. **最终组装**
   ```python
   _paper_template(title, subtitle, show_answers, sections)
   ```

### 使用示例

```python
# 1. 准备题目数据
sections = [
    ("单选题", [
        "\\begin{question}...\end{question}",
        "\\begin{question}...\end{question}",
    ]),
    ("解答题", [
        "\\begin{problemWithPoints}{15}...\end{problemWithPoints}",
    ]),
]

# 2. 生成 LaTeX 文档
tex_content = _paper_template(
    title="2 月 24 日数学作业",
    subtitle="数学试题",
    show_answers=False,
    sections=sections,
)

# 3. 编译为 PDF
pdf_bytes = _compile_pdf(tex_content, xelatex_path="/usr/bin/xelatex")
```

## 扩展指南

### 添加新题型

1. 在 `section_headers.tex` 中添加新的章节标题命令：
   ```latex
   \newcommand{\sectionNewType}[1][1]{%
   \vspace{10pt}
   \noindent \textbf{六、新题型：本题共 #1 小题}\hangindent=2em
   }
   ```

2. 在 `question_formats.tex` 中添加新的题目环境：
   ```latex
   \newenvironment{newQuestion}[1]{%
       \begin{question}
   }{%
       \end{question}
   }
   ```

3. 在 `papers.py` 中更新 `_norm_question_type` 和 `_get_section_header` 函数

### 修改分值规则

在 `section_headers.tex` 中修改自动计算公式：

```latex
% 修改每小题分值（当前为 5 分）
\newcommand{\sectionSingleChoice}[1][8]{%
\noindent \textbf{一、选择题：本题共 #1 小题，每小题 5 分，共 \the\numexpr#1*5\relax 分。...}
}
```

### 自定义间距

在 `question_formats.tex` 中修改 `\vspace` 参数：

```latex
\newenvironment{problemWithPoints}[1]{%
    \begin{problem}[points=#1]%
}{%
    \end{problem}%
    \vspace{80pt}%  % 修改这里的数值
}
```

## 注意事项

1. **模板文件路径**：所有模板文件必须位于 `backend/app/templates/` 目录下
2. **编码格式**：所有 `.tex` 文件必须使用 UTF-8 编码
3. **LaTeX 引擎**：使用 `xelatex` 编译（支持中文和 Unicode）
4. **占位符格式**：使用 `{{PLACEHOLDER}}` 格式，Python 代码会用 `str.replace()` 替换
5. **调试模式**：设置 `AI_DEBUG_LLM=true` 可查看生成的 LaTeX 内容

## 故障排查

### 常见问题

1. **模板文件未找到**
   - 检查文件路径是否正确
   - 确认文件编码为 UTF-8

2. **章节标题未显示**
   - 检查 `{{SECTION_HEADERS}}` 占位符是否被正确替换
   - 确认 `_get_section_header` 返回正确的 LaTeX 命令

3. **题目格式错误**
   - 检查 `question_formats.tex` 是否被正确 `\input`
   - 确认 `exam-zh` 宏包已安装

4. **PDF 编译失败**
   - 检查 `xelatex` 是否安装在 PATH 中
   - 查看 `backend/storage/llm_errors.log` 获取详细错误信息

## 参考资源

- [exam-zh 文档](https://ctan.org/pkg/exam-zh)
- [LaTeX 试题排版指南](https://www.latex-project.org/)
- [Overleaf 数学公式手册](https://www.overleaf.com/learn/latex/Mathematical_expressions)
