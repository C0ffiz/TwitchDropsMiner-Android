"""TwitchDropsMiner Android - Main Application"""
# ── Crash-log bootstrap ─────────────────────────────────────────────────────
# Stdlib-only imports come first so the crash logger is active before any
# third-party import (e.g. kivymd) that could itself raise an ImportError.
import sys
import os
import traceback
from pathlib import Path
from datetime import datetime


def _get_log_dir() -> Path:
    """Return a user-accessible directory for logs (no extra permissions needed)."""
    if 'ANDROID_ARGUMENT' in os.environ:
        # Package name must match buildozer.spec package.domain + package.name.
        # App-specific external storage – no WRITE_EXTERNAL_STORAGE permission
        # required. Visible in Samsung My Files under:
        #   Internal storage → Android → data → org.example.twitchdropsminer → files
        pkg = 'org.example.twitchdropsminer'
        candidate = Path('/sdcard/Android/data') / pkg / 'files'
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            # Fallback: internal app storage (adb pull only)
            return Path('/data/user/0') / pkg / 'files'
    return Path.home() / '.twitch_drops_android'


LOG_DIR = _get_log_dir()
CRASH_LOG = LOG_DIR / 'crash.log'


def _write_log(text: str) -> None:
    """Append text to the crash/run log file."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CRASH_LOG, 'a', encoding='utf-8') as fh:
            fh.write(text)
    except Exception:
        pass  # nothing we can do if even the log write fails


class _TeeStream:
    """Write to both the original stream and the crash log file."""

    def __init__(self, original):
        self._orig = original

    def write(self, s: str) -> None:
        _write_log(s)
        try:
            self._orig.write(s)
        except Exception:
            pass

    def flush(self) -> None:
        try:
            self._orig.flush()
        except Exception:
            pass

    def fileno(self):
        try:
            return self._orig.fileno()
        except Exception:
            return -1


def _excepthook(exc_type, exc_value, exc_tb):
    """Global handler — writes full traceback to crash.log before exiting."""
    tb = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    _write_log(f'\n=== CRASH {datetime.now():%Y-%m-%d %H:%M:%S} ===\n{tb}\n')
    sys.__excepthook__(exc_type, exc_value, exc_tb)


# Install before any third-party import so even ImportErrors are captured.
sys.excepthook = _excepthook
sys.stderr = _TeeStream(sys.stderr)
_write_log(
    f'=== START {datetime.now():%Y-%m-%d %H:%M:%S} '
    f'log={CRASH_LOG} ===\n'
)
# ── End crash-log bootstrap ──────────────────────────────────────────────────

import asyncio
import logging
import threading
from kivymd.app import MDApp
from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager
from kivy.utils import platform
from core.settings import Settings
from core.twitch_client import TwitchClient
from ui.screens import (
    HomeScreen,
    LoginScreen,
    InventoryScreen,
    SettingsScreen,
    ChannelsScreen,
    LogsScreen
)

# Setup logging — also route all logger.* output to crash.log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
crash_log_handler = logging.FileHandler(str(CRASH_LOG), encoding='utf-8')
crash_log_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
logging.getLogger().addHandler(crash_log_handler)
logger = logging.getLogger("TwitchDrops")
logger.info(f"Crash log: {CRASH_LOG}")


class TwitchDropsMinerApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "TwitchDropsMiner"
        self.settings = Settings()
        self.twitch_client = None
        self.screen_manager = None
        self.logs = []
        # --- Asyncio setup ---
        self.loop = asyncio.new_event_loop()
        self.async_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.async_thread.start()

    def _run_event_loop(self):
        """Runs in a separate thread."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def build(self):
        self.screen_manager = ScreenManager()
        # Add screens
        self.screen_manager.add_widget(HomeScreen(name='home'))
        self.screen_manager.add_widget(LoginScreen(name='login'))
        self.screen_manager.add_widget(InventoryScreen(name='inventory'))
        self.screen_manager.add_widget(SettingsScreen(name='settings'))
        self.screen_manager.add_widget(ChannelsScreen(name='channels'))
        self.screen_manager.add_widget(LogsScreen(name='logs'))
        callbacks = {
            'on_print': self.on_print,
            'on_status': self.on_status,
            'on_progress': self.on_progress,
            'on_channel': self.on_channel,
            'on_drop': self.on_drop,
            'on_inventory': self.on_inventory,
            'on_notify': self.on_notify,
        }
        self.twitch_client = TwitchClient(self.settings, callbacks)
        if self.settings.oauth_token:
            self.screen_manager.current = 'home'
        else:
            self.screen_manager.current = 'login'
        return self.screen_manager

    # --- Safe UI calls from async thread ---
    def _update_ui(self, func, args):
        Clock.schedule_once(lambda dt: func(args))

    def on_print(self, message: str):
        logger.info(message)
        # Limit logs to last 500 lines (prevent RAM overflow)
        self.logs.append(message)
        if len(self.logs) > 500:
            self.logs.pop(0)

        def update_logs_ui(msg):
            if self.screen_manager.current == 'logs':
                self.screen_manager.get_screen('logs').add_log(msg)

        self._update_ui(update_logs_ui, message)

    def on_status(self, status: str):
        self._update_ui(self.screen_manager.get_screen('home').update_status, status)

    def on_progress(self, current: int, total: int):
        self._update_ui(
            self.screen_manager.get_screen('home').update_progress,
            (current, total)
        )

    def on_channel(self, channel_name: str):
        self._update_ui(self.screen_manager.get_screen('home').update_channel, channel_name)

    def on_drop(self, drop):
        self._update_ui(self.screen_manager.get_screen('home').update_drop, drop)

    def on_inventory(self, inventory: list):
        self._update_ui(self.screen_manager.get_screen('inventory').update_inventory, inventory)

    def on_notify(self, title: str, message: str):
        if platform == 'android':
            self._show_android_notification(title, message)
        logger.info(f"Notification: {title}: {message}")

    def _show_android_notification(self, title, message):
        """Android notification with channel support (Android 8+)."""
        try:
            from jnius import autoclass
            Context = autoclass('android.content.Context')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            NotificationManager = autoclass('android.app.NotificationManager')
            NotificationChannel = autoclass('android.app.NotificationChannel')
            NotificationCompat = autoclass('androidx.core.app.NotificationCompat')
            activity = PythonActivity.mActivity
            channel_id = "twitch_drops_miner"
            # Create notification channel (required for Android 8+)
            importance = NotificationManager.IMPORTANCE_DEFAULT
            channel = NotificationChannel(channel_id, "Twitch Miner Notifications", importance)
            notification_manager = activity.getSystemService(Context.NOTIFICATION_SERVICE)
            notification_manager.createNotificationChannel(channel)
            # Build notification
            builder = NotificationCompat.Builder(activity, channel_id)
            builder.setContentTitle(title)
            builder.setContentText(message)
            builder.setSmallIcon(activity.getApplicationInfo().icon)
            builder.setAutoCancel(True)
            notification_manager.notify(1, builder.build())
        except Exception as e:
            logger.error(f"Android Notification Error: {e}")

    # --- ACTIONS ---
    def start_mining(self):
        if self.twitch_client and not self.twitch_client._running:
            asyncio.run_coroutine_threadsafe(self.twitch_client.start(), self.loop)

    def stop_mining(self):
        if self.twitch_client and self.twitch_client._running:
            asyncio.run_coroutine_threadsafe(self.twitch_client.stop(), self.loop)

    def login(self, oauth_token: str):
        self.settings.oauth_token = oauth_token
        self.settings.save()
        asyncio.run_coroutine_threadsafe(self.twitch_client.login(), self.loop)
        self.screen_manager.current = 'home'

    def logout(self):
        self.stop_mining()
        self.settings.oauth_token = ""
        self.settings.save()
        self.screen_manager.current = 'login'

    def on_stop(self):
        # Stop the event loop when the app closes
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.settings.save(force=True)


def main():
    """Main entry point."""
    TwitchDropsMinerApp().run()


if __name__ == '__main__':
    main()
