# 打标 — 详细指令（V2）

为主题目标注多维标签：知识点、错因、难度。

## 工作方式

### 1. 查询已有标签

受管 Web 模式调用 `mcp__oopsnote_pipeline__list_tags`，交互模式调用 `mcp__oopsnote__list_tags` 渐进获取 AI 可选标签：

```python
# 第一次：获取一级分组和二级分支
branches = mcp__oopsnote_pipeline__list_tags(
    dimension="knowledge", subject="math", scope="core"
)

# 从 branches.items 中选择 1-6 个二级分支 ID，再获取对应叶子标签
leaves = mcp__oopsnote_pipeline__list_tags(
    dimension="knowledge",
    subject="math",
    scope="core",
    branch_ids=["27942", "27943"]
)

# 获取错因标签
mcp__oopsnote_pipeline__list_tags(dimension="error", subject="math")
```

知识点必须从第二次调用返回的 `mode="leaves"` 的 `items` 中选择。最多传 6 个二级分支 ID；不要传一级分组，也不要自由创建知识标签。

### 2. 分析题目

根据题目文本、答案、解析判断：

| 维度 | 说明 |
|------|------|
| `knowledge_points` | 涉及的知识点，按重要性排列，1~5 个 |
| `error_hypothesis` | 可能的错因，具体可操作（如"忽略定义域"而非"粗心"）|
| `difficulty` | `简单` / `中等` / `较难` |

### 3. 创建新标签（如果需要）

```python
mcp__oopsnote_pipeline__create_tag(
    dimension="error",
    value="忽略定义域",
    aliases=["定义域遗忘", "忘记定义域限制"],
    subject="math"
)
```

## JSON 输出格式

```json
{
  "knowledge_points": ["判断元素能否构成集合"],
  "error_hypothesis": ["忽略定义域"],
  "difficulty": "中等"
}
```

## 约束
- `knowledge_points` 用标准术语，不超过 5 个
- `error_hypothesis` 要具体（"忽略定义域" ✅ / "粗心" ❌）
- 难度用中文：`简单` / `中等` / `较难`
- 最多选择 6 个二级分支，知识点只从随后加载的叶子标签中选择
