from __future__ import annotations

import base64
import ctypes
import json
import os
import sys
import threading
from ctypes import wintypes
from pathlib import Path
from typing import Any

_ENTROPY = b"LumenStudio::secrets::v1"


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _blob(data: bytes) -> _DataBlob:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _dpapi_available() -> bool:
    return sys.platform == "win32"


def _protect(data: bytes) -> bytes:
    if not _dpapi_available():
        return b"plain:" + base64.b64encode(data)
    input_blob = _blob(data)
    entropy_blob = _blob(_ENTROPY)
    output_blob = _DataBlob()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        "Lumen Studio secret",
        ctypes.byref(entropy_blob),
        None,
        None,
        0x1,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(output_blob),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def _unprotect(data: bytes) -> bytes:
    if data.startswith(b"plain:"):
        return base64.b64decode(data[6:])
    if not _dpapi_available():
        raise ValueError("encrypted secret is not readable on this platform")
    input_blob = _blob(data)
    entropy_blob = _blob(_ENTROPY)
    output_blob = _DataBlob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        0x1,
        ctypes.byref(output_blob),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


class SecretStore:
    """Stores provider API keys encrypted with Windows DPAPI.

    The file never contains plaintext keys on Windows. On other platforms a
    clearly marked base64 fallback is used so development still works.
    """

    def __init__(self, data_dir: Path):
        self.path = data_dir / "secrets.json"
        self._lock = threading.RLock()
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                self._data = {str(k): str(v) for k, v in parsed.items()}
        except Exception:
            self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        os.replace(temp, self.path)

    def set(self, key: str, value: str | None) -> None:
        with self._lock:
            if value:
                self._data[key] = base64.b64encode(_protect(value.encode("utf-8"))).decode("ascii")
            else:
                self._data.pop(key, None)
            self._save()

    def get(self, key: str) -> str | None:
        with self._lock:
            encoded = self._data.get(key)
            if not encoded:
                return None
            try:
                return _unprotect(base64.b64decode(encoded)).decode("utf-8")
            except Exception:
                return None

    def has(self, key: str) -> bool:
        return key in self._data and bool(self._data.get(key))

    def masked(self, key: str) -> str:
        value = self.get(key)
        if not value:
            return ""
        if len(value) <= 8:
            return "••••••••"
        return f"{value[:3]}••••{value[-4:]}"


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "••••••••"
    return f"{value[:3]}••••{value[-4:]}"
