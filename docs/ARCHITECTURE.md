# OopsNote architecture

状态：LangChain 单一运行时，Better Auth 单一生产认证
更新：2026-08-27

## 1. 产品边界

OopsNote 是本地优先的多用户错题系统。Web 是主入口，Obsidian 是开放数据出口；
CLI 和脚本只用于开发、运维与评测。输入包括单题图片、手动题目和 Web 手动批量
框选。自动页面分割不属于当前可靠链路。

## 2. 运行架构

```text
Browser
   | Better Auth session
Next.js BFF
   | signed internal identity
FastAPI
   | enqueue / run / cancel / retry / recover stale
ManagedAiRunner
   | immutable provider policy snapshot
LangChainRunner
   | bounded 24-round restricted tool loop
restricted MCP HTTP -> OCR + pipeline tools -> Core stores
```

系统不提供 AI backend 选择。`LangChainRunner` 是唯一模型运行时；
`ManagedAiRunner` 是唯一生命周期所有者，负责 run 所有权、heartbeat、timeout、
取消、陈旧任务恢复、日志、重试资格和 finalize 后检查。LangChain 只负责显式
provider 调用和受限工具循环。

普通 run 在入队时冻结 `vision`、`agent`、`review` 三阶段 channel/model policy；
题图重建冻结独立的 `diagram` 选择。OCR 只能从当前 run 的不可变 Vision 快照解析
模型和 SecretStore 凭证，不读取第二份配置。失败不会切换 provider 或模型。

## 3. 身份与工作区

Better Auth 是生产身份真源，数据库由 Next.js 独占。BFF 验证 session 后向 FastAPI
发送短时 HMAC 签名身份封套；FastAPI 从控制库解析不可变 workspace 映射。浏览器
不能直接指定 workspace 路径或资源 owner。

`local` 模式只允许回环开发，跳过登录并映射固定本地管理员。生产没有外部身份
提供商兼容路径，也没有 bearer token/JWKS 分支。

## 4. 数据与写入边界

```text
LangChain -> restricted MCP -> Core -> storage/workspaces/<id>/
                                      -> assets/
                                      -> Obsidian vault (explicit sync)
Frontend  -> signed BFF REST -----> Core
```

- AI 不能直接读写 `storage/`。
- MCP capability 绑定 `workspace_id`、`task_id` 和 `run_id`。
- `submit_solution_candidate` 只写当前 run 的未提交候选；新 review 上下文验证后才能
  `finalize_task`。
- finalize 幂等且最多成功一次。
- 仅瞬时网络、429 或明确 5xx 最多产生两个 fresh retry；401/403、模型配置、schema、
  validation 和未 finalize 都不可重试。
- 历史 `storage/` 记录是本地证据，不定义当前架构，也不触发旧运行时加载。

## 5. 内容协议

题干、选项、答案和解析只有一份可编辑源：OopsMark v1。

```text
OCR / AI / manual edit -> OopsMark v1 -> Web renderer
                                     -> Obsidian writer
                                     -> LaTeX adapter
```

协议定义见 [oopsmark-v1.md](oopsmark-v1.md)。渲染端不得悄悄重写 v1 原文；历史
内容使用显式 legacy 内容格式适配，这与运行时兼容无关。

## 6. 源码职责

| 区域 | 职责 |
| --- | --- |
| `oopsnote/core` | Pydantic 模型、JSON store、资产、标签和搜索 |
| `oopsnote/content` | OopsMark 解析、验证和导出适配 |
| `oopsnote/ai` | 共享生命周期、LangChain adapter、provider 与 SecretStore |
| `oopsnote/api` | REST DTO、路由与应用组合 |
| `oopsnote/mcp` | AI 可调用的数据工具和 pipeline 写入边界 |
| `oopsnote/obsidian` | Core 到 Vault 的同步 |
| `oopsnote/paper` | 试卷模板与导出支持 |
| `frontend` | Next.js UI、Better Auth 与 BFF。排版与交互约定见 [frontend-interaction.md](frontend-interaction.md) |
| `skills` | OCR、解题、验证、标签和编排指令的唯一源码 |

## 7. 配置与密钥

AppSettings 只保存非敏感 provider channel、模型目录、四阶段策略和 opaque
credential reference。Windows 使用 Credential Manager；Linux/容器使用由只读挂载
master key 加密的持久化 vault。密钥明文绝不写入 `storage/`、TaskRun、日志、环境
变量或 REST 响应。

当前运行架构不读取隐藏 runtime 目录、外部 agent 配置或外部身份提供商配置。
退役历史仅见 [retired-runtime-history.md](archive/retired-runtime-history.md)，不得作为
实现或评测门槛依据。
