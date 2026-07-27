---
name: oopsnote-tag-problem
description: "打标 — 为题目标注知识点、错因、题型等多维标签。"
version: 1.2.0
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
- `student_response_status`: `answered` / `unanswered` / `unknown`
- `student_response`: OCR 识别到的学生作答；不是题目标准答案

## 输出

```json
{
  "knowledge_points": ["判断元素能否构成集合"],
  "error_hypothesis": ["忽略定义域"],
  "difficulty": "中等"
}
```

## 步骤

### 1. 查询标签候选
调用 Pi 暴露的 OopsNote `list_tags` 直连工具渐进获取 AI 可选标签。查询知识点时必须传入题目的英文 `subject`，普通题默认使用 `scope=core`。

1. 调用 `list_tags(task_id=<当前任务>, run_id=<当前运行>, dimension="knowledge", subject=<题目学科>, scope="core")`，读取 `mode="branches"` 下的一级分组和二级分支。
2. 根据题目直接考查内容选择 **1-6 个**最相关的二级分支 ID。禁止传一级分组名称或 ID。
3. 在同一轮并行调用以下两个互不依赖的查询：
   - `list_tags(task_id=<当前任务>, run_id=<当前运行>, dimension="knowledge", subject=<题目学科>, scope="core", branch_ids=[...])`，读取 `mode="leaves"` 的 `items`；
   - `list_tags(task_id=<当前任务>, run_id=<当前运行>, dimension="error", subject=<题目学科>)`，读取 `mode="values"` 下的已有错因标签。

知识点必须从第二次调用返回的叶子标签中选择。父级目录、未加载标签和自由生成标签会被最终提交校验拒绝。

### 2. 分析题目
根据题目内容、解题过程判断：
- **knowledge_points**：只保留题目直接考查、解答不可绕开的核心知识点，按重要性排列，通常 1-3 个
- **error_hypothesis**：只分析可读学生作答中有证据支持的实际错因。`student_response_status` 不是 `answered` 时必须为 `[]`；不得根据题目难点臆测错因。
- **difficulty**：简单/中等/较难

### 3. 创建新标签（如果需要）
禁止创建知识标签。仅在确实缺少合适的错因标签时，才调用 Pi 暴露的 OopsNote `create_tag(task_id=<当前任务>, run_id=<当前运行>, dimension="error", ...)` 直连工具创建错因标签。

### 4. 返回结果
将标签字段返回给 orchestrator，由 `finalize_task` 与完整 Problem 一次性提交。

## 约束
- 最多选择 6 个二级分支；知识点只使用这些分支加载出的叶子标签
- 知识点标签用标准术语
- 选择题不得因为干扰项或解析中顺带使用的方法增加知识点；删除背景概念、通用解题动作和非得分点标签
- 错因标签要具体可操作（不是"粗心"，而是"忽略定义域"）
