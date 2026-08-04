# OopsNote architecture

状态：LangChain 默认运行时，RustPi 隔离评测后待删除
更新：2026-08-04

## 1. 产品边界

OopsNote 是本地单用户错题系统。Web 是主入口与主浏览界面，Obsidian 是开放数据出口；CLI 和脚本只用于开发、运维与基准验证。

当前输入包括单题图片、手动题目和 Web 手动批量框选。自动页面分割不属于当前可靠链路。

## 2. 运行架构

```text
Frontend
   | REST
FastAPI
   | enqueue / run / cancel / retry / recover_stale
ManagedAiRunner
   |-------------------------|
LangChainRunner (default)       PiRpcRunner / HermesRunner
explicit provider + 24 turns    diagnostic / migration only
   |
ProviderClientFactory -> SecretStore
                         | Windows Credential Manager
                         | Linux encrypted vault + mounted master key
   |
restricted MCP HTTP -> OCR + pipeline tools -> Core stores
```

共享生命周期只由 `ManagedAiRunner` 管理：run 所有权、heartbeat、timeout、abort、陈旧任务恢复、日志、重试资格和 finalize 后检查。Backend 只负责模型调用与受控工具循环，并通过 `ActiveRunControl` 暴露可取消执行句柄。

默认运行时是 LangChain 的显式 provider adapter。每次 run 固定其三阶段 channel/model policy snapshot，solver 与 verifier 使用独立上下文，最多 24 轮受限 MCP tool loop；Vision/OCR 从同一 run snapshot 解析模型。Pi 与 Hermes 仅可由显式 backend 选择用于诊断，任一 run 都不得自动切换。

LangChain run 使用受管 asyncio task；完整模型与工具循环受同一个超时约束，取消时只取消当前 run。Pi 诊断后端仍复用有界 worker 进程并通过 RPC `abort` 取消。持久化队列先写入 `TaskRun`，应用重启后恢复 `queued` run，遗失的 `running` run 以 fresh retry 处理。

## 3. 数据与写入边界

```text
AI runtime -> restricted MCP -> Core -> storage/*.json
                                    -> storage/assets/
                                    -> vaults/ (explicit sync)
Frontend   -> REST ----------> Core
```

- AI 不能直接读写 `storage/`。
- AI 只开放 `ocr_image`、`get_task`、`get_asset_path`、`list_tags`、`create_tag`、`report_task_stage`、`submit_solution_candidate`、`finalize_task`、`fail_task`。`submit_solution_candidate` 只写入当前 `TaskRun` 的未提交候选，必须由新会话复核后才可 `finalize_task`。
- `run_id` 必须属于当前任务；finalize 必须幂等且最多成功一次。
- 同一 run 不允许从 Pi 自动切换到 Hermes。
- 仅瞬时网络、429 或明确 5xx 最多产生两个全新 retry run；401/403、无效模型、schema/validation 与未 finalize 均不可重试。retry 保留原 run 的三阶段 strategy snapshot，且不会切换 backend。

## 4. 内容协议

题干、选项、答案和解析只有一份可编辑源：OopsMark v1。

```text
OCR / AI / manual edit -> OopsMark v1 -> Web renderer
                                     -> Obsidian writer
                                     -> LaTeX adapter
```

协议定义见 [oopsmark-v1.md](oopsmark-v1.md)。渲染端不得悄悄重写 v1 原文；历史内容使用显式 legacy 格式兼容。

## 5. 源码职责

| 区域                | 职责                                        |
| ------------------- | ------------------------------------------- |
| `oopsnote/core`     | Pydantic 模型、JSON store、资产、标签和搜索 |
| `oopsnote/content`  | OopsMark 解析、验证和导出适配               |
| `oopsnote/ai`       | 共享受管生命周期和 backend 协议             |
| `oopsnote/api`      | REST DTO、路由与应用组合                    |
| `oopsnote/mcp`      | AI 可调用的数据工具和 pipeline 写入边界     |
| `oopsnote/obsidian` | Core 到 Vault 的同步                        |
| `oopsnote/paper`    | 试卷模板与导出支持                          |
| `frontend`          | Next.js UI，只经 REST 访问 Core             |
| `skills`            | OCR、解题、验证、标签和编排指令的唯一源码   |

## 6. 配置与密钥

AppSettings 只保存非敏感 provider channel、模型目录、三阶段策略与 opaque credential reference。Windows 使用 Credential Manager；Linux/容器使用由只读挂载 master key 加密的持久化 vault。密钥明文绝不写入 `storage/`、TaskRun、日志、环境变量或 REST 响应。`.pi/extensions.json` 只为显式旧 Pi 后端保留；LangChain 与 OCR 不会把它作为 vault 失败的回退。

`.pi/skills/` 是 `skills/` 的生成镜像。修改 skill 后运行 `scripts/setup/setup_pi.py --sync`。

## 7. 两套阶段名称

为避免混淆，项目只使用以下两个命名空间：

- 产品里程碑：Core、Web、Obsidian、复习与出卷能力。
- AI 迁移阶段：Pi PoC、生产化、质量优化、Hermes 下线。

当前已完成 LangChain 受管执行路径与 SecretStore 迁移实现。运行证据由 RunStore 按 run 保留并由 REST 暴露非敏感索引；RustPi 删除仍等待隔离的真实任务评测门槛。

## 8. RustPi 删除门槛

LangChain 在隔离 storage 中完成至少 30 个真实任务且无丢失、重复 finalize 或无法取消；完成率不低于 95%，质量相对 RustPi 基线下降不超过 2 个百分点，P95 延迟恶化不超过 20%，成本门槛经实测 provider usage 批准后，才删除 `.pi-rust`、Pi auth 复制、RPC worker、JS bridge、安装脚本、相关 benchmark 与文档。Hermes 是否退役另行决定，Python MCP 与 `ManagedAiRunner` 继续保留。
