# OopsNote Compose secrets

`docker-compose.yml` 与 `docker-compose.dev.yml` 把本目录下的文件以 Docker
secret 挂载进容器。真实密钥被 `.gitignore` 忽略，仓库只提交 `*.example`
占位模板；部署前在服务器上生成真实文件（目录 0700、文件 0600）。

## 生产（docker-compose.yml）

| 文件 | 用途 |
| --- | --- |
| `better_auth_secret` | Better Auth 会话签名密钥（≥32 字节） |
| `bff_hmac_secret` | 前端 BFF → 后端请求 HMAC 密钥 |
| `credential_store_key` | SecretStore 凭证库主密钥（Fernet 兼容：32 随机字节的 urlsafe base64） |
| `bootstrap_secret` | 首次引导密钥：生产 Compose 常驻挂载，用户表为空时 `/setup` 可创建第一个管理员 |

## 开发（docker-compose.dev.yml）

`dev_better_auth_secret`、`dev_bff_hmac_secret`、`dev_bootstrap_secret`：同上。

## 首次启动自动生成（推荐）

在服务器 Compose 目录执行一次，`.env` 与所有缺失的 secret 文件会被自动生成
（幂等，已存在则跳过）：

```sh
./scripts/deploy/bootstrap.sh        # 或 make secrets
```

- `.env` 从 `.env.example` 复制（请按需修改 `OOPSNOTE_PUBLIC_URL`）。
- `credential_store_key` 由 shell 生成，与
  `EncryptedFileSecretStore.generate_key()`（`scripts/setup/init_secret_store.py`）
  等价（32 随机字节的 urlsafe base64），两者可互换。

## 手动生成（等价）

```sh
cd deploy/oopsnote/secrets
for name in better_auth_secret bff_hmac_secret bootstrap_secret \
            dev_better_auth_secret dev_bff_hmac_secret dev_bootstrap_secret; do
    [ -f "$name" ] || openssl rand -base64 32 > "$name"
    chmod 600 "$name"
done
openssl rand -base64 32 | tr '+/' '-_' > credential_store_key
chmod 600 credential_store_key
```

生成后确认 `docker compose config` 不再报 secret 文件缺失。
