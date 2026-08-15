# Changelog

本文件从 0.1.0 起记录对外可见的变化；更早历史见 Git 日志。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

### Added

- 首次启动引导：`scripts/deploy/bootstrap.sh` 幂等生成 `.env` 与全部 secret
  文件；`/setup` 网页引导页创建第一个管理员（`/api/admin/setup`）。
- GitHub Actions CI：ruff + pytest + eslint/tsc/单元测试 + 前后端镜像构建。
- 代码风格门禁：`ruff.toml` 全库统一（line-length 100）、pre-commit、
  `.editorconfig`、`.gitattributes`（LF）。
- 统一任务入口：`Makefile`（Linux/CI）与 VSCode 任务（Windows）。
- 部署 runbook（`deploy/README.md`）、根 `.env.example`、secret 模板
  （`deploy/oopsnote/secrets/*.example`）、`SECURITY.md`/`CONTRIBUTING.md`。

### Changed

- AI 运行时收敛为唯一 LangChain backend；移除旧 agent/RPC runner、配置、
  部署挂载、setup、benchmark、诊断和兼容测试。
- 认证收敛为 Better Auth（生产）与 local（回环开发）；移除外部身份提供商
  的 bearer/JWKS、前端回调和 sessionStorage 兼容代码。

### Fixed

- backend Dockerfile 引用不存在的 `scripts/migrate_multitenancy.py`。
- Better Auth schema 并发迁移竞态（`duplicate column name: username`，构建
  多 worker / 多实例冷启动）。
- pytest 在 CI console-script 调用下无法导入 `scripts.*`（增加
  `pythonpath = ["."]`）。
- `docs/issue.md` 乱码恢复、`docs/todo.md` 残留块清理。
