# Security Policy

## Supported versions

只有 `main` 分支的最新提交受支持。历史 tag 不提供安全修复。

## Reporting a vulnerability

请通过 [GitHub Security Advisory](https://github.com/34LiuNian/OopsNote/security/advisories/new)
私下报告，或邮件联系维护者（ztianrui454@gmail.com）。请不要在公开 issue 中
披露可复现细节；我们会在确认后尽快修复并发布公告。

## Security posture

- 模型与 OCR 凭证只通过 OopsNote SecretStore 解析（Windows Credential Manager
  或加密的容器 vault + 文件挂载主密钥），不写入环境变量、日志或响应。
- 仓库不包含任何真实密钥；`deploy/oopsnote/secrets/` 只提交 `*.example`
  占位模板，真实文件由 `scripts/deploy/bootstrap.sh` 在服务器上生成（0600）。
- 首次管理员创建（`/setup` 引导页）仅在用户表为空时可用，且创建动作是一次
  性原子 claim；创建完成后引导页自动关闭，无需手动摘除。
- 后端仅接受由 Better Auth BFF 用 HMAC 签发的内部身份请求；前端与后端共享
  的 HMAC 密钥独立于会话密钥。
- 若发现密钥泄露：轮换对应 secret（`bootstrap.sh` 只会生成缺失文件，轮换需
  手动生成新值并重启服务），并检查 `oopsnote_auth_audit` 审计日志。

## Disclosure process

1. 私密报告 → 确认与复现；
2. 修复并在 `main` 提交（含回归测试）；
3. 发布公告与升级说明。
