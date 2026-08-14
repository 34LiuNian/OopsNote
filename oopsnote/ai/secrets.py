"""Opaque local secret storage for AI providers.

Only opaque references are persisted by OopsNote.  The Windows implementation
uses Credential Manager; callers must not log returned values.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import sys
import tempfile
import threading
from abc import ABC, abstractmethod
from ctypes import wintypes
from pathlib import Path
from uuid import uuid4


class SecretNotFoundError(KeyError):
    pass


class SecretStoreCorruptionError(RuntimeError):
    pass


_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _validated_reference(reference: str) -> str:
    if not isinstance(reference, str) or not _REFERENCE_PATTERN.fullmatch(reference):
        raise ValueError("credential reference must be an opaque identifier")
    return reference


class SecretStore(ABC):
    @abstractmethod
    def put(self, secret: str, *, reference: str | None = None) -> str: ...

    @abstractmethod
    def get(self, reference: str) -> str: ...

    @abstractmethod
    def delete(self, reference: str) -> None: ...

    def has(self, reference: str | None) -> bool:
        if not reference:
            return False
        try:
            self.get(reference)
        except SecretNotFoundError:
            return False
        return True


class MemorySecretStore(SecretStore):
    """Process-local test/development store; never used as production default."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._lock = threading.RLock()

    def put(self, secret: str, *, reference: str | None = None) -> str:
        if not isinstance(secret, str) or not secret:
            raise ValueError("secret must be a non-empty string")
        reference = _validated_reference(reference or uuid4().hex)
        with self._lock:
            self._values[reference] = secret
        return reference

    def get(self, reference: str) -> str:
        reference = _validated_reference(reference)
        with self._lock:
            try:
                return self._values[reference]
            except KeyError as error:
                raise SecretNotFoundError(reference) from error

    def delete(self, reference: str) -> None:
        reference = _validated_reference(reference)
        with self._lock:
            if reference not in self._values:
                raise SecretNotFoundError(reference)
            del self._values[reference]


