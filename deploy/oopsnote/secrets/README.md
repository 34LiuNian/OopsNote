# OopsNote Compose secrets

`docker-compose.yml`、`docker-compose.dev.yml` 与 `deploy/compose.bootstrap.yml`
把本目录下的文件以 Docker secret 挂载进容器。真实密钥被 `.gitignore` 忽略，
仓库只提交 `*.example` 占位模板；部署前在服务器上生成真实文件（目录 0700、
文件 0600）。

## 生产（docker-compose.yml）

| 文件 | 用途 | 生成方式 |
| --- | --- | --- |
| `better_auth_secret` | Better Auth 会话签名密钥（≥32 字节） | `openssl rand -base64 32` |
| `bff_hmac_secret` | 前端 BFF → 后端请求 HMAC 密钥 | `openssl rand -base64 32` |
| `credential_store_key` | SecretStore 凭证库主密钥 | `python scripts/setup/init_secret_store.py`（幂等，不回显密钥，格式由项目保证） |
| `bootstrap_secret` | `deploy/compose.bootstrap.yml` 一次性引导密钥 | `openssl rand -base64 32` |

## 开发（docker-compose.dev.yml）

`dev_better_auth_secret`、`dev_bff_hmac_secret`、`dev_bootstrap_secret`：
生成方式同上（`openssl rand -base64 32`）。

## 服务器上生成示例

```sh
cd /opt/oopsnote/deploy/oopsnote/secrets
for name in better_auth_secret bff_hmac_secret bootstrap_secret \
            dev_better_auth_secret dev_bff_hmac_secret dev_bootstrap_secret; do
    [ -f "$name" ] || openssl rand -base64 32 > "$name"
    chmod 600 "$name"
done
# SecretStore 主密钥：在安装了 oopsnote 的环境中执行（幂等，已存在则跳过）
python /opt/oopsnote/scripts/setup/init_secret_store.py
```

生成后确认 `docker compose config` 不再报 secret 文件缺失。
