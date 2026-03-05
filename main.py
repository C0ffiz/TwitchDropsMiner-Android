"""TwitchDropsMiner Android - Main Application"""
import asyncio
import logging
import sys
import traceback
import threading
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager
from kivymd.app import MDApp
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText  # Android-specific: KivyMD 2.x API
from core.settings import Settings
from core.twitch_client import TwitchClient
from ui.screens import LoginScreen, AppScreen, ChannelsScreen, LogsScreen

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(name)s] %(levelname)s - %(message)s')
logger = logging.getLogger("TwitchDrops")


class TwitchDropsMinerApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = "TwitchDropsMiner"
        self.theme_cls.primary_palette = "Purple"
        self.theme_cls.theme_style = "Dark"
        self.settings = None  # Android-specific: deferred — Settings() needs App running for get_app_paths()
        self.twitch_client = None
        self.screen_manager = None
        self.logs = []
        self.loop = asyncio.new_event_loop()
        self.async_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.async_thread.start()
        self._setup_exception_handlers()
        logger.debug("TwitchDropsMinerApp initialized")

    def _run_event_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _setup_exception_handlers(self):
        """Install global exception hooks so crashes reach adb logcat verbatim."""
        def _excepthook(exc_type, exc_value, exc_tb):
            logger.critical(
                "Uncaught exception:\n%s",
                "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            )
            sys.__excepthook__(exc_type, exc_value, exc_tb)

        sys.excepthook = _excepthook

        def _asyncio_excepthook(loop, context):
            exc = context.get("exception")
            if exc:
                logger.critical(
                    "Unhandled asyncio exception: %s\n%s",
                    context.get("message", ""),
                    "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                )
            else:
                logger.error("asyncio error: %s", context.get("message", "Unknown"))

        self.loop.set_exception_handler(_asyncio_excepthook)

    def build(self):
        logger.debug("build() start")
        self.settings = Settings()  # Android-specific: deferred — App must be running for get_app_paths()
        logger.debug("Settings loaded: user_data_dir=%s", getattr(self, 'user_data_dir', 'N/A'))
        self.screen_manager = ScreenManager()
        # Phase 1 navigation architecture: LoginScreen + AppScreen (bottom nav shell) + secondary screens
        self.screen_manager.add_widget(LoginScreen(name='login'))
        self.screen_manager.add_widget(AppScreen(name='app'))
        self.screen_manager.add_widget(ChannelsScreen(name='channels'))
        self.screen_manager.add_widget(LogsScreen(name='logs'))
        logger.debug("Screens added to ScreenManager")
        callbacks = {
            'on_login_code': self.on_login_code,    # device code flow: show code on LoginScreen
            'on_login_success': self.on_login_success,  # device code flow: navigate to AppScreen
            'on_print': self.on_print,
            'on_status': self.on_status,
            'on_progress': self.on_progress,
            'on_channel': self.on_channel,
            'on_drop': self.on_drop,
            'on_inventory': self.on_inventory,
            'on_channels': self.on_channels,
            'on_notify': self.on_notify,
        }
        self.twitch_client = TwitchClient(self.settings, callbacks)
        logger.debug("TwitchClient created")
        if self.settings.oauth_token:
            # Saved token found — show app shell immediately, validate in background
            logger.debug("build(): saved token found → AppScreen + background validation")
            self.screen_manager.current = 'app'
            self._start_login_validation()
        else:
            logger.debug("build(): no saved token → LoginScreen + device login")
            self.screen_manager.current = 'login'
            self._start_device_login()
        Window.bind(on_keyboard=self.on_key_back)
        logger.debug("build() complete")
        return self.screen_manager

    def _start_device_login(self):
        """Kick off the async device code OAuth flow in the background event loop."""
        logger.debug("_start_device_login() — scheduling coroutine")
        asyncio.run_coroutine_threadsafe(
            self.twitch_client.start_device_login(), self.loop
        )

    def _start_login_validation(self):
        """Validate the saved token in background; fall back to device login if invalid."""
        logger.debug("_start_login_validation() — validating saved token")
        async def _validate():
            try:
                await self.twitch_client.login()
                logger.debug("_validate(): token OK — scheduling start_mining()")
                # Token valid — auto-start mining so inventory is fetched immediately
                Clock.schedule_once(lambda dt: self.start_mining())
            except Exception as e:
                logger.warning("_validate(): token invalid (%s) — fallback to device login", e)
                # Token invalid or expired — switch to login screen and start fresh
                Clock.schedule_once(lambda dt: self._switch_to_login())

        asyncio.run_coroutine_threadsafe(_validate(), self.loop)

    def _switch_to_login(self):
        logger.debug("_switch_to_login() called")
        self.screen_manager.current = 'login'
        self._start_device_login()

    def on_key_back(self, window, key, *args):
        if key == 27:  # Android back button / Escape
            current = self.screen_manager.current
            logger.debug("on_key_back: back pressed on screen=%r", current)
            if current in ('channels', 'logs'):
                self.screen_manager.current = 'app'
                return True  # Consumed — don't exit
            # On 'app' or 'login', allow default (exit) behaviour
        return False

    def _update_ui(self, func, *args):
        Clock.schedule_once(lambda dt: func(*args))

    # --- Login callbacks (device code flow) ---

    def on_login_code(self, user_code, verification_uri):
        """Called by TwitchClient when a new device code is ready; routes to LoginScreen."""
        logger.debug("on_login_code: code=%r uri=%r", user_code, verification_uri)
        self._update_ui(
            self.screen_manager.get_screen('login').show_login_code,
            user_code, verification_uri
        )

    def on_login_success(self):
        """Called by TwitchClient when the device code polling succeeds; navigate to AppScreen."""
        logger.info("on_login_success: navigating to AppScreen and starting mining")
        def _navigate_and_start(dt):
            self.screen_manager.current = 'app'
            self.start_mining()
        Clock.schedule_once(_navigate_and_start)

    # --- Mining state callbacks ---

    def on_print(self, message):
        logger.info(message)
        self.logs.append(message)
        if len(self.logs) > 500:
            self.logs.pop(0)
        # Android-specific: always buffer — LogsScreen shows all messages whenever entered
        self._update_ui(self.screen_manager.get_screen('logs').add_log, message)
        # Surface device-login connection errors on the LoginScreen so the user
        # can see why the activation code hasn't appeared yet.
        if 'Device login error' in message:
            short = message[:100] + '\u2026' if len(message) > 100 else message
            self._update_ui(
                self.screen_manager.get_screen('login').set_login_status, short
            )

    def on_status(self, status):
        logger.debug("on_status: %r", status)
        self._update_ui(self.screen_manager.get_screen('app').update_status, status)

    def on_progress(self, current, total):
        self._update_ui(self.screen_manager.get_screen('app').update_progress, current, total)

    def on_channel(self, channel_name):
        self._update_ui(self.screen_manager.get_screen('app').update_channel, channel_name)

    def on_drop(self, drop):
        self._update_ui(self.screen_manager.get_screen('app').update_drop, drop)

    def on_inventory(self, inventory):
        logger.debug("on_inventory: %d campaigns", len(inventory) if inventory else 0)
        self._update_ui(self.screen_manager.get_screen('app').update_inventory, inventory)

    def on_channels(self, channels):
        logger.debug("on_channels: %d channels", len(channels) if channels else 0)
        # Android-specific: push channel list to ChannelsScreen on main thread when fetch completes
        self._update_ui(self.screen_manager.get_screen('channels').update_channels, channels)

    def on_notify(self, title, message):
        logger.debug("on_notify: title=%r msg=%r", title, message)
        # Android-specific: KivyMD 2.x — MDSnackbarText must be passed as child widget
        t = f"{title}: {message}"
        Clock.schedule_once(lambda dt: MDSnackbar(MDSnackbarText(text=t)).open())

    def start_mining(self):
        logger.info("start_mining() called (running=%s)", self.twitch_client._running if self.twitch_client else 'N/A')
        if self.twitch_client and not self.twitch_client._running:
            asyncio.run_coroutine_threadsafe(self.twitch_client.start(), self.loop)

    def stop_mining(self):
        logger.info("stop_mining() called (running=%s)", self.twitch_client._running if self.twitch_client else 'N/A')
        if self.twitch_client and self.twitch_client._running:
            asyncio.run_coroutine_threadsafe(self.twitch_client.stop(), self.loop)

    def logout(self):
        logger.info("logout() called")
        self.stop_mining()
        self.settings.oauth_token = ""
        self.settings.save()
        self.screen_manager.current = 'login'
        self._start_device_login()

    def on_start(self):
        """Request POST_NOTIFICATIONS runtime permission on Android 13+ (API 33+)."""
        logger.info("on_start() — app is running")
        try:
            from android.permissions import request_permissions, Permission  # type: ignore[import]
            perms = []
            if hasattr(Permission, 'POST_NOTIFICATIONS'):
                perms.append(Permission.POST_NOTIFICATIONS)
            if perms:
                request_permissions(perms)
        except ImportError:
            pass  # Not running on Android
        # Lock screen to portrait orientation so the app looks correct on all devices.
        # This complements android.orientation = portrait in buildozer.spec.
        try:
            from jnius import autoclass  # type: ignore[import]
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            ActivityInfo = autoclass('android.content.pm.ActivityInfo')
            PythonActivity.mActivity.setRequestedOrientation(
                ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
            )
            logger.debug("on_start: portrait orientation locked via pyjnius")
        except Exception as e:
            logger.warning("on_start: could not lock portrait orientation: %s", e)

    def on_stop(self):
        logger.info("on_stop() — shutting down")
        # Android-specific: schedule a clean shutdown coroutine on the event loop.
        # stop() cancels tasks and closes the session before we halt the loop.
        # settings.save() is called only after stop() completes, not before.
        async def _stop_then_halt():
            if self.twitch_client:
                await self.twitch_client.stop()
            self.settings.save()
            self.loop.stop()

        asyncio.run_coroutine_threadsafe(_stop_then_halt(), self.loop)
        self.async_thread.join(timeout=3)  # Keep under Android ANR watchdog threshold
        if self.async_thread.is_alive():
            logger.warning("on_stop: async thread did not exit cleanly within timeout")


def main():
    TwitchDropsMinerApp().run()


if __name__ == '__main__':
    main()
