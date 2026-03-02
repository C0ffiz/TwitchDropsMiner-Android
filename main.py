"""TwitchDropsMiner Android - Main Application"""
import asyncio
import logging
import threading
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager
from kivymd.app import MDApp
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText  # Android-specific: KivyMD 2.x API
from core.settings import Settings
from core.twitch_client import TwitchClient
from ui.screens import LoginScreen, AppScreen, ChannelsScreen, LogsScreen

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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

    def _run_event_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def build(self):
        self.settings = Settings()  # Android-specific: deferred — App must be running for get_app_paths()
        self.screen_manager = ScreenManager()
        # Phase 1 navigation architecture: LoginScreen + AppScreen (bottom nav shell) + secondary screens
        self.screen_manager.add_widget(LoginScreen(name='login'))
        self.screen_manager.add_widget(AppScreen(name='app'))
        self.screen_manager.add_widget(ChannelsScreen(name='channels'))
        self.screen_manager.add_widget(LogsScreen(name='logs'))
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
        if self.settings.oauth_token:
            # Saved token found — show app shell immediately, validate in background
            self.screen_manager.current = 'app'
            self._start_login_validation()
        else:
            self.screen_manager.current = 'login'
            self._start_device_login()
        Window.bind(on_keyboard=self.on_key_back)
        return self.screen_manager

    def _start_device_login(self):
        """Kick off the async device code OAuth flow in the background event loop."""
        asyncio.run_coroutine_threadsafe(
            self.twitch_client.start_device_login(), self.loop
        )

    def _start_login_validation(self):
        """Validate the saved token in background; fall back to device login if invalid."""
        async def _validate():
            try:
                await self.twitch_client.login()
            except Exception:
                # Token invalid or expired — switch to login screen and start fresh
                Clock.schedule_once(lambda dt: self._switch_to_login())

        asyncio.run_coroutine_threadsafe(_validate(), self.loop)

    def _switch_to_login(self):
        self.screen_manager.current = 'login'
        self._start_device_login()

    def on_key_back(self, window, key, *args):
        if key == 27:  # Android back button / Escape
            current = self.screen_manager.current
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
        self._update_ui(
            self.screen_manager.get_screen('login').show_login_code,
            user_code, verification_uri
        )

    def on_login_success(self):
        """Called by TwitchClient when the device code polling succeeds; navigate to AppScreen."""
        Clock.schedule_once(lambda dt: setattr(self.screen_manager, 'current', 'app'))

    # --- Mining state callbacks ---

    def on_print(self, message):
        logger.info(message)
        self.logs.append(message)
        if len(self.logs) > 500:
            self.logs.pop(0)
        # Android-specific: always buffer — LogsScreen shows all messages whenever entered
        self._update_ui(self.screen_manager.get_screen('logs').add_log, message)

    def on_status(self, status):
        self._update_ui(self.screen_manager.get_screen('app').update_status, status)

    def on_progress(self, current, total):
        self._update_ui(self.screen_manager.get_screen('app').update_progress, current, total)

    def on_channel(self, channel_name):
        self._update_ui(self.screen_manager.get_screen('app').update_channel, channel_name)

    def on_drop(self, drop):
        self._update_ui(self.screen_manager.get_screen('app').update_drop, drop)

    def on_inventory(self, inventory):
        self._update_ui(self.screen_manager.get_screen('app').update_inventory, inventory)

    def on_channels(self, channels):
        # Android-specific: push channel list to ChannelsScreen on main thread when fetch completes
        self._update_ui(self.screen_manager.get_screen('channels').update_channels, channels)

    def on_notify(self, title, message):
        # Android-specific: KivyMD 2.x — MDSnackbarText must be passed as child widget
        t = f"{title}: {message}"
        Clock.schedule_once(lambda dt: MDSnackbar(MDSnackbarText(text=t)).open())

    def start_mining(self):
        if self.twitch_client and not self.twitch_client._running:
            asyncio.run_coroutine_threadsafe(self.twitch_client.start(), self.loop)

    def stop_mining(self):
        if self.twitch_client and self.twitch_client._running:
            asyncio.run_coroutine_threadsafe(self.twitch_client.stop(), self.loop)

    def logout(self):
        self.stop_mining()
        self.settings.oauth_token = ""
        self.settings.save()
        self.screen_manager.current = 'login'
        self._start_device_login()

    def on_stop(self):
        # Android-specific: schedule a clean shutdown coroutine on the event loop.
        # stop() cancels tasks and closes the session before we halt the loop.
        # settings.save() is called only after stop() completes, not before.
        async def _stop_then_halt():
            if self.twitch_client:
                await self.twitch_client.stop()
            self.settings.save()
            self.loop.stop()

        asyncio.run_coroutine_threadsafe(_stop_then_halt(), self.loop)
        self.async_thread.join(timeout=5)  # Android-specific: wait for clean shutdown


def main():
    TwitchDropsMinerApp().run()


if __name__ == '__main__':
    main()
