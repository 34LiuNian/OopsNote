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
       -> Pi RPC / pi_agent_rust（默认，三个长驻 worker）
       -> upstream Pi（仅显式诊断）
       -> Hermes（迁移期 fallback）
    -> 受限 Python MCP
    -> OopsNote Core
       -> JSON / Assets / Obsidian
```

Pi 使用三个有界的长驻 RPC worker 串行处理各自领取的任务，并在每个任务前通过 `new_session` 创建干净上下文。失败任务只可作为同一后端上的全新 run 重试，绝不在同一 run 内自动切换到 upstream Pi 或 Hermes。Core 负责数据、任务生命周期和原子 finalize；AI 运行时不直接写仓库文件。题目正文统一使用 [OopsMark v1](docs/oopsmark-v1.md)。

完整设计见 [架构文档](docs/ARCHITECTURE.md)，本机 Pi 配置与调试见 [Pi 运维指南](docs/operations/pi.md)。

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
npm install --prefix .pi
.\.venv\Scripts\python.exe scripts\setup\setup_pi.py --sync

$env:PYTEST_ADDOPTS='--basetemp=E:/works/2026/OopsNote/.pytest-tmp'
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix frontend run typecheck
npm --prefix frontend run lint
```

API 与前端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn oopsnote.api.main:app --reload
npm --prefix frontend install
npm --prefix frontend run dev
```

Pi 实题验证：

```powershell
.\.venv\Scripts\python.exe scripts\benchmarks\pi_math_smoke.py
.\.venv\Scripts\python.exe scripts\benchmarks\pi_math_benchmark.py
```

基准报告写入 `storage/pi-benchmark/`，单次任务状态、阶段 prompt version/延迟、重试计数、模型原始/解析输出和校验错误证据写入 `storage/runs/`；REST 只展示非敏感的证据目录。

## 当前进度

- Core、MCP、Obsidian、搜索和 Web 主流程已建立。
- Pi P1/P2 已接入，具备受管运行、取消、超时、恢复、统计和受限工具。
- OopsMark v1 已接入 Core、AI 输出与 Web 渲染。
- 下一步是结构化生产验证和 60 题黄金集，不是继续扩展双后端。
- Hermes 仅保留到 Pi 达成下线门槛。

具体优先级见 [项目 backlog](docs/todo.md)。

## License

OopsNote 自有代码以 [AGPL-3.0-or-later](LICENSE) 发布。

第三方代码、字体、框架和其他资源不自动继承 OopsNote 的许可证，具体归属和许可证见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