class WindowsCredentialManagerSecretStore(SecretStore):
    """Windows Credential Manager generic credentials, scoped to OopsNote."""

    _PREFIX = "OopsNote/ai/"
    _CRED_TYPE_GENERIC = 1
    _CRED_PERSIST_LOCAL_MACHINE = 2

    def __init__(self) -> None:
        if not hasattr(ctypes, "windll"):
            raise RuntimeError("Windows Credential Manager is only available on Windows")
        self._advapi32 = ctypes.windll.advapi32

    @staticmethod
    def _target(reference: str) -> str:
        return WindowsCredentialManagerSecretStore._PREFIX + _validated_reference(reference)

    def put(self, secret: str, *, reference: str | None = None) -> str:
        if not isinstance(secret, str) or not secret:
            raise ValueError("secret must be a non-empty string")
        reference = reference or uuid4().hex
        target = self._target(reference)
        encoded = secret.encode("utf-16-le")

        class CREDENTIALW(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", ctypes.c_byte * 8),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        blob = (ctypes.c_byte * len(encoded)).from_buffer_copy(encoded)
        credential = CREDENTIALW(
            0,
            self._CRED_TYPE_GENERIC,
            target,
            None,
            (ctypes.c_byte * 8)(),
            len(encoded),
            blob,
            self._CRED_PERSIST_LOCAL_MACHINE,
            0,
            None,
            None,
            "OopsNote",
        )
        if not self._advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise OSError(ctypes.get_last_error(), "CredWriteW failed")
        return reference

    def get(self, reference: str) -> str:
        target = self._target(reference)
        credential_ptr = ctypes.c_void_p()
        if not self._advapi32.CredReadW(
            target, self._CRED_TYPE_GENERIC, 0, ctypes.byref(credential_ptr)
        ):
            raise SecretNotFoundError(reference)
        try:
            # CredentialBlobSize is at offset determined by the platform ABI;
            # use CredRead only on Windows and decode the documented UTF-16 blob.
            class CREDENTIALW(ctypes.Structure):
                _fields_ = [
                    ("Flags", wintypes.DWORD),
                    ("Type", wintypes.DWORD),
                    ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR),
                    ("LastWritten", ctypes.c_byte * 8),
                    ("CredentialBlobSize", wintypes.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
                ]

            credential = ctypes.cast(credential_ptr, ctypes.POINTER(CREDENTIALW)).contents
            return ctypes.string_at(
                credential.CredentialBlob, credential.CredentialBlobSize
            ).decode("utf-16-le")
        finally:
            self._advapi32.CredFree(credential_ptr)

    def delete(self, reference: str) -> None:
        target = self._target(reference)
        if not self._advapi32.CredDeleteW(target, self._CRED_TYPE_GENERIC, 0):
            raise SecretNotFoundError(reference)


class EncryptedFileSecretStore(SecretStore):
    """Encrypted Linux/container vault protected by a file-mounted master key."""

    _FORMAT_VERSION = 1

    def __init__(self, path: Path, key_file: Path) -> None:
        self.path = path
        self.key_file = key_file
        self._lock = threading.RLock()
        try:
            key = key_file.read_bytes().strip()
        except OSError as error:
            raise RuntimeError(f"secret-store master key is unavailable: {key_file}") from error
        try:
            from cryptography.fernet import Fernet

            self._fernet = Fernet(key)
        except (ImportError, ValueError) as error:
            raise RuntimeError("secret-store master key is invalid") from error

    @staticmethod
    def generate_key() -> bytes:
        from cryptography.fernet import Fernet

        return Fernet.generate_key()

    def _read(self) -> dict[str, str]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as error:
            raise SecretStoreCorruptionError(
                f"encrypted secret store is unreadable: {self.path}"
            ) from error
        if not isinstance(payload, dict) or payload.get("version") != self._FORMAT_VERSION:
            raise SecretStoreCorruptionError("encrypted secret store has an unsupported format")
        credentials = payload.get("credentials")
        if not isinstance(credentials, dict) or any(
            not isinstance(reference, str) or not isinstance(token, str)
            for reference, token in credentials.items()
        ):
            raise SecretStoreCorruptionError("encrypted secret store credentials are invalid")
        return credentials

    def _write(self, credentials: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = (
            json.dumps(
                {"version": self._FORMAT_VERSION, "credentials": credentials},
                ensure_ascii=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        descriptor, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        temp = Path(temp_name)
        descriptor_open = True
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, 0o600)
            else:
                os.chmod(temp, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor_open = False
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            temp.replace(self.path)
            self.path.chmod(0o600)
        finally:
            if descriptor_open:
                os.close(descriptor)
            if temp.exists():
                temp.unlink()

    def put(self, secret: str, *, reference: str | None = None) -> str:
        if not isinstance(secret, str) or not secret:
            raise ValueError("secret must be a non-empty string")
        reference = _validated_reference(reference or uuid4().hex)
        token = self._fernet.encrypt(secret.encode("utf-8")).decode("ascii")
        with self._lock:
            credentials = self._read()
            credentials[reference] = token
            self._write(credentials)
        return reference

    def get(self, reference: str) -> str:
        reference = _validated_reference(reference)
        with self._lock:
            try:
                token = self._read()[reference]
            except KeyError as error:
                raise SecretNotFoundError(reference) from error
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except Exception as error:
            raise SecretStoreCorruptionError(
                f"credential cannot be decrypted: {reference}"
            ) from error

    def delete(self, reference: str) -> None:
        reference = _validated_reference(reference)
        with self._lock:
            credentials = self._read()
            if reference not in credentials:
                raise SecretNotFoundError(reference)
            del credentials[reference]
            self._write(credentials)


def secret_store_from_environment() -> SecretStore:
    """Create the platform store without accepting secret material from env."""
    if sys.platform == "win32":
        return WindowsCredentialManagerSecretStore()
    path = Path(os.getenv("OOPSNOTE_SECRET_STORE_PATH", "/vault/credentials.json"))
    key_file = Path(
        os.getenv("OOPSNOTE_SECRET_STORE_KEY_FILE", "/run/secrets/oopsnote_secret_store_key")
    )
    return EncryptedFileSecretStore(path, key_file)


__all__ = [
    "EncryptedFileSecretStore",
    "MemorySecretStore",
    "SecretNotFoundError",
    "SecretStore",
    "SecretStoreCorruptionError",
    "WindowsCredentialManagerSecretStore",
    "secret_store_from_environment",
]
