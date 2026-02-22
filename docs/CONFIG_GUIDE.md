# 配置文件与环境设置指南

**更新日期**: 2026 年 2 月 22 日  
**最后整理**: 配置文件统一与环境优化

---

## 📁 配置文件总览

### 根目录配置

| 文件 | 用途 | 状态 |
|------|------|------|
| `.gitignore` | Git 忽略规则 | ✅ 已优化 |
| `.vscode/launch.json` | VS Code 调试配置 | ✅ 已修复 |
| `.vscode/tasks.json` | VS Code 任务配置 | ✅ 已清理 |
| `README.md` | 项目说明 | ✅ 已更新 |

### 后端配置 (backend/)

| 文件 | 用途 | 状态 |
|------|------|------|
| `.env` | 环境变量（敏感） | ✅ 存在 |
| `.env.example` | 环境变量示例 | ✅ 存在 |
| `pyproject.toml` | Python 项目配置 | ✅ 存在 |
| `uv.lock` | uv 依赖锁定 | ✅ 存在 |
| `agent_config.example.toml` | Agent 配置示例 | ✅ 存在 |

### 前端配置 (frontend/)

| 文件 | 用途 | 状态 |
|------|------|------|
| `.env` | 环境变量 | ✅ 已创建 |
| `.env.example` | 环境变量示例 | ✅ 存在 |
| `package.json` | Node.js 依赖 | ✅ 存在 |
| `package-lock.json` | npm 依赖锁定 | ✅ 存在 |
| `tsconfig.json` | TypeScript 配置 | ✅ 存在 |
| `next.config.mjs` | Next.js 配置 | ✅ 已优化 |
| `.eslintrc.json` | ESLint 配置 | ✅ 存在 |
| `.npmrc` | npm 配置 | ✅ 存在 |

### 运行时配置 (backend/storage/settings/)

| 文件 | 用途 | 状态 |
|------|------|------|
| `tags.json` | 标签库 | ✅ 存在 |
| `tag_dimensions.json` | 标签维度样式 | ✅ 存在 |
| `agent_models.json` | Agent 模型选择 | ✅ 存在 |
| `agent_enabled.json` | Agent 启用状态 | ✅ 存在 |
| `agent_thinking.json` | Agent 思考模式 | ✅ 存在 |

---

## 🔧 环境变量说明

### 后端环境变量 (backend/.env)

#### 必需配置

```bash
# OpenAI 兼容网关地址
OPENAI_BASE_URL=http://server.alan-ztr.eu.org:3000/v1

# API 密钥（敏感信息）
OPENAI_API_KEY=sk-xxx

# 认证头名称（可选，默认 Authorization）
OPENAI_AUTH_HEADER_NAME=Authorization

# 完整认证头（可选，自动使用 OPENAI_API_KEY）
OPENAI_AUTHORIZATION=Bearer ${OPENAI_API_KEY}
```

#### 可选配置

```bash
# 模型选择（默认由 Agent 决定）
# OPENAI_MODEL=gpt-4o-mini

# 温度参数（默认 0.2）
OPENAI_TEMPERATURE=0.2

# 最大 token 数（默认 10000）
OPENAI_MAX_TOKENS=10000

# 启用多 Agent 协同（默认 true）
ENABLE_MULTI_AGENT=true

# 日志级别（默认 INFO）
APP_LOG_LEVEL=INFO

# 调试选项
AI_DEBUG_LLM=false                    # LLM 调用日志
AI_DEBUG_LLM_PAYLOAD=true            # LLM 请求/响应内容
AI_DEBUG_LLM_PAYLOAD_INCLUDE_IMAGE=true  # 包含图片数据
```

#### 功能开关

```bash
# 扫描功能
# ENABLE_SCANNER=true

# 任务持久化
# PERSIST_TASKS=true
# TASKS_DIR=./storage/tasks

# 任务超时设置（秒）
# TASK_STALE_SECONDS=600
```

#### Agent 配置

```bash
# Agent TOML 配置文件路径（可选）
# AGENT_CONFIG_PATH=./agent_config.toml
```

### 前端环境变量 (frontend/.env)

#### 必需配置

```bash
# 后端 API 地址（用于开发和生产）
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

#### 生产环境配置

```bash
# 生产环境后端地址
NEXT_PUBLIC_BACKEND_URL=https://api.yourdomain.com
```

---

## 🚀 快速开始

### 1. 后端配置

```bash
# 复制示例配置
cd backend
cp .env.example .env

# 编辑 .env，填入必要的配置
# 至少需要设置 OPENAI_BASE_URL 和 OPENAI_API_KEY
```

### 2. 前端配置

```bash
# 复制示例配置
cd frontend
cp .env.example .env

