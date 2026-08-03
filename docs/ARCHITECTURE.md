# OopsNote architecture

状态：LangChain 迁移中
更新：2026-08-03

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
ProviderClientFactory -> Windows Credential Manager SecretStore
   |
restricted MCP HTTP -> OCR + pipeline tools -> Core stores
```

共享生命周期只由 `ManagedAiRunner` 管理：run 所有权、heartbeat、timeout、abort、陈旧任务恢复、日志、重试资格和 finalize 后检查。Backend 只负责具体进程协议。

默认运行时是 LangChain 的显式 provider adapter。每次 run 固定其 profile snapshot，solver 与 verifier 使用独立上下文，最多 24 轮受限 MCP tool loop。Pi 与 Hermes 仅可由显式 backend 选择用于诊断，任一 run 都不得自动切换。

正常任务复用三个有界 worker 进程。超时、session 重置失败或异常退出只销毁对应 worker；取消通过 RPC `abort` 完成，不关闭健康 worker。持久化队列先写入 `TaskRun`，应用重启后恢复 `queued` run，遗失的 `running` run 以 fresh retry 处理。

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
- 瞬时网络或限流错误最多产生两个全新 Pi retry run。

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

AppSettings 只保存非敏感 provider profile 与 opaque credential reference。密钥位于 Windows Credential Manager，绝不写入 `storage/`、TaskRun、日志、环境变量或 REST 响应。`.pi/extensions.json` 只为显式旧 Pi 后端保留；LangChain 与 OCR 不会把它作为 vault 失败的回退。

`.pi/skills/` 是 `skills/` 的生成镜像。修改 skill 后运行 `scripts/setup/setup_pi.py --sync`。

## 7. 两套阶段名称

为避免混淆，项目只使用以下两个命名空间：

- 产品里程碑：Core、Web、Obsidian、复习与出卷能力。
- AI 迁移阶段：Pi PoC、生产化、质量优化、Hermes 下线。

当前已完成 Rust 接入、真实 OCR-to-finalize smoke 与三 worker 并发验证，运行证据由 RunStore 按 run 保留并由 REST 暴露非敏感索引，进入 Hermes 下线前的生产观察期。

## 8. Hermes 下线门槛

pi_agent_rust 默认运行满 7 天，至少 30 个真实任务无丢失、重复 finalize 或无法取消；成功率不低于 95%，质量相对 Hermes 下降不超过 2 个百分点，P95 延迟恶化不超过 20%，故障注入测试全部通过后，删除 Hermes backend、安装脚本与专属文档。Python MCP 继续保留。
