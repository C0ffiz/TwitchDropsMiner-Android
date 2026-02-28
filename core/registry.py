from __future__ import annotations

# Android-specific: the upstream registry.py wraps the Windows `winreg` module
# to read/write OS registry keys.  Android has no such registry, so this module
# provides an identical public API backed by a per-namespace JSON file stored in
#   <App.user_data_dir>/registry_<MAIN_KEY>.json
#
# Storage layout:
#   {
#     "Software\\Twitch\\SomeKey": {
#       "valueName": [<ValueType.value: int>, <data>],
#       ...
#     },
#     ...
#   }
#
# No file I/O is performed at module import time.

import json
import os
from typing import Any
from enum import Enum, Flag
from collections.abc import Generator


class RegistryError(Exception):
    pass


class ValueNotFound(RegistryError):
    pass


# Android-specific: individual access-flag bits are kept as powers of 2 so
# that Flag composition (KEY_READ | KEY_WRITE, etc.) works on all Python
# versions.  The numeric values intentionally differ from the winreg constants
# because they are never passed to any OS call on Android.
class Access(Flag):
    KEY_QUERY_VALUE        = 0x0001
    KEY_SET_VALUE          = 0x0002
    KEY_CREATE_SUB_KEY     = 0x0004
    KEY_ENUMERATE_SUB_KEYS = 0x0008
    KEY_NOTIFY             = 0x0010
    KEY_CREATE_LINK        = 0x0020
    KEY_READ               = KEY_QUERY_VALUE | KEY_ENUMERATE_SUB_KEYS | KEY_NOTIFY
    KEY_WRITE              = KEY_SET_VALUE | KEY_CREATE_SUB_KEY
    KEY_EXECUTE            = KEY_READ   # alias — same semantics as original winreg
    KEY_ALL_ACCESS         = KEY_READ | KEY_WRITE | KEY_CREATE_LINK


# Android-specific: MainKey members carry string values instead of winreg
# integer handles.  The names (HKCU, HKLM, …) are preserved so that path
# strings like "HKCU/Software/..." parse correctly via MainKey[name].
class MainKey(Enum):
    HKU                   = "HKU"
    HKCR                  = "HKCR"
    HKCU                  = "HKCU"
    HKLM                  = "HKLM"
    HKEY_USERS            = "HKU"               # alias for HKU
    HKEY_CLASSES_ROOT     = "HKCR"              # alias for HKCR
    HKEY_CURRENT_USER     = "HKCU"              # alias for HKCU
    HKEY_LOCAL_MACHINE    = "HKLM"              # alias for HKLM
    HKEY_CURRENT_CONFIG   = "HKEY_CURRENT_CONFIG"
    HKEY_PERFORMANCE_DATA = "HKEY_PERFORMANCE_DATA"


# ValueType integer values are kept identical to the Windows REG_* constants
# so that data serialised on desktop can be deserialised on Android and vice
# versa.  Aliases (REG_DWORD_LITTLE_ENDIAN == REG_DWORD, etc.) match the
# original winreg behaviour.
class ValueType(Enum):
    REG_NONE                       = 0
    REG_SZ                         = 1
    REG_EXPAND_SZ                  = 2
    REG_BINARY                     = 3
    REG_DWORD                      = 4
    REG_DWORD_LITTLE_ENDIAN        = 4   # alias for REG_DWORD
    REG_DWORD_BIG_ENDIAN           = 5
    REG_LINK                       = 6
    REG_MULTI_SZ                   = 7
    REG_RESOURCE_LIST              = 8
    REG_FULL_RESOURCE_DESCRIPTOR   = 9
    REG_RESOURCE_REQUIREMENTS_LIST = 10
    REG_QWORD                      = 11
    REG_QWORD_LITTLE_ENDIAN        = 11  # alias for REG_QWORD


