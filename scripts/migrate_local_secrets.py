"""One-time import of legacy Pi model/OCR credentials into OopsNote SecretStore."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from oopsnote.ai.providers import ProviderProfile
from oopsnote.ai.secrets import SecretStore, secret_store_from_environment
from oopsnote.core import AppSettingsStore


def _payload(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"legacy configuration must be an object: {path}")
    return value


def _next_version(settings: AppSettingsStore, profile_id: str) -> int:
    previous = next((item for item in settings.provider_profiles() if item.id == profile_id), None)
    return previous.version + 1 if previous else 1


def import_model_profile(
    path: Path,
    *,
    store: SecretStore,
    settings: AppSettingsStore,
    profile_id: str,
    provider: str,
    model: str,
    base_url: str,
) -> ProviderProfile:
    provider_config = _payload(path).get(provider)
    secret = provider_config.get("key") if isinstance(provider_config, dict) else None
    if not isinstance(secret, str) or not secret:
        raise ValueError(f"legacy auth has no {provider}.key credential")
    reference = store.put(secret)
    try:
        profile = ProviderProfile(
            id=profile_id,
            version=_next_version(settings, profile_id),
            provider=provider,
            model=model,
            base_url=base_url,
            credential_ref=reference,
        )
        settings.activate_provider_profile(profile)
    except Exception:
        store.delete(reference)
        raise
    return profile


def import_ocr_profile(
    path: Path,
    *,
    store: SecretStore,
    settings: AppSettingsStore,
    profile_id: str,
) -> ProviderProfile:
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
        profile = ProviderProfile(
            id=profile_id,
            version=_next_version(settings, profile_id),
            provider="openai-compatible",
            model=model,
            base_url=base_url,
            credential_ref=reference,
        )
        settings.activate_ocr_profile(profile)
    except Exception:
        store.delete(reference)
        raise
    return profile


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
    parser.add_argument("--profile-id", default="deepseek-primary")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--ocr-config", type=Path)
    parser.add_argument("--ocr-profile-id", default="dashscope-ocr")
    args = parser.parse_args()
    if args.pi_auth is None and args.ocr_config is None:
        parser.error("at least one of --pi-auth or --ocr-config is required")
    store = secret_store_from_environment()
    settings = AppSettingsStore(args.settings)
    profiles: list[ProviderProfile] = []
    if args.pi_auth is not None:
        profiles.append(import_model_profile(
            args.pi_auth,
            store=store,
            settings=settings,
            profile_id=args.profile_id,
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
        ))
    if args.ocr_config is not None:
        profiles.append(import_ocr_profile(
            args.ocr_config,
            store=store,
            settings=settings,
            profile_id=args.ocr_profile_id,
        ))
    print(json.dumps({
        "profiles": [
            profile.model_dump(mode="json", exclude={"credential_ref"})
            for profile in profiles
        ]
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
