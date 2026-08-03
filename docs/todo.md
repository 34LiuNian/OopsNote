user:
- [x] 跨页（切页脚）：连续选框按阅读顺序拆为 page-local `parts`，会话契约拒绝错序、跳号、越栏和已删除页引用；浏览器回归覆盖拖过页脚后的持久化，渲染回归覆盖跨页图片按 `order` 纵向拼接。
- [x] 框纠正：选框列表可将未读、区域不完整、多题或其他异常持久化为 `needs_review`，恢复时保留原始状态；浏览器回归覆盖标记与解除。
- [x] 框修改：待提交选框由同一 `SelectionModel` 的八个拖拽手柄修改，重算局部 `parts` 后自动保存；浏览器回归覆盖真实手柄拖拽与持久化几何同步。
- [x] Web displaymode：OopsMark 行内数学在 `rehype-katex` 前局部注入 `\displaystyle`，保留行内布局且不再 monkey-patch KaTeX 全局 API；浏览器回归验证 TeX 注解和非块布局。
- [x] 相同题目合并：精确指纹候选、双向归并、Core 防循环记录和详情页跳转均已接通。
- [x] 提高 PDF 性能：前端按可见区域懒渲染并将全分辨率页位图/URL 限制为 6 页 LRU，后端分段渲染限制为 4 页 LRU；工作区代际阻止旧 PDF 的在途渲染回写新工作区。浏览器回归覆盖 10 页顺序访问、淘汰后重载、URL 释放和清空竞态。
- [x] 识别章节、题号：真实 Pi-Rust smoke（task `42ee3e8d6c0843658d1e3fbd48b0240a`，run `ff79112ccec74f2494511a088af94de4`）从含“第二章 函数与导数”和“12”的题图识别并持久化章节、印刷题号；人工覆盖与组卷消费已接通。
# OopsNote backlog

更新：2026-08-03

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
- [x] Web 上传 -> process -> stage -> finalize 的真实浏览器 E2E；通过 `frontend/npm run test:e2e:credentialed` 显式启用真实模型调用并提供测试图片。
- [x] 覆盖文本题、图片题、不可读图片、限流、OCR timeout、取消和 retry；真实 credentialed E2E 覆盖文本/图片题，其余边界由 MCP 和 managed lifecycle 回归覆盖。
- [x] 覆盖错误 JSON、错误 run_id、重复 finalize、abort 无响应与进程崩溃；回归保留 RPC 日志、退出码和第一个终态证据。
- [x] 提供只读 `scripts/benchmarks/pi_production_report.py`，按最终终态任务统计重试后的端到端时间、成本、内存和修订覆盖率，并对未建立的 Hermes 质量/P95 基线及故障注入证据明确显示 `not observed`。
- [ ] 连续运行至少 30 个真实任务并统计成功率、修订率、P50/P95、内存和成本。
- [x] 将端到端时间统一记录为 queued/starting/OCR/solve/verify/tag/finalize 阶段，并由 RunStore 计算排队至终态总时长。

## P2 - AI 质量黄金集

- [ ] 建立 60 题黄金集：数学、物理、化学各 20 题。
- [ ] 覆盖模糊、倾斜、批注、复杂公式、图表和多小问。
- [x] 保存阶段 prompt version、raw/parsed output、validation error、latency 和 retry count：RunStore 以只追加证据记录保存 OCR、solver candidate、verifier submission 及拒绝原因，REST 仅展示非敏感目录。
- [x] OCR 增加缺失区域与低质量提示并禁止补写：`uncertain_regions`、`unreadable`、`incomplete` 会在受管边界终止任务，取消后的 OCR 结果不得附着到任务。
- [x] solve 与 verify 使用独立上下文并检查单位、定义域、条件和选项映射：solver 只持久化一次候选解；runner 创建全新 Pi session 后才允许 verifier 进行标签和终结写入。
- [x] 增加 `answer` 结论契约与一次定向修复：`finalize_task` 对新的 OopsMark v1 AI 写入拒绝推导标记、未编号多段步骤和超长答案；模型按 skill 将被拒内容移入 `explanation` 后重试，历史记录保持可读。
- [x] 标签先召回已有候选再排序：受管 AI 必须先读取 error 候选；知识标签受分支叶子候选约束；创建 error 标签时拒绝已有 canonical/alias 的重复项。

## P3 - 产品链路

- [x] 完成手动批量分割浏览器 E2E 与批量状态恢复。
- [x] 完成题目详情编辑、标签修订和历史 OopsMark 迁移预览：详情 override 已覆盖浏览器 E2E；`scripts/migrate_oopsmark.py` 默认只生成报告，只有 `--apply` 才迁移已验证记录。
- [x] 按 `docs/paper-workflow.md` 实现正式组卷配置、持久化试卷草稿和独立试卷编辑器；保留现有快速重练入口。
- [x] 难度系数按同一题型区段内的 `题号 / 总题数` 估算，数值越高越难。
- [ ] 校准小题量区段的难度系数估算精度。
- [x] 支持人工难度系数覆盖题号估算值：覆盖值保存在 `TaskRecord.difficulty_coefficient_override`，由选题和草稿快照统一派生。
- [x] 无法识别题号或区段总题数时，将题目标记为需要人工处理：`TaskRecord.section_question_count` 是唯一总题数来源；缺失、越界或来源缺失会携带明确 review reason，且不会进入自动选题。
- [x] 实现 `/papers/compile`，只调用 Core OopsMark 导出器。
- [x] 为 molecule 与 Mermaid 建立带源 SHA-256、渲染器版本和主题变体的有界浏览器派生 SVG 缓存；失败和超限 SVG 不缓存，OopsMark 仍是唯一内容源。
- [x] 完成 Obsidian 单向同步冲突策略：manifest v2 保存写入哈希；本地修改后保留 vault 文件并报告冲突，不自动覆盖或删除。双向同步仍不在当前范围内。

## P4 - Hermes 下线

- [ ] Pi 达成 `docs/ARCHITECTURE.md` 的 7 天和 30 任务门槛。
- [ ] 删除 Hermes runner、setup、profile 同步和专属说明。
- [ ] 保留 Python MCP，并把 backend 参数收敛为 Pi 默认兼容行为。