class RegistryKey:
    """Context-manager wrapper around a single registry key (path).

    On Android the backing store is a JSON file; the key opens and closes
    without holding any OS resource.  Usage is intentionally identical to the
    desktop version::

        with RegistryKey("HKCU/Software/Twitch/Drops") as key:
            vtype, data = key.get("LastRun")
    """

    # Android-specific: lazily resolved once per process; may be overridden by
    # tests via RegistryKey.set_storage_root("/some/writable/dir").
    _storage_root: str | None = None

    @classmethod
    def _get_storage_root(cls) -> str:
        """Return the directory used for JSON storage, resolving it if needed."""
        if cls._storage_root is None:
            try:
                from kivy.app import App  # Android-specific
                app = App.get_running_app()
                if app is not None:
                    cls._storage_root = app.user_data_dir
                    return cls._storage_root
            except Exception:
                pass
            # Android-specific: fallback for unit tests / non-Kivy environments
            cls._storage_root = os.path.join(
                os.path.expanduser("~"), ".twitchdrops_registry"
            )
        return cls._storage_root

    # Android-specific: allow the storage root to be pinned from outside
    # (e.g. in tests or when the Kivy app bootstraps early).
    @classmethod
    def set_storage_root(cls, path: str) -> None:
        cls._storage_root = path

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, path: str, *, read_only: bool = False):
        main_key_name, _, key_path = path.replace("/", "\\").partition("\\")
        self.main_key = MainKey[main_key_name]
        self.path = key_path
        self._read_only = read_only
        self._file_data: dict[str, dict[str, list]] = {}
        self._load()

    def __enter__(self) -> RegistryKey:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Android-specific: no OS handle to release; kept as a no-op so that
        # callers using `with RegistryKey(...) as key:` remain portable.
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _storage_file(self) -> str:
        """Absolute path to the JSON file backing this MainKey namespace."""
        root = self._get_storage_root()
        os.makedirs(root, exist_ok=True)
        return os.path.join(root, f"registry_{self.main_key.value}.json")

    def _load(self) -> None:
        filepath = self._storage_file()
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as fh:
                    self._file_data = json.load(fh)
            except (json.JSONDecodeError, OSError):
                self._file_data = {}
        # Ensure the path section exists and keep a direct reference so that
        # mutations to self._data are visible through self._file_data on save.
        if self.path not in self._file_data:
            self._file_data[self.path] = {}
        self._data: dict[str, list] = self._file_data[self.path]

    def _save(self) -> None:
        if self._read_only:
            return
        filepath = self._storage_file()
        try:
            with open(filepath, "w", encoding="utf-8") as fh:
                json.dump(self._file_data, fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            raise RegistryError(f"Failed to persist registry data: {exc}") from exc

    # ------------------------------------------------------------------
    # Core operations — same signatures as the desktop registry.py
    # ------------------------------------------------------------------

    def get(self, name: str) -> tuple[ValueType, Any]:
        if name not in self._data:
            # TODO: consider returning None for missing values
            raise ValueNotFound(name)
        entry = self._data[name]
        return (ValueType(entry[0]), entry[1])

    def set(self, name: str, value_type: ValueType, value: Any) -> bool:
        self._data[name] = [value_type.value, value]
        self._save()
        return True  # TODO: return False if the set operation fails

    def delete(self, name: str, *, silent: bool = False) -> bool:
        if name not in self._data:
            if not silent:
                raise ValueNotFound(name)
            return False
        del self._data[name]
        self._save()
        return True

    def values(self) -> Generator[tuple[str, ValueType, Any], None, None]:
        for name, entry in list(self._data.items()):
            try:
                yield name, ValueType(entry[0]), entry[1]
            except (ValueError, TypeError, IndexError):
                return

    # ------------------------------------------------------------------
    # Android-specific: extra dunder helpers absent from the desktop version
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        """Number of values stored under this key."""
        return len(self._data)

    def __contains__(self, name: object) -> bool:
        """Support ``'ValueName' in key`` membership testing."""
        return name in self._data

    def __iter__(self) -> Generator[str, None, None]:
        """Iterate over value names stored under this key."""
        yield from self._data
