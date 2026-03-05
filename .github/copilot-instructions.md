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

## Android Debug Setup

**Device:** Samsung Galaxy S23 FE (SM-S711B), serial `RXCX800EP6L`
**Package:** `io.github.c0ffiz.twitchdropsminer`
**Activity:** `org.kivy.android.PythonActivity`
**Build:** `buildozer android debug` → `bin/*.apk`

### Debug workflow
When the user reports a bug on-device:
1. Read the relevant source files before making any changes.
2. Modify the code (fix + ensure sufficient `logger.debug/info` coverage near the bug site).
3. Push changed Python files via adb — no rebuild needed for pure-Python changes:
   ```bash
   adb push <file.py> /sdcard/
   adb shell run-as io.github.c0ffiz.twitchdropsminer cp /sdcard/<file.py> files/app/<path/to/file.py>
   ```
4. Restart the app (no reinstall):
   ```bash
   adb shell am force-stop io.github.c0ffiz.twitchdropsminer
   adb shell am start -n io.github.c0ffiz.twitchdropsminer/org.kivy.android.PythonActivity
   ```
5. Capture logs:
   ```bash
   adb logcat -s python:* AndroidRuntime:E *:F
   ```
6. Only run `buildozer android debug` + `adb install -r bin/*.apk` when native dependencies changed.

### Common adb push paths (relative to `files/app/` on device)
| Local file | Device path |
|---|---|
| `main.py` | `files/app/main.py` |
| `ui/screens.py` | `files/app/ui/screens.py` |
| `core/twitch_client.py` | `files/app/core/twitch_client.py` |
| `core/settings.py` | `files/app/core/settings.py` |
| `core/websocket_client.py` | `files/app/core/websocket_client.py` |
| `core/inventory.py` | `files/app/core/inventory.py` |
| `core/channel.py` | `files/app/core/channel.py` |

### What is already instrumented
- `logging.basicConfig(level=DEBUG)` — all log calls appear in logcat tagged `python`
- `sys.excepthook` + asyncio exception handler in `main.py` — full tracebacks in logcat
- `main.py` — all lifecycle methods and callbacks emit `[TwitchDrops]` debug lines
- `ui/screens.py` — all `on_enter()`, tab switches, list updates emit `[TwitchDrops.UI]` debug lines
- `core/twitch_client.py` — every `_callback()` dispatch and GQL payload logged at DEBUG

## Agent Rules

- **Always start** by running: `adb connect 192.168.68.53:5555`
- **To read crash logs** run: `adb logcat -d -s python:* AndroidRuntime:E *:F`
- **After making code changes**, check which files were modified:
  - `.py` or `.kv` only → proceed with adb push flow (no rebuild needed)
  - `requirements.txt`, `buildozer.spec`, any `.c`/`.pyx`/`.so` file, or any other non-Python file → **stop** and tell the user a full rebuild is required via GitHub Actions
- **adb push flow** (package = `io.github.c0ffiz.twitchdropsminer`):
  1. `adb shell am force-stop io.github.c0ffiz.twitchdropsminer`
  2. For each changed file:
     ```bash
     adb push <local/path/file.py> /sdcard/<file.py>
     adb shell run-as io.github.c0ffiz.twitchdropsminer cp /sdcard/<file.py> files/app/<path/to/file.py>
     ```
  3. `adb shell am start -n io.github.c0ffiz.twitchdropsminer/org.kivy.android.PythonActivity`
  4. Inform the user: "Push successful, app restarted. Please test."
- **Never guess the package name** — always read it from `buildozer.spec` (`package.domain` + `.` + `package.name`)
- **Never trigger a build yourself** — builds are done manually by the user via GitHub Actions (or by running `.\deploy.ps1` after the build completes)
- **After pushing changes, do NOT do `git push`** unless the user explicitly asks
- **deploy.ps1** is the install script: it connects ADB, downloads the latest APK artifact via `gh run download`, installs it with `adb install -r`, and launches the app