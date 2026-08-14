"""Shared test baseline: API 回归测试以显式 local 认证模式运行。

历史原因：大量 API 回归测试以未认证请求直接调用路由，依赖旧的“默认 oidc
且未配置 issuer 时回环视为管理员”行为。现在默认模式是 better-auth（未认证
请求一律拒绝），因此把测试基线显式固定为 local 模式；需要其它模式的测试
自行 patch 环境变量（patch.dict 会覆盖本基线并在测试后恢复）。
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _local_auth_baseline(monkeypatch):
    monkeypatch.setenv("OOPSNOTE_AUTH_MODE", "local")
