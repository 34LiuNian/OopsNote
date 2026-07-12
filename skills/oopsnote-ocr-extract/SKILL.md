---
name: oopsnote-ocr-extract
description: "OCR 提取 — 从题目图片中提取结构化题面（Markdown + LaTeX）。"
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [oopsnote, ocr, extract, problem-structuring]
---

# OopsNote — OCR 题目提取

## 功能
从题目图片中提取结构化题面，包含题干文本、LaTeX 公式、选项（如有）。

## 输入
- 题目图片（通过 vision_analyze 查看）
- 学科

## 输出
严格的 JSON 格式：

```json
{
  "subject": "数学",
  "question_type": "解答题",
  "problem_text": "已知 $f(x) = x^2 - 2ax + 3$，$x \\in [1, 3]$，求 $f(x)$ 的最小值。",
  "options": [],
  "has_diagram": false
}
```

## 字段说明
- `question_type`: 单选题 / 多选题 / 填空题 / 解答题
- `problem_text`: Markdown + LaTeX 格式，内嵌公式用 $...$ 或 $$...$$
- `options`: 选择题选项列表，每项为纯文本或 LaTeX
- `has_diagram`: 是否包含几何图形/图表

## 步骤

### 1. 查看题目图片
用 `vision_analyze` 仔细查看题目图片。

### 2. 提取文本
将印刷文字转录为 Markdown 格式：
- 数学公式使用 LaTeX $...$ 内嵌
- 化学式使用原始文本（后续由 chemfig 处理）
- 图表保留描述文字（后期单独渲染）

### 3. 结构化输出
按 JSON schema 组织结果。确保：
- `question_type` 判断准确
- `problem_text` 完整保留题面信息
- `options` 顺序与图片一致

### 4. 保存结果
调用 `mcp__oopsnote__set_problems` 将解析结果写入任务。

## 错误处理
- 图片模糊/无法识别 → 返回 `error: "图片质量不足"`，标记为需人工处理
- JSON 格式错误 → 重试一次，仍失败则标记任务失败
