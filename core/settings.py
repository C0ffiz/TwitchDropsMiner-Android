"""Settings management"""
from __future__ import annotations

import os
from typing import Any, TypedDict

from core.constants import PriorityMode, DEFAULT_LANG, get_app_paths
from core.utils import json_load, json_save, notification_urls

# ---------------------------------------------------------------------------
# TypedDict — describes the set of keys persisted to disk
# ---------------------------------------------------------------------------

class SettingsFile(TypedDict):
    # --- upstream fields ---
    proxy: str                    # stored as plain str; yarl.URL not required on Android
    language: str
    dark_mode: bool
    exclude: set[str]
    priority: list[str]
    connection_quality: int
    autostart_tray: bool          # Android-specific: not applicable (desktop tray); kept for upstream sync
    tray_notifications: bool      # Android-specific: not applicable (desktop tray); kept for upstream sync
    notification_url: set[str]
    unlinked_campaigns: bool
    enable_badges_emotes: bool
    available_drops_check: bool
    priority_mode: PriorityMode
    # --- Android-specific fields ---
    oauth_token: str              # Android-specific: stored in settings (no system keychain)
    user_id: int | None           # Android-specific
    username: str                 # Android-specific
    auto_claim: bool              # Android-specific
    notifications_enabled: bool   # Android-specific: mobile notification toggle
    background_mining: bool       # Android-specific: keep miner alive as a foreground service
    keep_screen_on: bool          # Android-specific: acquire wake-lock while actively watching
    mobile_data_allowed: bool     # Android-specific: allow mining over cellular data


_default_settings: SettingsFile = {
    # upstream
    "proxy": "",
    "priority": [],
    "exclude": set(),
    "dark_mode": False,
    "autostart_tray": False,      # Android-specific: not applicable; kept for upstream sync
    "tray_notifications": True,   # Android-specific: not applicable; kept for upstream sync
    "connection_quality": 1,
    "language": DEFAULT_LANG,
    "notification_url": set(),
    "unlinked_campaigns": False,
    "enable_badges_emotes": False,
    "available_drops_check": False,
    "priority_mode": PriorityMode.PRIORITY_ONLY,
    # Android-specific
    "oauth_token": "",
    "user_id": None,
    "username": "",
    "auto_claim": True,
    "notifications_enabled": True,
    "background_mining": True,    # Android-specific
    "keep_screen_on": False,      # Android-specific
    "mobile_data_allowed": True,  # Android-specific
}


class Settings:
    """Application settings."""

    PASSTHROUGH = ("_settings", "_altered")

    def __init__(self):
        self._settings: SettingsFile = dict(_default_settings)  # type: ignore[assignment]
        self._altered: bool = False
        self.load()
        self.__get_settings_from_env__()  # env vars override file (mirrors upstream)

    def __get_settings_from_env__(self) -> None:
        """Apply ENV-var overrides (mirrors upstream behaviour; useful for Docker/CI)."""
        if os.environ.get('PRIORITY_MODE') in ('0', '1', '2'):
            self._settings["priority_mode"] = PriorityMode(int(os.environ['PRIORITY_MODE']))
        if 'UNLINKED_CAMPAIGNS' in os.environ:
            self._settings["unlinked_campaigns"] = os.environ['UNLINKED_CAMPAIGNS'] == '1'
        if 'APPRISE_URL' in os.environ:
            self._settings["notification_url"] = notification_urls(  # type: ignore[assignment]
                os.environ.get('APPRISE_URL') or '', mode="set"
            )

    def __getattr__(self, name: str, /) -> Any:
        if name in self.__dict__.get('_settings', {}):
            return self._settings[name]  # type: ignore[literal-required]
        raise AttributeError(f"Settings has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any, /) -> None:
        if name in self.PASSTHROUGH:
            super().__setattr__(name, value)
            return
        if name in self._settings:
            self._settings[name] = value  # type: ignore[literal-required]
            self._altered = True
            return
        raise TypeError(f"{name} is missing a custom setter")

    def __delattr__(self, name: str, /) -> None:
        raise RuntimeError("settings can't be deleted")

    def alter(self) -> None:
        """Mark settings as altered so the next save() will write to disk."""
        self._altered = True

    def load(self) -> None:
        """Load settings from file, merging with defaults for any missing keys."""
        settings_path = get_app_paths()["settings"]
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        loaded = json_load(settings_path, _default_settings)
        self._settings.update(loaded)
        self.migrate()

    def save(self, *, force: bool = False) -> None:
        """Save settings to file if altered or force=True."""
        if self._altered or force:
            settings_path = get_app_paths()["settings"]
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            json_save(settings_path, self._settings, sort=True)
            self._altered = False

    def migrate(self) -> None:  # Android-specific
        """
        Apply forward-compatible migrations for renamed or type-changed fields.

        json_load/merge_json already drop unknown keys and fill missing ones from
        defaults, so this method only needs to handle *renamed* or *transformed*
        fields across app versions.  Add steps here as the app evolves; never
        remove old ones.
        """
        pass
