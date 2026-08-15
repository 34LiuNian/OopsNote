# OopsNote backlog

更新：2026-08-15

本文件只记录当前 LangChain + Better Auth 架构下尚未完成的产品工作。历史迁移工作
不作为当前待办，退役说明见 `docs/archive/retired-runtime-history.md`。

## P1 - 生产验证

- [ ] 使用固定四阶段策略连续运行至少 30 个真实任务，统计成功率、修订率、
  P50/P95、token、成本和取消终态。
- [ ] 对真实任务执行人工质量复核，并将验收阈值写入 LangChain evidence manifest。
- [ ] 完成恢复、取消、重复 finalize 和 provider 瞬时失败的生产故障注入记录。

## P2 - AI 质量黄金集

- [ ] 建立 60 题黄金集：数学、物理、化学各 20 题。
- [ ] 覆盖模糊、倾斜、批注、复杂公式、图表和多小问。
- [ ] 为 Vision、solve、review、tag/finalize 建立固定策略回归报告。

## P3 - 产品链路

- [ ] 校准小题量区段的难度系数估算精度。
- [ ] 完成题图自动版面识别的独立评测，再决定是否接入人工确认流程。
- [ ] 为 Better Auth 账号恢复和可选 Passkey 建立产品与安全方案。
