---
name: oopsnote-tag-problem
description: "打标 — 为题目标注知识点、错因、题型等多维标签。"
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [oopsnote, tag, knowledge-points, error-analysis]
---

# OopsNote — 打标

## 功能
为一道题目标注多维标签：知识点、错因、题型、难度。

## 输入
- `problem_text`: 题目文本
- `answer`: 答案
- `explanation`: 解析
- `subject`: 学科

## 输出

```json
{
  "knowledge_points": ["二次函数", "最值问题", "分类讨论"],
  "error_hypothesis": ["忽略定义域"],
  "difficulty": "中等"
}
```

## 步骤

### 1. 查询标签候选
调用 `mcp__oopsnote__list_tags` 获取已有标签库。
- dimension=knowledge：获取知识点候选
- dimension=error：获取错因候选

**优先从已有标签中选择**，避免创建同义标签。

### 2. 分析题目
根据题目内容、解题过程判断：
- **knowledge_points**：涉及的知识点（按重要性排列，1-5 个）
- **error_hypothesis**：可能的错因（计算失误/概念不清/审题错误/忽略条件/...）
- **difficulty**：简单/中等/较难

### 3. 创建新标签（如果需要）
如果标签库中不存在合适的标签，调用 `mcp__oopsnote__create_tag` 创建。

### 4. 写入结果
调用 `mcp__oopsnote__update_task` 将打标结果更新到任务中。

## 约束
- 优先复用已有标签，避免同义词泛滥
- 知识点标签用标准术语
- 错因标签要具体可操作（不是"粗心"，而是"忽略定义域"）
