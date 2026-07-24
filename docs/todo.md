user:
- [ ] 跨页（切页脚）
- [ ] 框纠正
- [ ] 框修改
- [ ] web displaymode
- [ ] 相同题目合并
- [ ] 提高pdf性能
- [ ] 识别章节、题号
# OopsNote backlog

更新：2026-07-22

本文件只记录尚未完成的工作。已完成历史由 Git 和架构决策记录保存。

## P0 - 当前结构治理

- [x] 将 setup、benchmark、diagnostic、legacy 脚本迁入 `scripts/`。
- [x] 将 `.pi/skills/`、`.pi/self-learning-memory/` 明确为本地生成目录。
- [x] 拆分 AI backend 与 API route，同时保持现有 REST 行为。
- [x] 完整 Python 测试和 Pi setup validation 通过。

## P1 - 生产验证

- [x] 为 Pi 增加串行任务队列；排队任务仍可取消。
- [x] 修复 Windows 下 RunStore 并发读写、完成任务遗留 running run 和 stale recovery 反向覆盖问题。
- [x] 启用长驻 Pi RPC worker，并以逐任务 `new_session`、启动期 MCP 缓存锁、超时重建和进程崩溃恢复保持隔离。
- [ ] Web 上传 -> process -> stage -> finalize 的真实浏览器 E2E。
- [ ] 覆盖文本题、图片题、不可读图片、限流、OCR timeout、取消和 retry。
- [ ] 覆盖错误 JSON、错误 run_id、重复 finalize、abort 无响应与进程崩溃。
- [ ] 连续运行至少 30 个真实任务并统计成功率、修订率、P50/P95、内存和成本。
- [ ] 将未归入 OCR/solve/verify/tag 的端到端时间拆成可观察阶段。

## P2 - AI 质量黄金集

- [ ] 建立 60 题黄金集：数学、物理、化学各 20 题。
- [ ] 覆盖模糊、倾斜、批注、复杂公式、图表和多小问。
- [ ] 保存阶段 prompt version、raw/parsed output、validation error、latency 和 retry count。
- [ ] OCR 增加缺失区域与低质量提示，禁止补写不存在题面。
- [ ] solve 与 verify 使用独立上下文并检查单位、定义域、条件和选项映射。
- [ ] 增加 `answer` 语义校验与一次定向修复：只允许最终结论，证明、推导和理由必须位于 `explanation`。
- [ ] 标签先召回已有候选再排序，默认禁止自由生成近义重复标签。

## P3 - 产品链路

- [ ] 完成手动批量分割浏览器 E2E 与批量状态恢复。
- [ ] 完成题目详情编辑、标签修订和历史 OopsMark 迁移预览。
- [ ] 实现 `/papers/compile`，只调用 Core OopsMark 导出器。
- [ ] 为 molecule 与 Mermaid 建立带源哈希和版本的派生资产缓存。
- [ ] 完成 Obsidian 冲突策略后再考虑双向同步。

## P4 - Hermes 下线

- [ ] Pi 达成 `docs/ARCHITECTURE.md` 的 7 天和 30 任务门槛。
- [ ] 删除 Hermes runner、setup、profile 同步和专属说明。
- [ ] 保留 Python MCP，并把 backend 参数收敛为 Pi 默认兼容行为。
