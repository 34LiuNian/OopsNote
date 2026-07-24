# OopsNote architecture

状态：当前实现基线
更新：2026-07-22

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
PiRpcRunner               HermesRunner
(default)                 (temporary fallback)
   |
Pi JSONL RPC process, one long-lived serial worker
   |-- ocr_image extension -> DashScope vision model
   `-- pi-mcp-adapter -> restricted Python MCP -> Core stores
```

共享生命周期只由 `ManagedAiRunner` 管理：run 所有权、heartbeat、timeout、abort、陈旧任务恢复、日志、重试资格和 finalize 后检查。Backend 只负责具体进程协议。

Pi 使用 `--no-builtin-tools --no-extensions` 启动，再显式加载 OCR Extension 和固定版本 MCP Adapter。进程长期存活并串行处理任务；每个任务前必须等待 `new_session` 成功，以隔离上下文。

正常任务复用同一进程，因此 MCP Adapter 的共享缓存只在 worker 启动时初始化。跨 API 进程的启动锁仅保护这段初始化；超时、session 重置失败或进程异常退出会销毁 worker，下一个任务再启动新进程。取消通过 RPC `abort` 完成，不关闭健康的共享 worker。

## 3. 数据与写入边界

```text
AI runtime -> restricted MCP -> Core -> storage/*.json
                                    -> storage/assets/
                                    -> vaults/ (explicit sync)
Frontend   -> REST ----------> Core
```

- AI 不能直接读写 `storage/`。
- Web pipeline 只开放 `get_task`、`get_asset_path`、`list_tags`、`create_tag`、`report_task_stage`、`finalize_task`、`fail_task`。
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

仓库跟踪 `.pi/package*.json`、`mcp.json`、Extension 源码与配置示例。本机运行命令在 `.pi/runtime.json`，OCR 密钥与模型在 `.pi/extensions.json`，DeepSeek 鉴权由 Pi 本地 auth 保存。这些本机文件不提交，也不要求以环境变量作为默认密钥方案。

`.pi/skills/` 是 `skills/` 的生成镜像。修改 skill 后运行 `scripts/setup/setup_pi.py --sync`。

## 7. 两套阶段名称

为避免混淆，项目只使用以下两个命名空间：

- 产品里程碑：Core、Web、Obsidian、复习与出卷能力。
- AI 迁移阶段：Pi PoC、生产化、质量优化、Hermes 下线。

当前处于 AI 迁移阶段 2 完成后的生产验证期；下一步进入质量优化前的故障注入与真实任务观察。

## 8. Hermes 下线门槛

Pi 默认运行满 7 天，至少 30 个真实任务无丢失、重复 finalize 或无法取消；成功率不低于 95%，质量相对 Hermes 下降不超过 2 个百分点，P95 延迟恶化不超过 20%，故障注入测试全部通过后，删除 Hermes backend、安装脚本与专属文档。Python MCP 继续保留。
