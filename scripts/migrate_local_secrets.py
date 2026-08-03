"""Explicit one-time legacy OCR credential import into Windows Credential Manager."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from oopsnote.ai.secrets import WindowsCredentialManagerSecretStore


def migrate(path: Path, *, store=None) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    config = payload.get("ocr_image") if isinstance(payload, dict) else None
    if not isinstance(config, dict):
        raise ValueError("legacy config has no ocr_image section")
    secret = config.get("dashscope_api_key")
    if not isinstance(secret, str) or not secret:
        raise ValueError("legacy config has no DashScope credential")
    reference = (store or WindowsCredentialManagerSecretStore()).put(secret)
    # This is an opaque reference, not a secret value.
    return {"credential_ref": reference}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    result = migrate(parser.parse_args().path)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