# 通常不需要修改，使用默认的 http://localhost:8000 即可
```

### 3. 安装依赖

**后端（使用 uv，推荐）**
```bash
cd backend
uv sync --dev
```

**或使用 pip**
```bash
cd backend
python -m pip install -e .[dev]
```

**前端**
```bash
cd frontend
npm install
```

### 4. 启动开发环境

**使用 VS Code（推荐）**
1. 打开命令面板：`Terminal: Run Task`
2. 选择：`dev: all`

**手动启动**

后端：
```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端：
```bash
cd frontend
npm run dev
```

---

## 🔐 安全注意事项

### .env 文件安全

- ✅ `.env` 文件已在 `.gitignore` 中排除
- ✅ 提交前请确认 `.env` 未被跟踪：`git ls-files | grep "\.env$"`
- ⚠️ 不要将包含真实 API Key 的 `.env` 提交到版本控制

### API 密钥管理

**推荐做法**：
1. 使用环境变量注入（生产环境）
2. 使用密钥管理工具（如 AWS Secrets Manager）
3. 定期轮换 API 密钥

**开发环境**：
- 可以使用本地 `.env` 文件
- 确保 `.env` 文件权限设置为仅所有者可读

---

## 📊 配置依赖关系

### 后端配置加载顺序

```
1. 系统环境变量（最高优先级）
   ↓
2. backend/.env 文件
   ↓
3. agent_config.toml（若启用 AGENT_CONFIG_PATH）
   ↓
4. 代码中的默认值（config.py）
```

### 前端配置加载顺序

```
1. 系统环境变量
   ↓
2. frontend/.env 文件
   ↓
3. next.config.mjs 中的配置
   ↓
4. 代码中的默认值
```

---

## 🔍 配置验证

### 检查 .env 是否被提交

```bash
# 应该没有输出
git ls-files | grep "\.env$"
```

### 验证后端配置

```bash
cd backend
# 检查 .env 文件是否存在
Test-Path .env

# 检查 Python 环境
uv pip list

# 启动后端并查看日志
uv run uvicorn app.main:app --reload
```

### 验证前端配置

```bash
cd frontend
# 检查 .env 文件是否存在
Test-Path .env

# 检查 Node 环境
npm list --depth=0

# 启动前端并查看日志
npm run dev
```

### 测试 API 连接

```bash
# 测试后端健康检查
curl http://localhost:8000/health

# 测试前端代理
curl http://localhost:3000/api/health
```

---

## 🛠️ 故障排除

### 常见问题

#### 1. 前端无法连接后端

**症状**: 前端 API 请求失败

**解决方案**:
- 检查 `frontend/.env` 中的 `NEXT_PUBLIC_BACKEND_URL`
- 确认后端正在运行：`http://localhost:8000/health`
- 检查浏览器控制台是否有 CORS 错误

#### 2. 后端无法连接 AI 网关

**症状**: LLM 调用失败

**解决方案**:
- 检查 `backend/.env` 中的 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY`
- 测试网关连接：`curl -H "Authorization: Bearer $OPENAI_API_KEY" $OPENAI_BASE_URL/models`
- 检查网络防火墙设置

#### 3. VS Code 任务无法启动

**症状**: 运行 `dev: all` 任务失败

**解决方案**:
- 检查 `.vscode/tasks.json` 语法
- 确认 `.venv` 目录存在
- 手动运行后端和前端命令测试

#### 4. 环境变量未生效

**症状**: 配置修改后未生效

**解决方案**:
- 重启开发服务器（.env 在启动时读取）
- 清除 Next.js 缓存：`rm -rf .next`
- 检查环境变量拼写

---

## 📝 配置最佳实践

### 开发环境

- ✅ 使用 `.env` 文件管理本地配置
- ✅ 启用调试日志：`AI_DEBUG_LLM_PAYLOAD=true`
- ✅ 使用本地后端地址：`http://localhost:8000`

### 生产环境

- ✅ 使用系统环境变量注入
- ✅ 关闭调试日志：`AI_DEBUG_LLM=false`
- ✅ 使用 HTTPS 和域名
- ✅ 配置正确的 CORS 策略

### 团队协作

- ✅ 提交 `.env.example` 作为模板
- ✅ 在文档中说明必需的配置项
- ✅ 使用密钥管理工具共享敏感配置
- ✅ 定期更新依赖版本

---

## 🔄 配置更新历史

### 2026-02-22

- ✅ 创建 `frontend/.env` 文件
- ✅ 修复 `.vscode/launch.json` 语法错误
- ✅ 优化 `next.config.mjs` 使用环境变量
- ✅ 更新 `README.md` 说明使用 uv
- ✅ 清理 `.vscode/tasks.json` 注释代码
- ✅ 验证 `.env` 文件未被提交到 git

---

## 📚 相关文档

- `README.md` - 项目总体说明
- `AGENTS.md` - AI 流程说明
- `backend/README.md` - 后端详细说明
- `docs/ARCHITECTURE.md` - 系统架构
- `docs/CODE_CLEANUP_REPORT.md` - 代码清理报告
