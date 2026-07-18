---
name: oopsnote-orchestrator
description: "流水线编排器 — 加载 leaf skills，dispatch 子 agent，汇总结果。"
version: 2.0.0
license: MIT
metadata:
  hermes:
    tags: [oopsnote, orchestrator, dispatch, pipeline]
---

# OopsNote — 编排器

## 职责
编排流程，不写详细 prompt。OCR / 解题 / 打标的详细指令在各自的 skill 里。

## 三种模式

| 模式 | 触发词 | 流程 |
|------|--------|------|
| **批量扫描** | "扫一下" / "处理这本" | 逐页找错题 → 只 OCR 错题 → delegation 并行 solve+tag → 汇总 |
| **随手拍** | "拍一下" / 单张图 | 直接 delegation（一道题）→ 写入 |
| **单题更新** | "重做第3,5题" | 取已有 task → 指定题号重跑指定阶段 |

---

## 模式一：批量扫描

**核心思路：一页一页找错题，找到就派活，不等。**

```
父 agent:
  for each page:
    vision_analyze + oopsnote-segment → 找出本页所有错题
    if 本页没错题: 跳过
    for each 错题:
      delegate_task(goal="OCR+solve+tag 这道错题",
        skills=["oopsnote-ocr-extract", "oopsnote-solve-problem", "oopsnote-tag-problem"])
    # 不等子 agent，继续下一页
  # 最后等所有子 agent 完成，汇总写入
```

### 步骤

1. 没有 task_id → `mcp__oopsnote__create_task`
2. `mcp__oopsnote__mark_task_status` → processing
3. **逐页循环**：
   - vision_analyze + oopsnote-segment 分割本页题目
   - 每道题 `delegate_task`（自动 background，不阻塞）
   - 记录分派数，继续下一页
4. 等待所有子 agent 完成（汇总结果）
5. `mcp__oopsnote__set_problems` → completed → sync

### 并发控制
- Hermes 自动限制 `max_concurrent_children`，满了就排队
- 不要手动等待，让 Hermes 管理队列
- 中途单题失败不影响其他题

---

## 模式二：随手拍

单道题，流程同批量但只跑一次：

1. create_task → processing
2. vision_analyze 查看
3. delegate_task → 加载 ocr + solve + tag 三个 skill，输出一道题的结果
4. 写入 → completed → sync

---

## 模式三：单题更新

指定 task 中已有的题号重新处理：

1. `mcp__oopsnote__get_task` 获取数据
2. 对每个指定题号：
   - `action=ocr`: delegate_task 重跑 ocr → solve → tag
   - `action=solve`: 保留题面，delegate_task 重跑 solve → tag
   - `action=tag`: 保留题面+答案，delegate_task 只重跑 tag
3. `mcp__oopsnote__set_problems` 更新 → sync

---

## 错误处理
- 子 agent 失败 → 标记该题 failed，继续其他
- 汇总时报告：成功 N 道，失败 M 道
