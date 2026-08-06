# Better Auth、多用户隔离与内测额度实现规范

状态：待实现  
目标分支：`feat/auth-multitenancy`  
基线提交：`ffb845c`  
适用产品：独立部署的 OopsNote 封闭内测版

## 1. 目标与产品默认值

本次改造把 OopsNote 从“受 OIDC 保护的单用户应用”升级为“应用内部管理账号的多用户产品”。第一版只实现已经确认的需求：

- OopsNote 自己管理登录，不再要求用户理解或维护 Pocket ID。
- 只有 `admin` 和 `user` 两种角色。
- 管理员在 OopsNote 内创建邀请、查看成员、禁用或恢复成员、调整额度。
- 不开放公开注册；邀请链接一次性使用，初期不接 SMTP，由管理员复制链接发送。
- 每个用户拥有完全独立的题库、资产、批处理、试卷、标签和 AI 运行记录。
- 管理员默认也不能读取其他用户的题库内容。
- 默认额度为每个用户每天 20 次成功的 AI 处理，单用户最多 1 个并发 AI 任务。
- 失败或取消且未产生有效结果的任务释放预留额度；重试沿用原业务操作的幂等键，不重复扣费。
- 现有单用户数据在迁移时全部归属首个管理员。

第一版不实现组织、团队共享题库、复杂 RBAC、公开注册、付费订阅、第三方 SSO 和管理员代登录。这些能力不得以隐藏字段或未完成分支提前进入数据模型。

## 2. 必须始终成立的系统不变量

### 2.1 身份与账号

1. Better Auth 是账号、凭据、会话和 `admin | user` 角色的唯一真源。
2. Python 不直接读写 Better Auth 表，也不维护第二份封禁或角色状态。
3. 只有通过 Better Auth 校验的同源 HttpOnly 会话才能进入应用 API。
4. 禁用用户时必须撤销其会话；之后的每个新请求都应被拒绝。
5. 生产环境不存在 `local admin`、静态管理员 subject 或 OIDC 兼容旁路。

### 2.2 数据所有权

1. 每一份用户数据都归属一个不可变的 `workspace_id`。
2. 每个 Better Auth `user.id` 在应用控制库中最多映射一个工作区。
3. 外部请求只能取得当前身份对应的 `WorkspaceContext`，包括管理员请求。
4. Core 的用户数据 Store 必须从 `WorkspaceContext` 构造；调用者不能传任意磁盘路径。
5. 后台任务、重试、恢复和 MCP 调用必须从持久化 run 读取 `workspace_id`，不能读取进程级“当前用户”。
6. 资源不存在和资源属于其他用户，对外统一返回 404，避免资源枚举。

### 2.3 额度与任务生命周期

1. 额度检查、run 创建和额度预留在同一个 SQLite 事务中完成。
2. 一个 `idempotency_key` 最多产生一笔有效额度预留。
3. `reserved` 只能终结为 `consumed` 或 `released`，不能重复终结。
4. 启动恢复必须能处理“run 已入库、TaskRecord 尚未更新”的中断状态。
5. 重试是新的 run，但继承原始业务操作的额度预留；不能再次扣费。
6. 配额拒绝是确定性 admission failure，不进入 AI 队列，也不自动重试。

## 3. 当前状态与根因

当前代码已经能验证 Pocket ID OIDC token，但身份只停留在 FastAPI 请求边界：

- `oopsnote/api/main.py` 在模块加载时创建全局 `TASK_STORE`、`RUN_STORE`、`ASSET_STORE`、`TAG_STORE`、批处理 Store 和试卷 Store。
- `oopsnote/api/routes/` 中 6 个路由模块直接访问这些全局 Store，共有约 111 处引用。
- `TaskRecord`、`TaskRun`、`BatchSessionRecord` 和 `PaperDraft` 没有用户或工作区所有权。
- `oopsnote/mcp/server.py` 又独立创建了一组指向同一目录的全局 Store。
- `ManagedAiRunner` 和 dispatcher 只携带 `task_id`，启动恢复会扫描全局 `RunStore`。
- `/assets` 由 FastAPI 直接静态挂载；知道路径即可绕过资源所有权检查。
- Caddy 让大文件上传绕过 Next.js 直达 FastAPI。
- 前端把 OIDC bearer token 放在 `sessionStorage`，Next.js 只做无身份感知的 rewrite。

