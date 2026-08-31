# OopsNote 部署

生产环境在 Linux 上以 Docker Compose 运行；本地开发以 Windows + VSCode 任务为主
（见根 `README.md` 与 `.vscode/tasks.json`）。

## Compose 文件

| 文件 | 用途 |
| --- | --- |
| `docker-compose.yml` | 生产（backend / frontend / latex-renderer，认证默认 Better Auth）。默认从源码构建；保留给需要服务器本地构建的场景 |
| `deploy/compose.images.yml` | 预构建镜像覆盖：把三个服务的 `build:` 替换为 GHCR 镜像，服务器免构建部署 |
| `docker-compose.dev.yml` | 容器化本地开发（源码绑定挂载 + `--reload` 热更新） |
| `docker-compose.local.yml` | 本地认证模式覆盖：`docker compose -f docker-compose.yml -f docker-compose.local.yml ...` |

镜像由 GitHub Actions 在每次 push 到 `main` 时自动构建并发布到 GHCR
（tag `main` 跟随最新，`main-<短sha>` 可用于回滚；见
`.github/workflows/ci.yml` 的 `docker` job）。

## 生产部署（从零开始）

以 `/opt/oopsnote` 为例：

1. 准备 Compose 文件与部署脚本：克隆仓库（或只拷贝
   `docker-compose*.yml`、`deploy/`、`scripts/deploy/`）。**不再需要**在服务器
   同步源码或执行 `sync_production_context.sh`——镜像来自 GHCR。
2. 环境变量与密钥：执行 `./scripts/deploy/bootstrap.sh`（或 `make secrets`）——
   幂等生成 `.env` 与全部 secret 文件；随后编辑 `.env` 填写
   `OOPSNOTE_PUBLIC_URL`（认证默认 Better Auth，无需其它认证配置）。
3. 拉取镜像并启动：

   ```sh
   docker compose -f docker-compose.yml -f deploy/compose.images.yml pull
   docker compose -f docker-compose.yml -f deploy/compose.images.yml up -d
   docker compose ps
   ```

   服务器上没有任何构建步骤（`next build` 的内存峰值与 texlive 大基础镜像
   都由 GitHub Actions 承担）。国内主机请在 Docker daemon 配置镜像加速器。

4. 验证：

   - `curl http://127.0.0.1:13000/health`（backend 不对外暴露端口，经前端反代）。
   - 前端 `https://<OOPSNOTE_PUBLIC_URL>`。
   - `docker compose logs -f backend frontend`。

5. 首次进入网页完成引导（创建第一个管理员）：

   浏览器打开 `https://<OOPSNOTE_PUBLIC_URL>/setup`，填表创建管理员账号。
   引导页仅在用户表为空时可达，创建完成后自动关闭（再次访问回到登录页）。
   登录页也会在引导可用时显示「初始化管理员」入口。

## 升级与回滚

```sh
git pull                                   # 仅当需要更新 Compose 文件/部署脚本
docker compose -f docker-compose.yml -f deploy/compose.images.yml pull
docker compose -f docker-compose.yml -f deploy/compose.images.yml up -d
```

只替换镜像，不动数据卷。代码变更只需 push 到 `main`，等 CI 构建完成后在服务器
重复上述命令即可。

回滚：把 `deploy/compose.images.yml` 里的 `:main` 改成 `:main-<短sha>`
（目标版本），再 `pull` + `up -d`。

需要服务器本地构建时（例如临时改动未发布），去掉 `compose.images.yml`
覆盖，在服务器克隆完整源码后执行 `docker compose up -d --build`。

## 密钥与配置同步

镜像只包含代码。以下内容变更仍需手动同步到服务器：`docker-compose*.yml`、
`deploy/`（secrets、Caddyfile、Dockerfile）、`.env`。

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
