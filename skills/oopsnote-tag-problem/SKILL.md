---
name: oopsnote-tag-problem
description: "Assign validated knowledge, error-hypothesis, and difficulty tags to one managed OopsNote problem through the restricted tag catalogue workflow."
---

# Tag One Problem

- 仅依据题目、答案、解析、学科和观察到的学生作答打标；不得由难点、干扰项或题目本身臆测学生错误。runner 决定唯一合法的下一工具调用，按绑定顺序执行，不并行猜测调用。
- 知识点依次：请求 `dimension="knowledge"`、`subject`、`scope="core"` 的二级分支；选择 1-6 个直接考查分支 ID；请求其叶子；仅从返回叶子选 `knowledge_points`。禁止父级、自由文本和创建知识标签；通常保留 1-3 个不可绕开的核心点。
- 先请求 `dimension="error"` 的已有值，再选具体可操作的错因，如 `忽略定义域`，不用 `粗心`。`student_response_status` 不是 `answered` 时置空，除非定向变式有 runner 明确提供的可信错因；绝不从题目制造错因。
- 只有没有合适既有错因且当前工具允许时才创建错因标签。`difficulty` 只能为 `简单`、`中等`、`较难`。
