---
name: oopsnote-ocr-extract
description: "OCR 提取 — 从错题图片中提取结构化题面（Markdown + LaTeX）。"
version: 2.0.0
license: MIT
metadata:
  hermes:
    tags: [oopsnote, ocr, extract, problem-structuring]
---

# OopsNote — 错题 OCR 提取

## 功能
从错题图片中提取结构化题面。输入已经是 segment 确认的错题，不用再判断对错。

## 只录错题
- 页面中已经由 segment 筛选出错题
- 你收到的是一道错题的图片
- 正常提取即可，不需要再确认对错

## 输出

```json
{
  "subject": "math",
  "question_type": "解答题",
  "problem_text": "已知 $f(x) = x^2 - 2ax + 3$，$x \\in [1, 3]$，求 $f(x)$ 的最小值。",
  "options": [],
  "has_diagram": false
}
```

## 提取规范

### 学科识别
- **数学**：代数、几何、函数、概率统计、微积分等
- **物理**：力学、电磁学、光学、热学、原子物理等  
- **化学**：化学反应、化学方程式、物质结构、有机化学等

### 格式要求
- **数学公式**：行内 $...$，独行 $$...$$
- **填空题**：空位输出 `\underline{\hspace{2cm}}`
- **选择题**：选项单独列出，不混入题干
- **多小问**：用 `\begin{enumerate} \item[(1)] ... \end{enumerate}`
- **化学式**：可用 `\ce{...}` 或 `\chemfig{...}`

### 必须字段
- `question_type`：单选题 / 多选题 / 填空题 / 解答题
- `subject`：math / physics / chemistry
- `problem_text`：完整题面（Markdown+LaTeX）
- `has_diagram`：是否含图（供后续判断）

## 约束
- 不输出题号、来源（"2024某地一模"之类）
- JSON 之外不输出多余文本
- 图片模糊无法识别 → 返回错误标记
