"""One-time import of legacy Pi model/OCR credentials into OopsNote SecretStore."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from oopsnote.ai.providers import ChannelModel, ProviderChannel
from oopsnote.ai.secrets import SecretStore, secret_store_from_environment
from oopsnote.core import AppSettingsStore


def _payload(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"legacy configuration must be an object: {path}")
    return value


def _next_version(settings: AppSettingsStore, channel_id: str) -> int:
    previous = next((item for item in settings.provider_channels() if item.id == channel_id), None)
    return previous.version + 1 if previous else 1


def import_model_channel(
    path: Path,
    *,
    store: SecretStore,
    settings: AppSettingsStore,
    channel_id: str,
    provider: str,
    model: str,
    base_url: str,
) -> ProviderChannel:
    provider_config = _payload(path).get(provider)
    secret = provider_config.get("key") if isinstance(provider_config, dict) else None
    if not isinstance(secret, str) or not secret:
        raise ValueError(f"legacy auth has no {provider}.key credential")
    reference = store.put(secret)
    try:
        now = datetime.now(timezone.utc)
        channel = ProviderChannel(
            id=channel_id,
            version=_next_version(settings, channel_id),
            display_name=channel_id,
            provider=provider,
            base_url=base_url,
            credential_ref=reference,
            models=(ChannelModel(id=model, source=provider),),
            created_at=now,
            updated_at=now,
        )
        settings.upsert_provider_channel(channel)
    except Exception:
        store.delete(reference)
        raise
    return channel


def import_ocr_channel(
    path: Path,
    *,
    store: SecretStore,
    settings: AppSettingsStore,
    channel_id: str,
) -> ProviderChannel:
    config = _payload(path).get("ocr_image")
    if not isinstance(config, dict):
        raise ValueError("legacy config has no ocr_image section")
    secret = config.get("dashscope_api_key")
    model = config.get("model")
    base_url = config.get("endpoint")
    if not isinstance(secret, str) or not secret:
        raise ValueError("legacy config has no DashScope credential")
    if not isinstance(model, str) or not model:
        raise ValueError("legacy OCR config has no model")
    if not isinstance(base_url, str) or not base_url:
        raise ValueError("legacy OCR config has no endpoint")
    reference = store.put(secret)
    try:
        now = datetime.now(timezone.utc)
        channel = ProviderChannel(
            id=channel_id,
            version=_next_version(settings, channel_id),
            display_name=channel_id,
            provider="openai-compatible",
            base_url=base_url,
            credential_ref=reference,
            models=(ChannelModel(id=model, source="DashScope"),),
            created_at=now,
            updated_at=now,
        )
        settings.upsert_provider_channel(channel)
    except Exception:
        store.delete(reference)
        raise
    return channel


def migrate(path: Path, *, store: SecretStore | None = None) -> dict[str, str]:
    """Backward-compatible OCR-only helper used by local migration callers."""
    config = _payload(path).get("ocr_image")
    if not isinstance(config, dict):
        raise ValueError("legacy config has no ocr_image section")
    secret = config.get("dashscope_api_key")
    if not isinstance(secret, str) or not secret:
        raise ValueError("legacy config has no DashScope credential")
    reference = (store or secret_store_from_environment()).put(secret)
    return {"credential_ref": reference}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--pi-auth", type=Path)
    parser.add_argument("--channel-id", default="deepseek-primary")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--ocr-config", type=Path)
    parser.add_argument("--ocr-channel-id", default="dashscope-ocr")
    args = parser.parse_args()
    if args.pi_auth is None and args.ocr_config is None:
        parser.error("at least one of --pi-auth or --ocr-config is required")
    store = secret_store_from_environment()
    settings = AppSettingsStore(args.settings)
    channels: list[ProviderChannel] = []
    if args.pi_auth is not None:
        channels.append(import_model_channel(
            args.pi_auth,
            store=store,
            settings=settings,
            channel_id=args.channel_id,
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
        ))
    if args.ocr_config is not None:
        channels.append(import_ocr_channel(
            args.ocr_config,
            store=store,
            settings=settings,
            channel_id=args.ocr_channel_id,
        ))
    print(json.dumps({
        "channels": [
            channel.model_dump(mode="json", exclude={"credential_ref"})
            for channel in channels
        ]
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
