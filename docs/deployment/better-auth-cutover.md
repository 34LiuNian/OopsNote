# Better Auth 切换与迁移

当前分支的生产切换仍需维护窗口执行。Pocket ID/OIDC 兼容模式保留到验收结束，不能把两个身份系统同时作为正常流量入口。

## 运行边界

- Next.js 持有 `auth.sqlite`、Better Auth session cookie 和管理员 API。
- FastAPI 只接受 Next.js BFF 签发的 HMAC 身份信封。
- FastAPI 的 `storage/control/app.sqlite` 持有 `user.id -> workspace_id`、额度和 run 控制状态。
- Caddy 只把公网流量转发到 Next.js；FastAPI 端口只绑定 loopback。

## 1Panel/Compose secrets

为 Next.js 准备以下 secret 文件，并挂载到容器：

```text
/run/secrets/oopsnote_better_auth_secret   # Better Auth session secret，至少 32 字节
/run/secrets/oopsnote_bff_hmac_secret      # BFF 与 FastAPI 共用，必须与后端一致
/run/secrets/oopsnote_bootstrap_secret     # 首位管理员初始化后不再可用
```

Next.js 环境至少设置：

```text
BETTER_AUTH_URL=https://oopsnote.alan-ztr.eu.org
OOPSNOTE_AUTH_DB_PATH=/data/auth/auth.sqlite
OOPSNOTE_BETTER_AUTH_SECRET_FILE=/run/secrets/oopsnote_better_auth_secret
OOPSNOTE_BFF_HMAC_SECRET_FILE=/run/secrets/oopsnote_bff_hmac_secret
OOPSNOTE_BOOTSTRAP_SECRET_FILE=/run/secrets/oopsnote_bootstrap_secret
NEXT_PUBLIC_AUTH_MODE=better-auth
```

FastAPI 环境至少设置：

```text
OOPSNOTE_AUTH_MODE=better-auth
OOPSNOTE_BFF_HMAC_SECRET_FILE=/run/secrets/oopsnote_bff_hmac_secret
OOPSNOTE_STORAGE_DIR=/data
```

`auth.sqlite` 和 `/data` 必须分别使用持久卷；不能把 Better Auth 数据库交给 Python 直接查询。

## 首位管理员

先部署但不要开放普通用户入口，然后只通过内网或临时维护访问调用：

```powershell
curl.exe -X POST https://oopsnote.alan-ztr.eu.org/api/admin/bootstrap `
  -H "x-oopsnote-bootstrap-secret: <至少32字节的secret>" `
  -H "content-type: application/json" `
  -d '{"email":"admin@example.com","name":"OopsNote Admin","password":"<至少12位密码>"}'
```

该接口在 Better Auth 已存在任意用户后返回 `409`，不会再次创建管理员。初始化完成后应从公网入口移除 bootstrap secret，或直接不再挂载该 secret 文件。

## 旧数据迁移

先停写并做卷快照，再运行只读报告：

```powershell
.venv\Scripts\python.exe scripts\migrate_multitenancy.py `
  --storage-dir storage `
  --admin-user-id <Better-Auth-user.id> `
  --report migration-report.json
```

只有报告中 `active_run_ids` 和 `invalid_files` 都为空时才允许：

```powershell
.venv\Scripts\python.exe scripts\migrate_multitenancy.py `
  --storage-dir storage `
  --admin-user-id <Better-Auth-user.id> `
  --apply
```

`warnings` 会列出历史孤立 run 或已丢失的旧资源；它们不计入新额度，但必须在切换验收记录中留档。脚本不会删除旧目录，回滚窗口结束前保留原始数据只读备份。

## 发布闸门

切换后必须验证：管理员登录、普通用户登录、A/B 题库和资源隔离、上传、AI 运行、重试、额度边界、禁用后现有 session 失效，以及服务重启后 queued run 恢复。全部通过后再把 `NEXT_PUBLIC_AUTH_MODE` 和 `OOPSNOTE_AUTH_MODE` 固定为 `better-auth`，并在连续稳定观察期结束后移除 Pocket ID/OIDC 兼容代码。
