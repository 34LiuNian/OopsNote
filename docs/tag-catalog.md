# 标签目录源

OopsNote 的内置知识标签以学科知识树为权威源。旧的跨学段扁平
`tags_builtin.json` 已废弃，不参与运行时加载。

## 生成资产

- `oopsnote/catalog/data/knowledge_trees.json`：完整清洗知识树；保留来源节点 ID、父子关系、范围和所有同名路径。
- `oopsnote/catalog/data/knowledge_tags.json`：供 REST、MCP 和标签选择器检索的扁平索引；按“学科 + 规范化标题”合并同名节点。
- `oopsnote/catalog/data/chapter_trees.json`：清洗后的教材章节树，目前状态为 `reserve`，不参与知识标签检索。

当前收录高中数学、物理、化学、生物。知识树中的竞赛和初中衔接分支分别标记为
`competition`、`prerequisite`，其余为 `core`。

## HAR 解析

导入器读取标准 HAR 的 `log.entries[]`，只接受请求路径匹配
`/zujuan/tree/lk_<bank>.json` 或 `/zujuan/tree/c_<bank>_<edition>.json` 的响应。
JSON 正文来自 `response.content.text`；当 `response.content.encoding` 为
`base64` 时先解码。浏览器归档中的空响应、重复下载记录和其他接口请求不会作为树导入。

## 重新生成

使用项目解释器运行：

```powershell
.\.venv\Scripts\python.exe scripts\catalog\import_xkw_trees.py `
  <knowledge-or-chapter.har> [<more.har> ...]
```

导入要求每个学科最多一棵知识树和一棵章节树。输出使用源响应内容哈希和 HAR
捕获时间记录来源，不使用执行时钟，因此相同输入会生成相同结果。

## 运行时约定

- AI 查询知识标签时必须传当前题目的 `subject`。
- 普通题目默认查询 `scope=core`；只有明确属于竞赛或衔接内容时才查询相应范围。
- AI 的 `list_tags` 首次返回一级分组和二级分支；AI 选择最多 6 个二级分支后，再按 `branch_ids` 获取对应叶子标签。
- 受管 AI 最终提交只接受知识树叶子标签，父目录、未登记值和自由创建的知识标签会被拒绝。
- 标签正文仍保存标准术语字符串；树节点 ID 和路径属于目录元数据。
- 用户标签保存在根目录 `storage/`，不会被目录重新生成覆盖。
