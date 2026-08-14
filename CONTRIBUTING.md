# Contributing

感谢参与 OopsNote。提交 PR 前请确认满足下面的门禁——它们与 CI 完全一致。

## 环境准备

```sh
uv sync                       # Python（含 dev 依赖：pytest/ruff/pre-commit）
npm --prefix frontend ci      # 前端（Node 版本见 frontend/.nvmrc）
uv run pre-commit install     # 可选：commit 时自动执行风格门禁
```

## 质量门禁

- Linux / CI：`make check`（ruff + eslint + 格式校验 + tsc + 全部单测）；
- Windows / VSCode：任务 “OopsNote: Verify (Lint + Typecheck + Tests)”；
- Windows 上跑 pytest 必须带工作区本地 basetemp（见 `AGENTS.md`）。

CI 在每次 push/PR 上运行三个 job：Backend（ruff + pytest）、Frontend
（eslint + tsc + 单测）、Docker（前后端镜像构建）。全绿才会合入。

## 提交规范

使用 Conventional Commits（`feat:` `fix:` `docs:` `ops:` `chore:` `ci:`），
消息可用中文。一次提交只做一件事。

## 代码风格

- Python 由 `ruff.toml` 统一（line-length 100）：`uv run ruff check .` /
  `uv run ruff format .`；
- 前端由 eslint + prettier 隐含约束（`npm --prefix frontend run lint`）；
- 换行符统一 LF（`.gitattributes`），编辑器配置见 `.editorconfig`。

## 项目结构

见 `README.md` 与 `AGENTS.md`；内容格式改动前先读 `docs/oopsmark-v1.md`；
可靠性相关改动先读 `skills/prevent-patchwork-technical-debt/SKILL.md`。
