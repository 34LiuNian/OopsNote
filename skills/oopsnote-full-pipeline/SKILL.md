---
name: oopsnote-full-pipeline
description: "完整流水线 — 编排 segment → OCR → solve → tag，delegation 并行。支持批量扫描、随手拍、单题更新三种模式。"
version: 1.3.0
license: MIT
metadata:
  hermes:
    tags: [oopsnote, pipeline, orchestration, end-to-end]
---

# OopsNote — 完整流水线

## 三种模式

| 模式 | 触发词 | task_id | 说明 |
|------|--------|---------|------|
| **批量扫描** | "扫一下" / "处理这本" | 可选（无则自动创建） | 分割所有题 → delegation 并发 |
| **随手拍** | "拍一下" / "记这道" | 可选 | 同样走 delegation，最后只输出一道 |
| **单题更新** | "重做第3题" / "3,5,7重新OCR" | 必填 | 更新已有 task 中指定题号的题目 |

### 自动判别

- 多页 PDF / "这本" / "扫描" → **批量扫描**
- 单张图片 / "拍" / 无明显批量意图 → **随手拍**
- "重做" / "重新" + 题号 → **单题更新**

---

## 模式一：批量扫描

### 流程

1. 没有 task_id → `mcp__oopsnote__create_task` 创建
2. 标记 processing → `vision_analyze` 查看页面
3. 按 oopsnote-segment 分割所有题目
4. 每道题一个 `delegate_task`，并行 OCR+solve+tag
5. 汇总 → `mcp__oopsnote__set_problems` → completed → sync

### 报告
`完成，共 N 道题。`

---

## 模式二：随手拍

### 流程

**与批量扫描完全相同的 agent 流水线**，只是最后只有一道题：

1. 没有 task_id → `mcp__oopsnote__create_task` 创建
2. 标记 processing → `vision_analyze` 查看
3. 分割识别（页面中只识别出一道题）
4. 走 delegation：OCR → solve → tag（单题也并行跑这三个阶段，保持一致性）
5. 写入 → completed → sync

### 报告
`已记录：{知识点}。{错因提示}。`

---

## 模式三：单题更新

### 触发
指定一个或多个题号重新处理："重做第3题"、"3,5,7重新打标"

### 输入
- `task_id`: 必填
- `problem_indices`: 要更新的题号列表（如 [2, 4, 5]）
- `action`: "ocr" | "solve" | "tag" — 从哪个阶段开始重跑

### 流程

1. `mcp__oopsnote__get_task` 获取数据
2. 对每个 `problem_index` 走 delegation（可并发）：
   - `ocr`: 重新 OCR → solve → tag
   - `solve`: 保留 OCR 题面 → 重新 solve → tag
   - `tag`: 保留 OCR 题面 + 答案 → 只重新 tag
3. `mcp__oopsnote__set_problems` 更新 → sync

### 报告
`第 3,5,7 题已更新。`

---

## 错误处理（通用）
- 任何阶段失败 → `mark_task_status` 标记 failed + 错误信息
- 批量/单题更新：单题失败跳过，继续处理其他题
- 随手拍：失败直接报告原因
