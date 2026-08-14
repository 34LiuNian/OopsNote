# OopsNote 部署

生产环境在 Linux 上以 Docker Compose 运行；本地开发以 Windows + VSCode 任务为主
（见根 `README.md` 与 `.vscode/tasks.json`）。

## Compose 文件

| 文件 | 用途 |
| --- | --- |
| `docker-compose.yml` | 生产（backend / frontend / latex-renderer；Pocket ID 位于 `oidc-rollback` profile） |
| `docker-compose.dev.yml` | 容器化本地开发（源码绑定挂载 + `--reload` 热更新） |
| `docker-compose.local.yml` | 本地认证模式覆盖：`docker compose -f docker-compose.yml -f docker-compose.local.yml ...` |
| `deploy/compose.bootstrap.yml` | 一次性引导（bootstrap secret，用于首次成员邀请/管理员引导） |
| `deploy/compose.oidc-rollback.yml` | OIDC（Pocket ID）回滚 profile：`docker compose --profile oidc-rollback ...` |

## 生产部署（从零开始）

1. 准备 Compose 上下文（以 `/opt/oopsnote` 为例）：克隆仓库后执行
   `scripts/deploy/sync_production_context.sh`（只同步构建输入，不覆盖 Compose
   文件与密钥）。
2. 环境变量：`cp .env.example .env`，填写 `OOPSNOTE_PUBLIC_URL`、OIDC 参数与
   `OOPSNOTE_ADMIN_SUBJECTS`。
3. 生成 secret：按 [deploy/oopsnote/secrets/README.md](oopsnote/secrets/README.md)
   生成；Pocket ID 见 [deploy/pocket-id/README.md](pocket-id/README.md)。
4. 启动并检查：

   ```sh
   docker compose up -d --build
   docker compose ps
   ```

5. 验证：

   - 后端健康检查 `curl http://127.0.0.1:8000/health`（backend 不对外暴露端口，
     由前端口径反代）。
   - 前端 `https://<OOPSNOTE_PUBLIC_URL>`。
   - `docker compose logs -f backend frontend`。

## 升级

```sh
git pull
./scripts/deploy/sync_production_context.sh
docker compose up -d --build   # 只重建有变更的服务，不动 Pocket ID 与数据卷
```

## 备份

- 数据卷：`oopsnote-data`（题库/任务）、`oopsnote-auth`（认证库）、
  `oopsnote-vault`（凭证库）。
- 密钥文件：`deploy/oopsnote/secrets/*`、`deploy/pocket-id/secrets/*`。丢失
  `credential_store_key` 或 Pocket ID 加密密钥会导致对应数据不可解密，必须与
  数据卷一起备份并妥善保管。

## 反向代理

公网入口由服务器上的 Caddy 承担，站点配置参考 `deploy/caddy/Caddyfile`。
域名通过环境变量注入，启动 Caddy 前设置（systemd `Environment=` 或 shell
export；1Panel 在应用环境变量中配置）：

- `OOPSNOTE_DOMAIN`：生产前端（反代 `127.0.0.1:13000`）
- `OOPSNOTE_DEV_DOMAIN`：开发前端（反代 `127.0.0.1:13001`）
- `OOPSNOTE_AUTH_DOMAIN`：认证入口（反代 `127.0.0.1:14110`）

Compose 内服务仅绑定回环或内部网络（`latex-internal` 为 `internal: true`）。
本地开发经反代域名访问时，还需在 `frontend/.env.local` 设置
`OOPSNOTE_DEV_ALLOWED_ORIGIN`（见 `frontend/.env.example`）。
