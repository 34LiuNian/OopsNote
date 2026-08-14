# OopsNote 部署

生产环境在 Linux 上以 Docker Compose 运行；本地开发以 Windows + VSCode 任务为主
（见根 `README.md` 与 `.vscode/tasks.json`）。

## Compose 文件

| 文件 | 用途 |
| --- | --- |
| `docker-compose.yml` | 生产（backend / frontend / latex-renderer，认证默认 Better Auth） |
| `docker-compose.dev.yml` | 容器化本地开发（源码绑定挂载 + `--reload` 热更新） |
| `docker-compose.local.yml` | 本地认证模式覆盖：`docker compose -f docker-compose.yml -f docker-compose.local.yml ...` |
| `deploy/compose.bootstrap.yml` | 一次性引导：挂载 bootstrap secret，使 `/setup` 引导页可用（创建第一个管理员） |

## 生产部署（从零开始）

1. 准备 Compose 上下文（以 `/opt/oopsnote` 为例）：克隆仓库后执行
   `scripts/deploy/sync_production_context.sh`（只同步构建输入，不覆盖 Compose
   文件与密钥）。
2. 环境变量与密钥：执行 `./scripts/deploy/bootstrap.sh`（或 `make secrets`）——
   自动从模板生成 `.env` 与全部 secret 文件；随后编辑 `.env` 填写
   `OOPSNOTE_PUBLIC_URL`（认证默认 Better Auth，无需其它认证配置）。
3. 启动并检查：

   ```sh
   docker compose up -d --build
   docker compose ps
   ```

4. 验证：

   - 后端健康检查 `curl http://127.0.0.1:8000/health`（backend 不对外暴露端口，
     由前端口径反代）。
   - 前端 `https://<OOPSNOTE_PUBLIC_URL>`。
   - `docker compose logs -f backend frontend`。

5. 首次进入网页完成引导（创建第一个管理员）：

   ```sh
   docker compose -f docker-compose.yml -f deploy/compose.bootstrap.yml up -d frontend
   ```

   然后浏览器打开 `https://<OOPSNOTE_PUBLIC_URL>/setup`，填表创建管理员账号。
   完成后立即移除该 override（`docker compose up -d frontend`），引导页即随
   bootstrap secret 一起失效。

## 升级

```sh
git pull
./scripts/deploy/sync_production_context.sh
docker compose up -d --build   # 只重建有变更的服务，不动数据卷
```

## 备份

- 数据卷：`oopsnote-data`（题库/任务）、`oopsnote-auth`（认证库）、
  `oopsnote-vault`（凭证库）。
- 密钥文件：`deploy/oopsnote/secrets/*`。丢失 `credential_store_key` 会导致
  凭证库不可解密，必须与数据卷一起备份并妥善保管。

## 反向代理

公网入口由服务器上的 Caddy 承担，站点配置参考 `deploy/caddy/Caddyfile`。
域名通过环境变量注入，启动 Caddy 前设置（systemd `Environment=` 或 shell
export；1Panel 在应用环境变量中配置）：

- `OOPSNOTE_DOMAIN`：生产前端（反代 `127.0.0.1:13000`）
- `OOPSNOTE_DEV_DOMAIN`：开发前端（反代 `127.0.0.1:13001`）

Compose 内服务仅绑定回环或内部网络（`latex-internal` 为 `internal: true`）。
本地开发经反代域名访问时，还需在 `frontend/.env.local` 设置
`OOPSNOTE_DEV_ALLOWED_ORIGIN`（见 `frontend/.env.example`）。
