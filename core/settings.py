"""Settings management"""
import json
import os
from pathlib import Path
from core.constants import PriorityMode

# Android storage path: use app-internal storage (no permissions required)
try:
    from android.storage import app_storage_path
    APP_DIR = Path(app_storage_path()) / "TwitchDropsMiner"
except ImportError:
    APP_DIR = Path.home() / ".twitch_drops_android"

APP_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_PATH = APP_DIR / "settings.json"
COOKIES_PATH = APP_DIR / "cookies.jar"
LOG_PATH = APP_DIR / "log.txt"


class Settings:
    """Application settings."""

    def __init__(self):
        self.oauth_token = ""
        self.user_id = None
        self.username = ""
        self.priority = []
        self.exclude = set()
        self.language = "English"
        self.priority_mode = PriorityMode.PRIORITY_ONLY
        self.proxy = ""
        self.auto_claim = True
        self.notifications_enabled = True
        self._altered = False

        self.load()

    def load(self):
        """Load settings from file."""
        if SETTINGS_PATH.exists():
            try:
                with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.oauth_token = data.get('oauth_token', '')
                    self.user_id = data.get('user_id')
                    self.username = data.get('username', '')
                    self.priority = data.get('priority', [])
                    self.exclude = set(data.get('exclude', []))
                    self.language = data.get('language', 'English')
                    self.priority_mode = PriorityMode(data.get('priority_mode', 'priority_only'))
                    self.proxy = data.get('proxy', '')
                    self.auto_claim = data.get('auto_claim', True)
                    self.notifications_enabled = data.get('notifications_enabled', True)
            except Exception as e:
                print(f"Error loading settings: {e}")

    def save(self, force=False):
        """Save settings to file."""
        if self._altered or force:
            try:
                data = {
                    'oauth_token': self.oauth_token,
                    'user_id': self.user_id,
                    'username': self.username,
                    'priority': self.priority,
                    'exclude': list(self.exclude),
                    'language': self.language,
                    'priority_mode': self.priority_mode.value,
                    'proxy': self.proxy,
                    'auto_claim': self.auto_claim,
                    'notifications_enabled': self.notifications_enabled,
                }
                with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                self._altered = False
            except Exception as e:
                print(f"Error saving settings: {e}")

    def alter(self):
        """Mark settings as altered."""
        self._altered = True
