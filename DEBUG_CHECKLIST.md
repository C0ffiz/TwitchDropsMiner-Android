# TwitchDropsMiner Android — Debug Checklist

Use this file to track test results. Mark each item ✅ (pass), ❌ (fail), or ⚠️ (partial/needs investigation).

---

## Pre-flight (import / startup)

| # | Check | Result | Notes |
|---|---|---|---|
| 1 | `python main.py` launches without import errors | | |
| 2 | KivyMD dark theme applies (dark background visible) | | |
| 3 | No uncaught exceptions in console during startup | | |

---

## Flow A — First Launch (no saved token)

**Expected**: App shows `LoginScreen`. Device code flow starts automatically in background.

| # | Check | Result | Notes |
|---|---|---|---|
| A1 | `LoginScreen` is shown at startup (not AppScreen) | | |
| A2 | Within ~3 s, activation code (8 chars, e.g. `MCWVKSSZ`) appears on screen | | |
| A3 | Instruction label shows "Visit the link below and enter the code:" | | |
| A4 | Status label shows "Waiting for activation…" | | |
| A5 | "Open Twitch Website" button is visible and enabled | | |
| A6 | Tapping "Open Twitch Website" opens browser (or `webbrowser.open` fires) | | |
| A7 | `on_login_code` logged in LogsScreen after activation code appears | | |

---

## Flow B — Device Code Activation (complete the login)

**Expected**: User enters code on twitch.tv/activate → app transitions to `AppScreen`.

| # | Check | Result | Notes |
|---|---|---|---|
| B1 | After activating the code in browser, app navigates to `AppScreen` within `interval` seconds | | |
| B2 | `MDNavigationBar` is visible at bottom with 4 tabs | | |
| B3 | "Main" tab is selected and active by default | | |
| B4 | `settings.json` file is written with `oauth_token` and `username` | | |
| B5 | `console` / log shows "Logged in as: <username>" | | |

---

## Flow C — Startup with Saved Token

**Expected**: App skips `LoginScreen`, shows `AppScreen` immediately, validates token in background.

| # | Check | Result | Notes |
|---|---|---|---|
| C1 | After B completes, close and reopen the app | | |
| C2 | `AppScreen` (bottom nav) shown immediately — no `LoginScreen` | | |
| C3 | Console shows "Logged in as: <username>" from background validation | | |
| C4 | If token is expired/invalid, `LoginScreen` reappears and device code starts | | |

---

## Flow D — Mining (Main Tab)

**Expected**: User presses "Start Mining", miner loop begins, labels update.

| # | Check | Result | Notes |
|---|---|---|---|
| D1 | "Start Mining" button visible on Main tab | | |
| D2 | Pressing "Start Mining" fire `start_mining()` — confirmed via log "Starting TwitchDropsMiner…" | | |
| D3 | Status label updates ("Fetching inventory…", "Gathering channels…") | | |
| D4 | Channel label updates to a real channel name once watching starts | | |
| D5 | Drop label updates to drop name + game (or "No active drop") | | |
| D6 | Progress bar animates as minutes accumulate | | |
| D7 | Pressing "Stop Mining" shows "Stopping…" → "Stopped" in status label | | |
| D8 | After stopping, "Start Mining" can restart the miner | | |
| D9 | Console / Logs screen shows mining state transitions | | |

---

## Flow E — Navigation Bar (Tab Switching)

| # | Check | Result | Notes |
|---|---|---|---|
| E1 | Tapping "Inventory" tab switches inner screen to `InventoryTabScreen` | | |
| E2 | Tapping "Settings" tab switches to `SettingsTabScreen` | | |
| E3 | Tapping "Help" tab switches to `HelpTabScreen` | | |
| E4 | Tapping "Main" tab returns to `MainTabScreen` | | |
| E5 | Navigation indicator pill animates to the selected tab | | |
| E6 | Tab content is NOT reset when switching back and forth | | |

---

## Flow F — Inventory Tab

