#!/usr/bin/env sh
# OopsNote 首次启动引导：自动生成 .env 与全部 secret 文件（幂等，可重复执行）。
# 在服务器 Compose 目录（如 /opt/oopsnote）执行一次即可。
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
secrets_dir="$project_root/deploy/oopsnote/secrets"

# 1. .env：从模板复制（已存在则跳过；请按需修改 OOPSNOTE_PUBLIC_URL）。
if [ ! -f "$project_root/.env" ]; then
    cp "$project_root/.env.example" "$project_root/.env"
    echo "created $project_root/.env"
fi

# 2. 认证与 BFF 密钥：随机 32 字节 base64，权限 600。
mkdir -p "$secrets_dir"
chmod 700 "$secrets_dir"

for name in better_auth_secret bff_hmac_secret bootstrap_secret \
            dev_better_auth_secret dev_bff_hmac_secret dev_bootstrap_secret; do
    if [ ! -f "$secrets_dir/$name" ]; then
        openssl rand -base64 32 | tr -d '\n' > "$secrets_dir/$name"
        chmod 600 "$secrets_dir/$name"
        echo "created $secrets_dir/$name"
    fi
done

# 3. SecretStore 主密钥：32 随机字节的 urlsafe base64（44 字符，Fernet 兼容），
#    与 EncryptedFileSecretStore.generate_key() 等价。
#    等价替代：在安装了 oopsnote 的环境中执行 scripts/setup/init_secret_store.py。
if [ ! -f "$secrets_dir/credential_store_key" ]; then
    openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n' > "$secrets_dir/credential_store_key"
    chmod 600 "$secrets_dir/credential_store_key"
    echo "created $secrets_dir/credential_store_key"
fi

echo "首启引导完成。编辑 $project_root/.env 后执行："
echo "  docker compose up -d --build"
echo "创建第一个管理员："
echo "  docker compose -f docker-compose.yml -f deploy/compose.bootstrap.yml up -d frontend"
echo "然后访问 https://<你的域名>/setup 完成网页引导。"