因此仅替换登录组件无法实现多用户安全。最早违反不变量的层是 Core Store/Managed lifecycle 的资源寻址方式；修复必须让工作区成为这些边界的必填上下文。

## 4. 目标架构

```text
Browser
  | same-origin HttpOnly session
  v
Next.js
  |-- Better Auth route /api/auth/*
  |-- account/admin/invite UI
  `-- authenticated streaming BFF /api/backend/*
         | short-lived request-bound HMAC identity envelope
         v
      FastAPI (Docker private network only)
         | Principal -> WorkspaceRegistry -> WorkspaceContext
         |                         |
         |                         `-> storage/workspaces/<workspace_id>/
         |                               tasks/assets/tags/batches/papers
         |
         `-> app.sqlite
              workspaces + runs + quota policies + usage reservations
                    |
                    v
              ManagedAiRunner -> restricted MCP
                    (persistent workspace_id + run_id)

auth.sqlite is owned only by Better Auth/Next.js.
app.sqlite and workspace files are owned only by FastAPI/Core.
```

### 4.1 权威边界

| 状态 | 唯一所有者 | 其他组件如何使用 |
| --- | --- | --- |
| 用户、凭据、会话、角色、封禁 | Better Auth `auth.sqlite` | Next.js 校验后签发内部身份信封 |
| 邀请 token 与兑换状态 | Next.js 邀请模块的 Node-owned 表 | 只在注册入口消费，不由 Python 访问 |
| `user.id -> workspace_id` | FastAPI `app.sqlite` | 首次合法请求幂等创建，之后不可变 |
| 用户题库和文件 | Core 工作区目录 | 只通过 `WorkspaceContext` Store 访问 |
| run 生命周期、并发 admission | Managed lifecycle + `app.sqlite` | REST/MCP 只能调用 lifecycle API |
| 额度政策和流水 | Quota service + `app.sqlite` | admission 事务预留，terminal transition 结算 |
| AI provider 配置和密钥 | 现有全局 AppSettings/SecretStore | 仅管理员管理，所有用户共享服务端策略 |

邀请表可以与 `auth.sqlite` 放在同一文件，但只能由 Node 侧迁移和访问。不得让 Python 为方便而直接查询 Better Auth 数据库。

## 5. 认证与 BFF 设计

### 5.1 Better Auth 配置

- 在 Next.js 中嵌入 Better Auth，不新增认证容器。
- 使用 SQLite 和固定版本依赖；提交 lockfile。
- 启用 admin 插件，角色枚举严格限制为 `admin | user`。
- 第一阶段使用“邀请页设置密码”的 email/password 登录；账号创建必须经过有效邀请。
- Passkey 作为后续同分支阶段：用户首次登录后可绑定；不能让 Passkey 阻塞基础邀请、恢复和管理员禁用流程。
- session cookie 使用 `HttpOnly`、`Secure`、`SameSite=Lax`，生产 cookie 只覆盖 OopsNote 域名。
- Better Auth secret 使用 Docker secret 文件，由 Next.js 服务端读取，不写进 Git 或浏览器可见环境变量。
- 关闭公开 sign-up。即使用户直接调用 Better Auth sign-up endpoint，没有有效且未消费的邀请也必须失败。

实现前先用最小 spike 锁定当前 Better Auth 版本及以下官方能力：Next.js handler、SQLite adapter/migration、admin create/ban/unban/revoke、server-side sign-up hook 和 Passkey 注册前置条件。spike 结论写入 ADR，不能把版本差异做成永久兼容分支。

### 5.2 邀请流程

1. 管理员输入邮箱、显示名、角色和初始额度。
2. 服务端生成 32 字节随机 token，只保存 `SHA-256(token)`，明文只在创建响应中返回一次。
3. 邀请记录包含 `expires_at`、`consumed_at`、`revoked_at`，默认 72 小时过期。
4. 用户打开 `/invite/<token>`，设置密码并完成注册。
5. 同一数据库事务锁定邀请并标记消费；重复、过期或撤销 token 返回稳定错误。
6. 注册成功后第一次进入 BFF，FastAPI 幂等创建工作区和默认额度政策。

如果 Better Auth 的公开注册 hook 不能在同一事务中消费邀请，则采用 Node 侧自定义认证插件/endpoint，让“校验邀请 + 创建账号 + 消费邀请”由同一所有者完成；不采用先创建账号再补标记的双写流程。

### 5.3 Next.js 到 FastAPI 的身份信封

Next.js BFF 在每次请求中调用 Better Auth 服务端 session API。有效会话转换为内部身份信封：

```json
{
  "v": 1,
  "user_id": "better-auth-user-id",
  "role": "admin",
  "issued_at": 1786032000,
  "request_id": "uuid",
  "method": "POST",
  "path": "/tasks"
}
```

- 信封 canonical JSON 后 base64url 编码，并以 HMAC-SHA256 签名。
- FastAPI 校验签名、版本、method/path 和不超过 30 秒的时间窗。
- BFF 删除浏览器传入的所有 `x-oopsnote-*` 头，再写入自己的头。
- HMAC key 使用独立 Docker secret，不能复用 Better Auth session secret。
- FastAPI 只监听 Docker 私网；移除生产 loopback 直达上传端口和 Caddy 特例。
- BFF 必须流式转发 request/response，覆盖大文件上传、SSE/流式日志、取消和普通 JSON。
- `/health` 可在容器网络匿名访问；所有资产改为鉴权 route，不再静态挂载整个目录。

## 6. 工作区与 Core 数据布局

### 6.1 控制库 `app.sqlite`

建议第一版 schema：

```text
schema_migrations
  version PK, applied_at

workspaces
  id PK, auth_user_id UNIQUE NOT NULL, created_at, legacy_imported_at

quota_policies
  workspace_id PK/FK, daily_success_limit, max_concurrent_runs, updated_at

runs
  id PK, workspace_id FK, task_id, purpose, status, retry_of,
  quota_reservation_id, queued_at, started_at, finished_at,
  payload_json
  UNIQUE(workspace_id, id)

usage_reservations
  id PK, workspace_id FK, operation, units, idempotency_key UNIQUE,
  state CHECK(reserved|consumed|released), root_run_id,
  usage_day_utc, created_at, finalized_at, reason
```

SQLite 开启 WAL、foreign keys 和 busy timeout。所有 schema 变更使用顺序 migration；应用启动不得静默重建数据库。

### 6.2 用户文件布局

```text
storage/
  control/app.sqlite
  workspaces/<workspace_id>/
    tasks/<task_id>.json
    assets/<asset_id>/...
    settings/tags_user.json
    settings/batch_sessions.json
    batch_jobs/
    papers/
    exports/
  settings/app_settings.json       # 全局管理员配置
```

实现 `WorkspaceRegistry` 和不可变 `WorkspaceContext`。上下文只接受数据库已登记的 UUID，不接受路径片段。`WorkspaceStores` 从安全拼接后的根目录一次性构造该用户的 Task/Asset/Tag/Batch/Paper Store。

### 6.3 Store 接口改造

- REST 路由通过 FastAPI dependency 获得 `RequestContext(principal, workspace, stores)`。
- 删除路由模块通过 `_api().TASK_STORE` 等访问用户数据的方式。
- 全局只保留确实属于全产品的 `AppSettingsStore`、SecretStore、内置知识树和 provider policy。
- Store 的公开 API 不再接受裸 `owner_id` 后自行过滤；调用者只能先取得正确的工作区 Store。
- `task_id`、`asset_id` 和 `paper_id` 的查询均限制在当前工作区目录。
- 资产由 `/assets/{asset_id}/{name}` 鉴权 route 返回；路径规范化后必须仍位于当前工作区资产根目录。
- Obsidian/Vault 同步在多用户版本中必须绑定工作区配置。未完成该隔离前，对非迁移管理员关闭同步入口，而不是继续使用全局 vault。

物理工作区隔离比给每个 JSON 记录补 `owner_id` 更可靠：漏掉一次查询过滤也无法扫描到其他工作区文件，并且便于单用户导出、备份和删除。

## 7. ManagedAiRunner、MCP 与额度

### 7.1 工作项身份

新增不可变 `ManagedWorkItem`：

```text
workspace_id + task_id + run_id + purpose + quota_reservation_id
```

- dispatcher 队列只接受 `ManagedWorkItem`，不再只接受 `task_id`。
- `ManagedAiRunner` 根据 `workspace_id` 从 registry 取得 WorkspaceStores。
- run 行持久化 `workspace_id`；启动恢复按 app.sqlite 的 queued/running 索引恢复，不扫描每个目录猜测所有者。
- retry 必须断言新 run 与原 run 的 `workspace_id` 一致。
- active control 的 key 使用 `(workspace_id, run_id)`，避免跨用户 ID 混淆。

### 7.2 MCP 边界

- 移除 `oopsnote/mcp/server.py` 的模块级用户 Store。
- Managed runner 为每个 MCP session 生成短期、单 run 的 capability token。
- capability 绑定 `workspace_id + task_id + run_id + allowed_tools + expires_at`。
- MCP 每个工具先验证 capability，再解析对应 WorkspaceStores。
- `get_task`、`get_asset_path`、标签创建、候选提交、finalize 和 fail 均断言 task/run/workspace 三者一致。
- MCP HTTP 服务继续由 shared runtime 托管，但 shared 只指进程，不代表共享用户状态。

### 7.3 原子 admission 与结算

`QuotaService.admit()` 使用 `BEGIN IMMEDIATE`：

1. 读取该工作区当天 `reserved + consumed` 单位和 active run 数。
2. 检查 daily limit 与 max concurrency。
3. 用 `idempotency_key` 幂等创建或复用 reservation。
4. 创建 queued run，并把 reservation id 写入 run。
5. 提交事务后更新 TaskRecord 的派生状态并投递队列。

如果第 5 步失败，立即把 run 标为 failed 并 release；如果进程在事务提交后崩溃，启动恢复根据 queued run 修复 TaskRecord 并重新投递。

终态规则：

| 结果 | reservation |
| --- | --- |
| 正常完成并持久化有效结果 | `consumed` |
| 用户在产生结果前取消 | `released` |
| 确定性校验失败且未产生有效结果 | `released` |
| provider 已调用但最终失败 | 第一版仍 `released`，同时记录 provider usage 供后续评估 |
| retry | 沿用原 reservation，不新增单位 |
| stale recovery 最终完成 | `consumed` |
| stale recovery 最终失败 | `released` |

所有 terminal transition 通过同一 lifecycle finalize API 结算。路由、backend adapter 和 MCP 不得直接修改额度流水。

## 8. 管理界面

新增 `/settings/members`，仅管理员可见：

- 成员列表：头像/显示名、邮箱、角色、状态、今日用量/上限、活动任务数、加入时间。
- 操作：创建邀请、复制邀请链接、撤销邀请、禁用/恢复用户、调整每日额度。
- 禁用和角色变更由 Next.js server action/route 调用 Better Auth admin API。
- 额度修改调用经过 BFF 的 FastAPI admin endpoint。
- 不展示“查看题库”或“以该用户身份登录”。
- 不能禁用最后一个可用管理员，也不能把最后一个管理员降为 user。
- 敏感操作写结构化审计事件，但不记录 token、密码、cookie 或题目内容。

普通用户账户菜单显示名称、邮箱、今日剩余额度、退出；Passkey 阶段再增加凭据管理页。

## 9. 迁移与发布

### 9.1 离线迁移工具

新增幂等命令，例如：

```powershell
.\.venv\Scripts\python.exe scripts\migrate_multitenancy.py --admin-user-id <id> --dry-run
.\.venv\Scripts\python.exe scripts\migrate_multitenancy.py --admin-user-id <id> --apply
```

步骤：

1. 检查无 active run，进入维护模式并备份 `oopsnote-data`、Pocket ID 数据和 Compose 配置。
2. dry-run 清点 task、run、asset、batch、paper 和 tags，校验引用与路径。
3. 创建首个管理员对应 workspace。
4. 将现有用户数据复制到临时工作区目录；重写必要的内部相对资产路径。
5. 把现有 TaskRun 导入 app.sqlite，并归属该 workspace；历史 run 不生成额度消费。
6. 对临时目录做完整引用校验和数量/哈希核对。
7. 原子 rename 为正式工作区；写入 migration marker。
8. 保留原目录为只读回滚快照，至少经过一次稳定发布和人工确认后再单独清理。

迁移不得边读边移动生产文件，也不得在校验失败后留下“部分用户化”的活动目录。

### 9.2 切换顺序

1. 部署包含 Better Auth 但尚未开放给用户的版本，创建首个管理员。
2. 维护窗口停止写入并运行迁移。
3. Caddy 只转发到 Next.js；FastAPI 取消宿主机公开/loopback映射。
4. 验证管理员登录、数据数量、资产读取、AI 完整流程、额度和禁用。
5. 开放第一批测试用户邀请。
6. Pocket ID 容器和 OIDC 配置保留一个短回滚窗口，但不再接收正常流量。
7. 稳定后移除 Pocket ID service、旧 OIDC 前端、PyJWT/JWKS 代码和相关 secrets。

禁止长期保留 OIDC/Better Auth 双运行模式。回滚窗口有明确删除条件：首批内测用户完成登录、上传、处理、重试、登出和禁用验收，且连续 7 天无身份/隔离事故。

## 10. 分阶段实施清单

### Phase 0：架构锁定与测试夹具（1-2 天）

- ADR：确认 Better Auth 版本、邀请 hook、SQLite migration、Passkey 前置条件。
- 定义 `Principal`、`WorkspaceId`、`WorkspaceContext`、`ManagedWorkItem`。
- 建立 app.sqlite migration runner 和临时数据库测试夹具。
- 建立 A/B 两用户的安全测试工厂。

完成标准：类型和数据库不变量测试通过；没有业务路由行为变化。

### Phase 1：Better Auth 与同源 BFF（2-4 天）

- 安装 Better Auth、SQLite adapter、admin plugin。
- 实现登录、退出、session、关闭公开注册和首个管理员 bootstrap。
- 实现 streaming BFF 与 HMAC 身份信封。
- FastAPI 改用内部身份 dependency；移除 sessionStorage bearer token。
- 将前端 API base 改为 `/api/backend`。
- 资产和大文件上传先通过 BFF 验证流式能力。

完成标准：伪造身份头、过期签名、method/path replay、无 session 请求全部失败；大文件和流式响应不被缓冲破坏。

### Phase 2：工作区 Core 隔离（4-7 天）

- WorkspaceRegistry/WorkspaceStores。
- 依次改造 tasks/assets、tags/catalog、batch、papers/study、exports/Obsidian。
- 删除全局用户 Store 和 `/assets` 静态挂载。
- 为资源读取/修改/删除增加 A/B 交叉测试。

完成标准：用户 B 对用户 A 的已知 ID 在列表、详情、修改、删除、搜索、资产和导出全部得到 404；磁盘路径也位于不同工作区。

### Phase 3：run 控制库、AI/MCP 与额度（4-7 天）

- RunStore SQLite 实现和 JSON run 迁移。
- dispatcher/ManagedAiRunner 全链路携带 ManagedWorkItem。
- MCP capability 与 WorkspaceStores 解析。
- 原子 admission、reservation state machine、重试和 stale recovery。
- 每用户并发 1 + 现有全局 worker 上限共同生效。

完成标准：并发请求不会超额；崩溃点测试可恢复；重试不重复扣费；MCP 不能跨 workspace 获取 task/asset。

### Phase 4：邀请与管理员界面（2-4 天）

- 邀请创建/兑换/撤销/过期。
- 成员列表、禁用/恢复、角色和额度。
- 最后管理员保护、审计事件和普通用户额度展示。
- 可选 Passkey 绑定与恢复流程。

完成标准：被禁用用户的现有 session 失效，不能继续 BFF 请求；邀请 token 只能使用一次；管理员不能访问其他成员题库。

### Phase 5：迁移、部署与内测闸门（3-5 天）

- dry-run/apply migration 和备份恢复演练。
- Compose、Docker secrets、Caddy 和运维文档更新。
- 生产影子数据迁移校验；维护窗口正式切换。
- 两个真实测试账号执行完整 E2E。
- 观察 7 天后删除 Pocket ID/OIDC 兼容代码。

完成标准：迁移计数与哈希一致；回滚演练可恢复；所有发布闸门有实际运行证据。

整体预计 3-5 周的工程量。Better Auth 本身不是主要工作，数据隔离、后台生命周期、迁移和安全验证占大头。实现可按 Phase 形成可审查提交，但在 Phase 2 完成前不能邀请第二个真实用户，在 Phase 3 完成前不能宣称额度可靠。

## 11. 验证矩阵

### 11.1 自动测试

- Better Auth：公开注册关闭、邀请消费、session 撤销、角色枚举、最后管理员保护。
- BFF：无 cookie、伪造头、过期签名、路径重放、上传、下载、SSE、取消。
- Workspace：A/B 对 task、problem、asset、tag、batch、paper、search、merge、sync 的读写删除。
- Lifecycle：重复 admission、并发 admission、进程中断、queued recovery、stale retry、cancel/finalize 竞争。
- Quota：零额度、边界 19/20/21、并发抢最后一单位、失败释放、重试复用、跨 UTC 日期。
- Migration：空库、重复 dry-run、重复 apply、损坏引用、部分临时目录、89+ tasks/大量历史 runs 的规模样本。

### 11.2 发布前手工验收

1. 管理员创建邀请并复制链接。
2. 用户 A 注册、登录、上传、完成 AI 处理、重试、查看额度、退出。
3. 用户 B 登录后看不到 A 的任何题目；即使粘贴 A 的 URL/asset URL 也返回 404。
4. 管理员能调整 B 的额度并禁用 B，但不能查看 B 的内容。
5. B 的已有标签页在下一次请求被拒绝，重新登录也失败。
6. 服务重启后 queued run、用量和用户数据保持一致。
7. 恢复备份后能回到切换前状态。

## 12. 主要风险与处理

| 风险 | 处理 |
| --- | --- |
| Next BFF 缓冲大文件或 SSE | Phase 1 先做流式 spike；未通过不进入 Core 改造 |
| Better Auth 邀请注册无法原子消费 | 由 Node 侧自定义插件拥有整个事务，不做跨服务双写 |
| 全局 Store 遗漏导致越权 | 物理工作区 Store + 删除全局用户 Store + A/B 测试 |
| 后台线程丢失当前用户 | ManagedWorkItem 和 run 行持久化 workspace_id |
| JSON Task 与 SQLite run 中断不一致 | run 为 lifecycle 真源；启动恢复修复派生 Task 状态 |
| SQLite 写竞争 | WAL、busy timeout、短事务、单 backend writer；压测后再考虑 PostgreSQL |
| 封禁状态在两处漂移 | 只由 Better Auth 保存封禁；Python 信任每请求新签发的 BFF 身份 |
| 迁移损坏现有题库 | copy-validate-atomic-rename，原数据只读保留至回滚窗口结束 |

## 13. 官方资料与版本锁定

- Better Auth Next.js integration: <https://www.better-auth.com/docs/integrations/next>
- SQLite adapter: <https://www.better-auth.com/docs/adapters/sqlite>
- Admin plugin: <https://www.better-auth.com/docs/plugins/admin>
- Passkey plugin: <https://www.better-auth.com/docs/plugins/passkey>
- Session management: <https://www.better-auth.com/docs/concepts/session-management>

文档链接只作为设计输入。实现以 lockfile 中固定版本和 Phase 0 contract tests 为准，升级 Better Auth 时先升级测试证据，不保留多版本运行时兼容代码。
