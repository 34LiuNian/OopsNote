<!-- Authentication UI bundles Gloock Regular under OFL-1.1. Its full text is
at frontend/public/fonts/Gloock-OFL.txt; see THIRD-PARTY-NOTICES.md. -->

<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/favicon_white.svg">
  <img src="assets/favicon_black.svg" height="150" alt="OopsNote Logo" />
</picture>
<br/>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/oopsnote_white.svg">
  <img src="assets/oopsnote_black.svg" height="100" alt="OopsNote" />
</picture>

## AI 驱动的个人错题管理工具

图片或手动录入 -> OCR、解题、验证、打标 -> 可检索题库、Obsidian 与试卷输出

</div>

## 当前架构

```text
Web / REST
    -> ManagedAiRunner
       -> LangChainRunner（默认，显式 provider adapter）
       -> Pi RPC / pi_agent_rust（仅显式诊断）
       -> Hermes（迁移期显式诊断）
    -> 受限 Python MCP
    -> OopsNote Core
       -> JSON / Assets / Obsidian
```

`ManagedAiRunner` 是唯一任务生命周期所有者。LangChain 只负责 provider
调用和最多 24 轮的受限 MCP tool loop；每个 run 在入队时冻结三阶段 channel/model
策略快照，失败只能按共享策略创建同一 backend 的新 run，绝不自动切换
provider、Pi 或 Hermes。模型与 OCR 凭证只通过 OopsNote SecretStore 解析，
不会写入环境变量、TaskRun、日志或响应。Core 负责数据、状态竞争保护和原子
finalize；AI 运行时不直接写仓库文件。题目正文统一使用
[OopsMark v1](docs/oopsmark-v1.md)。

完整设计见 [架构文档](docs/ARCHITECTURE.md)，本机 provider 与凭证配置见
[LangChain 运维指南](docs/operations/langchain.md)。

## 项目结构

```text
OopsNote/
├── oopsnote/       Python Core、AI runtime、REST、MCP、Obsidian、paper
├── frontend/       Next.js Web 应用
├── skills/         Skill 唯一源码
├── scripts/        安装、基准、诊断和 legacy 工具
├── tests/          Python 测试
├── docs/           协议、架构、运维、决策与 backlog
├── storage/        本地运行数据
└── vaults/         用户题库与 Obsidian 数据
```

## 安装与测试

```powershell
uv sync

$env:PYTEST_ADDOPTS='--basetemp=E:/works/2026/OopsNote/.pytest-tmp'
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix frontend run typecheck
npm --prefix frontend run lint
```

API 与前端：

```powershell
$env:OOPSNOTE_AUTH_MODE='better-auth'
.\.venv\Scripts\python.exe -m uvicorn oopsnote.api.main:app --env-file frontend/.env.local --reload
npm --prefix frontend install
npm --prefix frontend run dev
```

LangChain 隔离生产评测报告：

```powershell
.\.venv\Scripts\python.exe scripts\benchmarks\langchain_production_report.py `
  --storage E:/works/2026/OopsNote/storage-langchain-eval `
  --evidence E:/works/2026/OopsNote/storage-langchain-eval/evidence.json `
  --output-dir E:/works/2026/OopsNote/storage-langchain-eval/report
```

单次任务状态、provider/model/policy version、token/cost、阶段延迟、重试和
脱敏事件写入 `storage/runs/`；REST 只展示非敏感证据。

## 当前进度

- Core、MCP、Obsidian、搜索和 Web 主流程已建立。
- LangChain、SecretStore 和管理员 provider 管理已接入，具备受管运行、取消、超时、恢复、统计和受限工具。
- OopsMark v1 已接入 Core、AI 输出与 Web 渲染。
- 下一步是在管理员 Provider 页面配置渠道、模型能力和三阶段策略，并在隔离 storage 完成至少 30 个真实任务评测。
- RustPi 仅在完成率、质量、P95、成本、取消和重复 finalize 门槛全部有证据后删除；Hermes 退役另行决定。

具体优先级见 [项目 backlog](docs/todo.md)。

## License

OopsNote 自有代码以 [AGPL-3.0-or-later](LICENSE) 发布。

第三方代码、字体、框架和其他资源不自动继承 OopsNote 的许可证，具体归属和许可证见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
