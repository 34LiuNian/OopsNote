# 打标 — 详细指令（V2）

为主题目标注多维标签：知识点、错因、难度。

## 工作方式

### 1. 查询已有标签

受管 Web 模式调用 `mcp__oopsnote_pipeline__list_tags`，交互模式调用 `mcp__oopsnote__list_tags` 获取标签候选：

```python
# 获取知识点标签
mcp__oopsnote_pipeline__list_tags(dimension="knowledge", query="函数", subject="math", scope="core", limit=20)

# 获取错因标签
mcp__oopsnote_pipeline__list_tags(dimension="error", query="定义域", limit=20)
```

**优先使用已有标签**，避免创建同义标签。仅当确实没有匹配时才创建新的。

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
    dimension="knowledge",
    value="二次函数",
    aliases=["一元二次函数", "二次函数图像"],
    subject="math"
)
```

## JSON 输出格式

```json
{
  "knowledge_points": ["二次函数", "最值问题", "分类讨论"],
  "error_hypothesis": ["忽略定义域"],
  "difficulty": "中等"
}
```

## 约束
- `knowledge_points` 用标准术语，不超过 5 个
- `error_hypothesis` 要具体（"忽略定义域" ✅ / "粗心" ❌）
- 难度用中文：`简单` / `中等` / `较难`
- 先查已有标签，后创建新标签
