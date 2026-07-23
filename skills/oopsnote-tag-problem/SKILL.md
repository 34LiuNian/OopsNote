---
name: oopsnote-tag-problem
description: "打标 — 为题目标注知识点、错因、题型等多维标签。"
version: 1.1.0
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
调用 Pi 暴露的 OopsNote `list_tags` 直连工具获取已有标签库。
- dimension=knowledge：获取知识点候选
- dimension=error：获取错因候选

**优先从已有标签中选择**，避免创建同义标签。

### 2. 分析题目
根据题目内容、解题过程判断：
- **knowledge_points**：只保留题目直接考查、解答不可绕开的核心知识点，按重要性排列，通常 1-3 个
- **error_hypothesis**：可能的错因（计算失误/概念不清/审题错误/忽略条件/...）
- **difficulty**：简单/中等/较难

### 3. 创建新标签（如果需要）
如果标签库中不存在合适的标签，调用 Pi 暴露的 OopsNote `create_tag` 直连工具创建。

### 4. 返回结果
将标签字段返回给 orchestrator，由 `finalize_task` 与完整 Problem 一次性提交。

## 约束
- 优先复用已有标签，避免同义词泛滥
- 知识点标签用标准术语
- 选择题不得因为干扰项或解析中顺带使用的方法增加知识点；删除背景概念、通用解题动作和非得分点标签
- 错因标签要具体可操作（不是"粗心"，而是"忽略定义域"）
