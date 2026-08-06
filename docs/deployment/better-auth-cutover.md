# Better Auth 切换与迁移

当前分支的生产切换仍需维护窗口执行。Pocket ID/OIDC 兼容模式保留到验收结束，不能把两个身份系统同时作为正常流量入口。

## 运行边界

- Next.js 持有 `auth.sqlite`、Better Auth session cookie 和管理员 API。
- FastAPI 只接受 Next.js BFF 签发的 HMAC 身份信封。
- FastAPI 的 `storage/control/app.sqlite` 持有 `user.id -> workspace_id`、额度和 run 控制状态。
- Caddy 只把公网流量转发到 Next.js；FastAPI 不发布 host 端口，只存在于 Compose `app` 网络。

切换时必须把服务器 `/opt/1panel/apps/caddy/caddy/data/conf/Caddyfile` 的 OopsNote 站点同步为 `deploy/caddy/Caddyfile`，并 reload Caddy。旧的批量上传直连 FastAPI 规则不能保留；新版 BFF 会流式转发上传并绑定用户身份。

## 1Panel/Compose secrets

在服务器仓库的 `deploy/oopsnote/secrets/` 创建以下文件，内容使用独立的随机值且不提交 Git：

```text
better_auth_secret   # Better Auth session secret，至少 32 字节
bff_hmac_secret      # BFF 与 FastAPI 共用，必须与后端一致
bootstrap_secret     # 只在初始化首位管理员时临时挂载
```

```bash
install -d -m 700 deploy/oopsnote/secrets
openssl rand -hex 32 > deploy/oopsnote/secrets/better_auth_secret
openssl rand -hex 32 > deploy/oopsnote/secrets/bff_hmac_secret
openssl rand -hex 32 > deploy/oopsnote/secrets/bootstrap_secret
chmod 600 deploy/oopsnote/secrets/*
```

Next.js 环境至少设置：

```text
BETTER_AUTH_URL=https://oopsnote.alan-ztr.eu.org
OOPSNOTE_AUTH_DB_PATH=/auth/auth.sqlite
OOPSNOTE_BETTER_AUTH_SECRET_FILE=/run/secrets/oopsnote_better_auth_secret
OOPSNOTE_BFF_HMAC_SECRET_FILE=/run/secrets/oopsnote_bff_hmac_secret
NEXT_PUBLIC_AUTH_MODE=better-auth
```

FastAPI 环境至少设置：

```text
OOPSNOTE_AUTH_MODE=better-auth
OOPSNOTE_BFF_HMAC_SECRET_FILE=/run/secrets/oopsnote_bff_hmac_secret
OOPSNOTE_STORAGE_DIR=/data
```

Compose 已将 `auth.sqlite` 放在独立的 `oopsnote-auth` 持久卷，并把应用数据放在 `oopsnote-data`；不能把 Better Auth 数据库交给 Python 直接查询。`bff_hmac_secret` 同时挂载给前后端，但认证密钥只挂载给前端。

## 首位管理员

进入维护窗口后先停止前后端写入，并为 `oopsnote-data`、`oopsnote-vault` 和 `oopsnote-auth`（若已存在）做快照。构建镜像后，仅启动前端并使用临时 bootstrap override；该文件只给前端挂载 bootstrap secret：

```bash
docker compose build frontend backend
docker compose stop frontend backend
docker compose -f docker-compose.yml -f deploy/compose.bootstrap.yml up -d --no-deps frontend
```

然后只通过维护访问调用：

```powershell
curl.exe -X POST https://oopsnote.alan-ztr.eu.org/api/admin/bootstrap `
  -H "x-oopsnote-bootstrap-secret: <至少32字节的secret>" `
  -H "content-type: application/json" `
  -d '{"email":"admin@example.com","name":"OopsNote Admin","password":"<至少12位密码>"}'
```

该接口在 Better Auth 已存在任意用户后返回 `409`，不会再次创建管理员。保存响应中的 `user.id` 作为旧数据迁移目标。初始化完成后立即不用 override 重建前端，从容器中移除 bootstrap secret：

```bash
docker compose up -d --no-deps --force-recreate frontend
```

普通内测用户由管理员在 `/settings/members` 生成 72 小时单次邀请链接。不要通过公开注册接口创建用户。

## 旧数据迁移

保持后端停止，前端仅用于认证初始化；使用新版后端镜像对 `oopsnote-data` 卷运行只读报告：

```bash
docker compose run --rm --no-deps backend \
  python /app/scripts/migrate_multitenancy.py \
  --storage-dir /data \
  --admin-user-id '<Better-Auth-user.id>' \
  --report /data/migration-report.json
```

只有报告中 `active_run_ids` 和 `invalid_files` 都为空时才允许：

```bash
docker compose run --rm --no-deps backend \
  python /app/scripts/migrate_multitenancy.py \
  --storage-dir /data \
  --admin-user-id '<Better-Auth-user.id>' \
  --apply
```

`warnings` 会列出历史孤立 run 或已丢失的旧资源；它们不计入新额度，但必须在切换验收记录中留档。脚本不会删除旧目录，回滚窗口结束前保留原始数据只读备份。

迁移成功后启动应用；Pocket ID 因 profile 默认保持停止：

```bash
docker compose up -d --no-deps backend frontend
docker compose --profile oidc-rollback stop pocket-id
docker compose ps
```

若发布闸门失败，先恢复数据卷快照，再使用显式 OIDC override 重建前后端并启动 Pocket ID：

```bash
docker compose --profile oidc-rollback \
  -f docker-compose.yml \
  -f deploy/compose.oidc-rollback.yml \
  up -d --build frontend backend pocket-id
```

## 发布闸门

切换后必须验证：管理员登录、邀请单次兑换、普通用户登录、A/B 题库和资源隔离、上传、AI 运行、重试、额度边界、禁用后现有 session 失效，以及服务重启后 queued run 恢复。全部通过后继续观察；Pocket ID 服务默认不启动，只能通过 `oidc-rollback` profile 和专用 override 回滚。稳定观察期结束后再移除 Pocket ID/OIDC 兼容代码和旧数据卷。