| # | Check | Result | Notes |
|---|---|---|---|
| F1 | Before mining starts: shows "No campaigns available" | | |
| F2 | After mining starts and inventory loads: shows campaign list | | |
| F3 | Each list item shows campaign name (headline) | | |
| F4 | Each list item shows "GameName — status" (supporting text) | | |
| F5 | List is scrollable when there are many campaigns | | |
| F6 | Switching away and back to Inventory tab re-syncs with latest inventory | | |

---

## Flow G — Settings Tab

| # | Check | Result | Notes |
|---|---|---|---|
| G1 | Username label shows "Logged in as: <username>" | | |
| G2 | "Auto Claim Drops" switch reflects saved setting | | |
| G3 | Toggling "Auto Claim Drops" writes to `settings.json` immediately | | |
| G4 | "Notifications" switch reflects saved setting | | |
| G5 | Toggling "Notifications" writes to `settings.json` | | |
| G6 | "Logout" button: stops mining, clears token, goes to LoginScreen | | |
| G7 | After logout, device code flow starts automatically | | |

---

## Flow H — Help Tab

| # | Check | Result | Notes |
|---|---|---|---|
| H1 | Version string displayed ("TwitchDropsMiner Android vX.Y.Z") | | |
| H2 | Help text visible and readable | | |
| H3 | "Open on GitHub" button opens browser | | |

---

## Flow I — Channels Screen (secondary screen)

| # | Check | Result | Notes |
|---|---|---|---|
| I1 | Tapping the "account-multiple" icon in Main tab toolbar navigates to `ChannelsScreen` | | |
| I2 | `ChannelsScreen` shows channel names + status text | | |
| I3 | List rebuilds correctly after `on_channels` callback fires | | |
| I4 | Tapping back arrow (toolbar) returns to `AppScreen` | | |
| I5 | Hardware/device back button returns to `AppScreen` (not exit) | | |

---

## Flow J — Logs Screen (secondary screen)

| # | Check | Result | Notes |
|---|---|---|---|
| J1 | Tapping the "text-box-outline" icon in Main tab toolbar navigates to `LogsScreen` | | |
| J2 | Existing buffered log messages are shown on first entry | | |
| J3 | New log messages added in real-time while screen is open | | |
| J4 | List auto-scrolls to the newest entry | | |
| J5 | Clear (trash icon) button empties the list and `app.logs` buffer | | |
| J6 | Back arrow returns to `AppScreen` | | |

---

## Flow K — Drop Claimed (end-to-end)

| # | Check | Result | Notes |
|---|---|---|---|
| K1 | When a drop is claimed, `on_notify` fires → MDSnackbar shows briefly | | |
| K2 | Inventory tab refreshes to reflect the claimed drop | | |
| K3 | Progress bar resets for next drop in the same campaign | | |

---

## Known Intentional Differences from Desktop (do NOT flag these as bugs)

| Item | Desktop behaviour | Android behaviour |
|---|---|---|
| Mining auto-start | Starts automatically after login | User must press "Start Mining" |
| System tray | Yes (pystray) | Not applicable |
| Window persistence | Stays open when minimized | Lifecycle managed by Android OS |
| `lock_file()` | OS file lock prevents double-launch | No-op stub (single-process sandbox) |
| Notification backend | OS notifications (pystray/win32) | `plyer.notification` (toast) |

---

## Common Failure Modes to Watch

| Symptom | Likely cause | Where to look |
|---|---|---|
| Activation code never appears | `start_device_login()` raised before completing | Console / Logs screen — look for "Device login error:" |
| App stuck on LoginScreen after activation | `on_login_success` callback not firing | Check `callbacks['on_login_success']` is wired in `build()` |
| Blank Inventory after mining starts | `update_inventory` callback not reaching UI thread | Check `Clock.schedule_once` path in `main.py` |
| Channels tab empty | `on_channels` callback not firing, or `channel.status_text` raises | Check `core/channel.py` `status_text` property |
| Progress bar never moves | PubSub `drop-progress` messages not received, or `_drops` dict miss | Check `process_drops` and `self._drops` population |
| `AttributeError: 'NoneType'` in UI callback | `twitch_client` or `settings` accessed before `build()` finishes | Check deferred init order |
| App crashes on token expiry | `RequestInvalid` not caught in polling loop | Check `start_device_login` exception handler |
