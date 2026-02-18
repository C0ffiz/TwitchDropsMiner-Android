"""TwitchDropsMiner Android - Main Application (Fixed)"""
import asyncio
import logging
import threading
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.uix.snackbar import Snackbar
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
Setup logging
logging.basicConfig(
level=logging.INFO,
format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TwitchDrops")
class TwitchDropsMinerApp(MDApp):
def __init__(self, kwargs):
super().__init__(kwargs)
self.title = "TwitchDropsMiner"
self.theme_cls.primary_palette = "Purple"
self.theme_cls.theme_style = "Dark"
self.settings = Settings()
self.twitch_client = None
self.screen_manager = None
self.logs = []
--- OPRAVA: Asyncio setup ---
self.loop = asyncio.new_event_loop()
self.async_thread = threading.Thread(target=self._run_event_loop, daemon=True)
self.async_thread.start()
def _run_event_loop(self):
"""Běží v samostatném vlákně."""
asyncio.set_event_loop(self.loop)
self.loop.run_forever()
def build(self):
self.screen_manager = ScreenManager()
Přidání obrazovek
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
--- OPRAVA: Bezpečné volání UI z async vlákna ---
def _update_ui(self, func, args):
Clock.schedule_once(lambda dt: func(args))
def on_print(self, message: str):
logger.info(message)
Omezení logů na posledních 500 řádků (prevence zaplnění RAM)
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
self._update_ui(self.screen_manager.get_screen('home').update_progress, current, total)
def on_channel(self, channel_name: str):
self._update_ui(self.screen_manager.get_screen('home').update_channel, channel_name)
def on_drop(self, drop):
self._update_ui(self.screen_manager.get_screen('home').update_drop, drop)
def on_inventory(self, inventory: list):
self._update_ui(self.screen_manager.get_screen('inventory').update_inventory, inventory)
def on_notify(self, title: str, message: str):
if platform == 'android':
self._show_android_notification(title, message)
self._update_ui(lambda t: Snackbar(text=t).open(), f"{title}: {message}")
def _show_android_notification(self, title, message):
"""OPRAVA: Korektní Android notifikace s kanálem."""
try:
from jnius import autoclass
Context = autoclass('android.content.Context')
PythonActivity = autoclass('org.kivy.android.PythonActivity')
NotificationManager = autoclass('android.app.NotificationManager')
NotificationChannel = autoclass('android.app.NotificationChannel')
NotificationCompat = autoclass('androidx.core.app.NotificationCompat')
activity = PythonActivity.mActivity
channel_id = "twitch_drops_miner"
Vytvoření kanálu (vyžadováno pro Android 8+)
importance = NotificationManager.IMPORTANCE_DEFAULT
channel = NotificationChannel(channel_id, "Twitch Miner Notifications", importance)
notification_manager = activity.getSystemService(Context.NOTIFICATION_SERVICE)
notification_manager.createNotificationChannel(channel)
Sestavení notifikace
builder = NotificationCompat.Builder(activity, channel_id)
builder.setContentTitle(title)
builder.setContentText(message)
builder.setSmallIcon(activity.getApplicationInfo().icon)
builder.setAutoCancel(True)
notification_manager.notify(1, builder.build())
except Exception as e:
logger.error(f"Android Notification Error: {e}")
--- ACTIONS ---
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
Korektní ukončení smyčky při zavření aplikace
self.loop.call_soon_threadsafe(self.loop.stop())
self.settings.save(force=True)
def main():
"""Main entry point."""
TwitchDropsMinerApp().run()
if __name__ == '__main__':
main()
