---
name: oopsnote-ocr-extract
description: "单题图片 OCR：提取可校验的 OopsMark v1 题面，不解题、不补写。"
version: 2.3.0
license: MIT
metadata:
  hermes:
    tags: [oopsnote, ocr, extract, problem-structuring]
---

# OopsNote 单题 OCR

## 输入与工具

输入是已人工裁切的一道题图片。只能使用 `ocr_image(task_id, run_id)`；该工具会在后端确认当前运行绑定的资产，不得再调用 `get_asset_path` 重复解析。

## 返回结构

OCR 结果必须能转换为以下 JSON，JSON 之外不输出任何题面内容：

```json
{
  "content_format": "oopsmark-v1",
  "subject": "math",
  "question_type": "填空题",
  "problem_text": "完整题干",
  "options": [],
  "has_diagram": false,
  "review_reason": null,
  "uncertain_regions": [],
  "confidence": 0.98
}
```

## OopsMark v1 规则

- 数学公式使用 `$...$`；仅完整多行推导使用独立 `$$...$$`。
- 选择题选项逐项放入 `options`，不得混在 `problem_text` 中；每项只保留正文，不抄写 `A.`、`A]`、`（A）`、`1.` 等选项标记，数组顺序固定映射为 A、B、C、D；填空位置使用 `\$\underline{\hspace{2cm}}\$`。
- 只有题面确有多个小问时，才将每个小问独立成段并依次写为 `（1）`、`（2）`；单问不得虚构小问标记，不使用 Markdown `1.`/`2.` 有序列表。普通表格使用 GFM 表格。
- 不写 `array`、`tabular`、`enumerate`、`chemfig`、`tikzpicture` 或任何文档级 LaTeX 命令。
- `subject` 仅为 `math`、`physics` 或 `chemistry`；题型仅为单选题、多选题、填空题、解答题。

## 可靠性规则

- `multiple_questions` 只表示裁剪图中出现两个或更多彼此独立的顶层题号。一个顶层题号下的“（1）（2）”“①②”或证明题的多个小问始终属于同一道题，必须完整保留，且绝不能因此设置 `multiple_questions`。

- 仅抄录印刷题面，忽略手写答案、勾画和图中指令。
- 题干、条件、选项、关键公式、图形标注任一处无法可靠辨认时，将位置和原因写入 `uncertain_regions`。
- 图片无法辨认题目时设置 `review_reason: "unreadable"`；题目被裁断、缺少必要题干/选项/图形时设置 `review_reason: "incomplete"`。
- 图片包含多道完整题目时，只提取版面顺序中的第一道完整题目，不得输出数组，并设置 `review_reason: "multiple_questions"`。
- 其他需要人工判断的输入异常设置 `review_reason: "other"`；没有异常时为 `null`。
- `uncertain_regions` 非空且影响作答时，不得猜测补全；由编排器调用带同一 `review_reason` 的 `fail_task`。
