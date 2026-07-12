---
name: oopsnote-segment
description: "页面分割 — 识别作业/试卷中的题目区域，AI 审计复核。"
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [oopsnote, segment, page-split, problem-detection]
---

# OopsNote — 页面分割

## 功能
将扫描的 PDF/图片页面切分为独立的题目区域。

## 输入
- 图片（通过 vision_analyze 查看）
- 可选：学科（数学/物理/化学）

## 输出
每道题的裁剪区域描述（bbox 或自然语言），以及简要的题目类型预判。

## 步骤

### 1. 查看图片
用 `vision_analyze` 查看输入的页面/图片。

### 2. 识别题目区域
分析图片中的题目分布：
- 题号标记（如 "1."、"一、"、"1、"）
- 空白分隔区域
- 题干 + 选项的排版特征
- 印刷题目 vs 手写笔记（忽略手写）

### 3. AI 审计
检查分割结果：
- 是否遗漏了题目？
- 是否把一道题切成了多块？
- 跨页题目是否被截断？

### 4. 返回结果
对每道题输出：
- `index`: 序号
- `description`: 题目在页面中的位置描述
- `question_type_hint`: 初步判断的题型（单选题/多选题/填空题/解答题）
- `subject_hint`: 初步判断的学科（如果混合了多学科）

## 约束
- 只提取印刷题目，忽略学生手写内容
- 跨页题目标注 `cross_page: true`
- 不确定的区域标注 `uncertain: true`，交由下一步 OCR 确认
