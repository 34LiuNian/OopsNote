"""Opaque local secret storage for AI providers.

Only opaque references are persisted by OopsNote.  The Windows implementation
uses Credential Manager; callers must not log returned values.
"""

from __future__ import annotations

import ctypes
from abc import ABC, abstractmethod
from ctypes import wintypes
from uuid import uuid4
import threading


class SecretNotFoundError(KeyError):
    pass


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
        reference = reference or uuid4().hex
        with self._lock:
            self._values[reference] = secret
        return reference

    def get(self, reference: str) -> str:
        with self._lock:
            try:
                return self._values[reference]
            except KeyError as error:
                raise SecretNotFoundError(reference) from error

    def delete(self, reference: str) -> None:
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
        if not reference or "/" in reference or "\\" in reference:
            raise ValueError("credential reference must be an opaque UUID")
        return WindowsCredentialManagerSecretStore._PREFIX + reference

    def put(self, secret: str, *, reference: str | None = None) -> str:
        if not isinstance(secret, str) or not secret:
            raise ValueError("secret must be a non-empty string")
        reference = reference or uuid4().hex
        target = self._target(reference)
        encoded = secret.encode("utf-16-le")

        class CREDENTIALW(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                ("LastWritten", ctypes.c_byte * 8), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)), ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

        blob = (ctypes.c_byte * len(encoded)).from_buffer_copy(encoded)
        credential = CREDENTIALW(0, self._CRED_TYPE_GENERIC, target, None, (ctypes.c_byte * 8)(), len(encoded), blob, self._CRED_PERSIST_LOCAL_MACHINE, 0, None, None, "OopsNote")
        if not self._advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise OSError(ctypes.get_last_error(), "CredWriteW failed")
        return reference

    def get(self, reference: str) -> str:
        target = self._target(reference)
        credential_ptr = ctypes.c_void_p()
        if not self._advapi32.CredReadW(target, self._CRED_TYPE_GENERIC, 0, ctypes.byref(credential_ptr)):
            raise SecretNotFoundError(reference)
        try:
            # CredentialBlobSize is at offset determined by the platform ABI;
            # use CredRead only on Windows and decode the documented UTF-16 blob.
            class CREDENTIALW(ctypes.Structure):
                _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                    ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                    ("LastWritten", ctypes.c_byte * 8), ("CredentialBlobSize", wintypes.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_byte))]
            credential = ctypes.cast(credential_ptr, ctypes.POINTER(CREDENTIALW)).contents
            return ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize).decode("utf-16-le")
        finally:
            self._advapi32.CredFree(credential_ptr)

    def delete(self, reference: str) -> None:
        target = self._target(reference)
        if not self._advapi32.CredDeleteW(target, self._CRED_TYPE_GENERIC, 0):
            raise SecretNotFoundError(reference)


__all__ = ["MemorySecretStore", "SecretNotFoundError", "SecretStore", "WindowsCredentialManagerSecretStore"]
