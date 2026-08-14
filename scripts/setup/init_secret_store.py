"""Initialize the Docker secret-store master key without printing key material."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from oopsnote.ai.secrets import EncryptedFileSecretStore

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KEY_PATH = ROOT / "deploy" / "oopsnote" / "secrets" / "credential_store_key"


def initialize(path: Path) -> bool:
    """Create a durable master key once; return False when it already exists."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    try:
        os.write(descriptor, EncryptedFileSecretStore.generate_key() + b"\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    path.chmod(0o600)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=DEFAULT_KEY_PATH)
    path = parser.parse_args().path.resolve()
    created = initialize(path)
    print(f"{'created' if created else 'exists'}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
