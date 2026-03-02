# Copilot Instructions

This is an Android port of TwitchDropsMiner using Kivy/Buildozer.

## Stack
- Python + Kivy / KivyMD 2.x (NOT tkinter)
- Target: Android via Buildozer
- UI: `ui/` folder with `.kv` layout files and Python callback classes
- Core logic: `core/` folder

## Reference project
JourneyDocker/TwitchDropsMiner is the upstream — it uses tkinter.
When adapting code from there:
- Replace `tkinter` imports/calls → Kivy/KivyMD equivalents
- Replace `threading` GUI updates → `Clock.schedule_once()`
- Replace file paths → `App.get_running_app().user_data_dir`
- Replace desktop notifications → Android toast / plyer notifications
- Replace `webopen()` → `webbrowser.open()` or Android intent via `android.intents`

## Navigation architecture (target state)
- Top-level navigation: `MDBottomNavigation` with 4 tabs — Main, Inventory, Settings, Help
- `LoginScreen` is a full-screen overlay outside the bottom nav (shown when no token is saved)
- `LogsScreen` and `ChannelsScreen` are secondary screens reached from the Main tab (top-bar icons)
- The `ScreenManager` wraps at minimum: `LoginScreen`, `MainScreen` (which contains the bottom nav)

## Login flow (device code — matches desktop)
1. POST `https://id.twitch.tv/oauth2/device` → get `user_code`, `verification_uri`, `device_code`, `interval`
2. Display `user_code` prominently to the user; offer a button to open `verification_uri` in Android browser
3. Poll `POST https://id.twitch.tv/oauth2/token` every `interval` seconds in background (asyncio)
4. On 200 response, save `access_token` to settings, navigate to MainScreen (bottom nav)
5. On code expiry (`RequestInvalid`), restart from step 1

## Callbacks (core → UI bridge)
All async state changes call `self._callback(name, ...)` in `TwitchClient` which routes to:
- `on_login_code(user_code, verification_uri)` — display activate code on LoginScreen
- `on_status(status_str)` — update status label on Main tab
- `on_channel(channel_name)` — update current channel label on Main tab
- `on_drop(drop_obj)` — update drop label + progress bar on Main tab
- `on_progress(current, total)` — update progress bar on Main tab
- `on_inventory(inventory_list)` — rebuild campaign list on Inventory tab
- `on_channels(channels_dict)` — rebuild channel list on ChannelsScreen
- `on_print(message)` — append to LogsScreen buffer
- `on_notify(title, message)` — show MDSnackbar or plyer notification

## Do NOT
- Add tkinter imports
- Use `os.startfile()` or Windows-specific paths
- Break existing Kivy UI callbacks in `ui/`
- Require manual OAuth token paste — use device code flow only