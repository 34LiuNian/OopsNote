# OopsNote 统一任务入口（Linux 服务器 / GitHub Actions CI）
# Windows 本地开发请使用 VSCode 任务（.vscode/tasks.json）

.PHONY: help sync secrets lint format format-check typecheck test ci-backend ci-frontend check

help: ## 列出所有可用任务
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

sync: ## 安装 Python 与前端依赖
	uv sync
	npm --prefix frontend ci

secrets: ## 首次启动：自动生成 .env 与全部 secret 文件（服务器上执行）
	./scripts/deploy/bootstrap.sh

lint: ci-backend ci-frontend ## Python (ruff) 与前端 (eslint) 静态检查

format: ## 应用 ruff format 统一代码格式
	uv run ruff format .

format-check: ## 校验格式（CI 门禁）
	uv run ruff format --check .

typecheck: ## 前端 TypeScript 检查
	npm --prefix frontend run typecheck

test: ## 全部单元测试
	uv run pytest -q
	npm --prefix frontend run test:unit

ci-backend: ## CI 后端门禁（ruff + pytest）
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest -q

ci-frontend: ## CI 前端门禁（eslint + tsc + 单元测试）
	npm --prefix frontend run lint
	npm --prefix frontend run typecheck
	npm --prefix frontend run test:unit

check: lint format-check typecheck test ## 完整质量门禁（本地，与 CI 同款）
