---
name: oopsnote-segment
description: "错题定位 — 在批改后的作业/试卷页面中识别错题区域。"
version: 2.0.0
license: MIT
metadata:
  hermes:
    tags: [oopsnote, segment, error-detection, wrong-problem]
---

# OopsNote — 错题定位

## 功能
在批改后的页面中识别**哪些题做错了**，输出错题区域列表。对题跳过。

## 输入
- 页面图片（vision_analyze）
- 学科

## 输出

```json
[
  {"index": 0, "description": "页面中部第3题，有红叉标记"},
  {"index": 1, "description": "页面下方第7题，题号被圈出，旁边有'重做'批注"}
]
```

## 判断标准

**以下情况判定为错题：**
- ✓ 红叉 / 打叉 / 半对半叉
- ✓ 题号被圈出（○、□）
- ✓ 老师批注（"？"、"重做"、"再算"、扣分标记如"-3"）
- ✓ 答案被划掉或被修改
- ✓ 空着没做的题
- ✓ 明显的订正痕迹（旁边写了正确答案）

**以下情况不是错题：**
- 打了 ✓ / 勾
- 没有任何批改标记
- 单纯的划线/波浪线（可能是重点标记）

## 步骤

1. `vision_analyze` 查看整页
2. 逐题扫描，找错题标记
3. 输出错题列表（位置描述 + 序号）
4. 如果整页没发现任何错题，直接说"本页无错题"，不调 OCR
