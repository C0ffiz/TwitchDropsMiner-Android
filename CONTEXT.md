# Project Context for Copilot Agent

---

## How to use this file across chat sessions

GitHub Copilot Premium requests have a token limit per session. When a session ends:
1. **Start a new chat** — the previous conversation is gone, but this file persists on disk.
2. **Always attach `CONTEXT.md` and `copilot-instructions.md`** at the start of the new chat (drag them into the attachment area, or use `#file`).
3. **Tell the agent which session to do next** — e.g. "do S6".
4. The agent must read the target file(s) and the upstream equivalent before making any changes.
5. After completing a session, the agent updates the Summary Table (marks ✅, advances "Next") and updates the Decisions Log if new choices were made.

**Never remove old decisions from the log** — they prevent the next session from re-debating settled questions.

---

## Summary Table — Full Plan at a Glance

| # | Session | File | Type | Tier |
|---|---|---|---|
| ✅ | Done | `core/version.py` | port | — |
| ✅ | Done | `core/exceptions.py` | port | — |
| ✅ | Done | `core/constants.py` | gap-check vs upstream | — |
| ✅ | Done | `core/utils.py` | gap-check vs upstream | — |
| ✅ | Done | `core/settings.py` | gap-check + Android paths | — |
| ✅ | Done | `core/cache.py` | gap-check | — |
| ✅ | Done | `core/notifications.py` | Android rewrite | — |
| ✅ | Done | `core/inventory.py` Part A | structure audit vs upstream | 🟠 Medium |
| ✅ | Done | `core/inventory.py` Part B | Android adaptation | 🟠 Medium |
| ✅ | Done | `core/channel.py` Part A | structure audit vs upstream | 🟠 Medium |
| ✅ | Done | `core/channel.py` Part B | Android adaptation | 🟠 Medium |
| ✅ | Done | `core/websocket_client.py` Part A | structure audit vs upstream | 🔴 Heavy |
| ✅ | Done | `core/websocket_client.py` Part B | Android adaptation | 🔴 Heavy |
| ✅ | Done | `core/twitch_client.py` Part A | device code OAuth (Phase 7) | 🔴 Heavy |
| ✅ | Done | `core/twitch_client.py` Part B | mining loop + callbacks audit | 🔴 Heavy |
| ✅ | Done | `main.py` | callbacks + ScreenManager prep | 🟠 Medium |
| ✅ | Done | `ui/screens.py` Part A | MDBottomNavigation shell (Phase 1) | 🔴 Heavy |
| ✅ | Done | `ui/screens.py` Part B | LoginScreen device code UI (Phase 2) | 🟠 Medium |
| ✅ | Done | `ui/screens.py` Part C | MainTab (Phase 3) | 🟠 Medium |
| ✅ | Done | `ui/screens.py` Part D | InventoryTab (Phase 4) | 🟠 Medium |
| ✅ | Done | `ui/screens.py` Part E | SettingsTab + HelpTab (Phases 5+6) | 🟠 Medium |
| ✅ | Done | `ui/screens.py` Part F | LogsScreen + ChannelsScreen (Phase 8) | 🟢 Light |
| ✅ | Done | Import audit | all `core/` + `ui/` | ⚫ Integration |
| ✅ | Done | `buildozer.spec` + `requirements.txt` | dependency audit | 🟠 Medium |
| ✅ | Done | Bug fix: GQL headers | add X-Device-Id, Client-Session-Id, Origin, Referer; auto-start mining | 🟠 Medium |
| ✅ | Done | Bug fix: `failed integrity check` | switch WEB → ANDROID_APP; drop `_ensure_integrity()`; add client_id mismatch check | 🟠 Medium |

---

## ⚠️ Next Steps (for next chat session)

After the ANDROID_APP switch the **saved WEB token will fail** (client_id mismatch → `login()` raises `LoginException` → `_start_login_validation` falls back to device login screen automatically). Users will need to log in once with the new ANDROID_APP device code. That is expected and handled.

**What to verify in the next session:**
1. Run `python main.py`, expect device login screen (old WEB token cleared by mismatch detection).
2. Complete device login → should navigate to AppScreen and auto-start mining.
3. Confirm `fetch_inventory()` succeeds (no GQL errors in log).
4. Confirm `InventoryTabScreen` displays campaigns.
5. If GQL still fails, capture the **exact error message** and the `[GQL request payload]` that precedes it.

---

## Decisions Log

These are design choices already made. Do NOT reverse or re-debate them.

| Decision | Rationale |
|---|---|
| `proxy` field stored as `str` (not `yarl.URL`) in `settings.py` | Avoids yarl dependency at settings-import time; `aiohttp` accepts str URLs |
| `BACKGROUND_WATCH_INTERVAL` removed from `constants.py` | Was defined but never referenced anywhere in the project |
| Dead GQL aliases (`GetDropCampaigns`, `GetInventory`, `GetDirectory`) removed from `constants.py` | Callers already use canonical names (`Campaigns`, `Inventory`, `GameDirectory`) |
| `PIL` imported lazily in `cache.py` via `try/except` with `_HAS_PIL` flag | Pillow is not installed in the dev venv; guards `_hash()` and `get()` with `RuntimeError` |
| `ImageCache` is unused by any other module today | Not yet wired into `TwitchClient`; reserved for future drop image display in UI |
| `webopen()` in `utils.py` uses Android Intent → `webbrowser` fallback | Desktop `LD_LIBRARY_PATH` workaround is not needed on Android |
| `lock_file()` in `utils.py` is a no-op stub | Android sandbox is single-process; OS-level file locking unavailable and unnecessary |
| `task_wrapper` critical path uses `core.twitch_client.TwitchClient` (not upstream `from twitch import Twitch`) | Avoids circular import on Android; same runtime behaviour |
| `Settings.__init__` takes no args (no `ParsedArgs`) | No CLI on Android; env-var overrides still apply |
| `Settings.load()` / `migrate()` split out of `__init__` | Allows deferred init after `App.user_data_dir` is ready |
| `get_app_paths()` deferred function (not module-level constants) | `App.user_data_dir` is only available after Kivy App starts |
| `notifications.py` has `_APPRISE_AVAILABLE` + `_PLYER_AVAILABLE` guards | Both are optional on Android build; code degrades gracefully |
| `AndroidNotification` class added (no upstream base) | Thin plyer wrapper for on-device toast/system notifications |
| `AppriseNotifier` unchanged from upstream logic | Discord/webhook logic is platform-agnostic; only import guard differs |
| `BaseDrop.generate_claim()` uses `settings.user_id` directly | `get_auth()` doesn't exist on `TwitchClient`; user_id already stored in `settings.user_id` |
| `BaseDrop.claim()` fires `update_inventory()` on success | InventoryTab must refresh when a drop is claimed; `notify_drop` alone does not update the tab |
| `TimedDrop._on_state_changed()` calls `self._twitch.update_drop(self)` | Replaces upstream `gui.inv.update_drop(self)`; fires `on_drop` callback to keep Main tab progress bar current |
| `_gui_channels` slot removed from `Channel.__slots__` | Was always `None`; `display()` and `remove()` now use `update_channels()` directly; dead slot removed to prevent future confusion |
| `Channel.status_text` returns rich online string | Format: "Online — GameName — 1,234 viewers"; used by ChannelsScreen |
| `Channel.remove()` fires `update_channels()` | Called after `del channels[ch.id]`; ChannelsScreen needs to reflect the removal |
| `Channel._check_drops_enabled()` uses `self._twitch._campaigns` | `_campaigns` is a `dict[str, DropsCampaign]`; matches upstream; previous `{c.id: c for c in inventory}` was O(n) and wrong |
| `MDNavigationBar` from `kivymd.uix.navigationbar`; not the deprecated `MDBottomNavigation` | KivyMD 2.0 renamed `MDBottomNavigation` → `MDNavigationBar`; KV file sets `size_hint_y=None, height=80dp` automatically |
| `AppScreen` inherits from `Screen` (not `BaseScreen`) and uses `MDBoxLayout` as outer layout | Follows KivyMD 2.x official example exactly: MDBoxLayout → MDScreenManager + MDNavigationBar |
| `on_switch_tabs` handler signature is `(self, bar, item, item_icon, item_text)` | Kivy event dispatch prepends the dispatching object; `item_text.lower()` maps to MDScreen names 'main'/'inventory'/'settings'/'help' |
| Tab screen names lowercase match `item_text.lower()`: 'main', 'inventory', 'settings', 'help' | `_NavItem` text must match `MDScreen.name` exactly (case-insensitive via `.lower()`) |
| `HomeScreen`, `InventoryScreen`, `SettingsScreen` removed from `screens.py` | All replaced by `MainTabScreen`, `InventoryTabScreen`, `SettingsTabScreen` inside `AppScreen` |
| `InventoryTabScreen.update_inventory` uses `campaign.status_text` | Added to `DropsCampaign` in S7; safe to reference here |
| `AppScreen` is the single post-login screen in ScreenManager (not `HomeScreen`) | MDBottomNavigation lives inside AppScreen; LoginScreen is the pre-login overlay |
| `ChannelsScreen` and `LogsScreen` remain top-level ScreenManager entries | Pushed on top of AppScreen; back button (`on_key_back`) returns to `'app'` |
| `main.py` `login(oauth_token)` method removed | Device code flow fires `on_login_success` callback instead; no manual token paste |
| `_start_login_validation()` runs `TwitchClient.login()` at startup when saved token exists | On exception, switches back to login screen and restarts device code flow |
| Auto-mining starts after both login paths | `_start_login_validation` calls `start_mining()` on success; `on_login_success` calls `start_mining()` after navigating to AppScreen — ensures inventory is fetched immediately without pressing Start |
| GQL requests include `X-Device-Id` and `Client-Session-Id` headers | Twitch integrity check requires these; `_device_id` (32-char hex) and `_session_id` (16-char hex) generated at `TwitchClient.__init__` via `create_nonce`; session headers expanded to match upstream `auth_state.headers()` |
| GQL requests include `Origin` and `Referer: CLIENT_URL` per-request | Mirrors upstream `auth_state.headers(gql=True)` which adds these for GQL calls; passed as per-request headers on `session.post()` |
| `CLIENT_URL: str` exported from `core/constants.py` | Shim alongside `CLIENT_ID` and `USER_AGENT`; needed by `twitch_client.py` for GQL Origin/Referer headers |
| `login()` verifies `client_id` in `/oauth2/validate` response matches `CLIENT_ID` | Mirrors upstream `_AuthState._validate()` client mismatch check; catches stale tokens from a previous client type (e.g. old WEB token when client switched to ANDROID_APP) and raises `LoginException` so the caller falls back to device login |
| `_ensure_integrity()` removed; `Client-Integrity` header not sent | `integrity.twitch.tv` DNS does not resolve in the target environment; ANDROID_APP client type does not require the Client-Integrity JWT — upstream TwitchDropsMiner uses ANDROID_APP without any integrity token and GQL works correctly |
| `DEFAULT_CLIENT_TYPE = ClientType.ANDROID_APP` (not `WEB`) | Device code OAuth tokens are issued for the client ID used to request them; ANDROID_APP matches upstream exactly and does NOT trigger the `failed integrity check` GQL error that WEB triggers; the old WEB decision only held when tokens were pasted manually from the browser — since we use device code exclusively, ANDROID_APP is the correct choice |
| `WebsocketPool.remove_topics` uses upstream recycling loop | Android had simplified version that only stripped empty-last-WS; upstream recycles underfull websockets into fewer connections — bug fixed in S10 |
| `_handle_topics` uses `settings.oauth_token` directly (no `get_auth()`) | `get_auth()` doesn't exist on `TwitchClient`; decision carried forward from S10 audit |
| `_handle_topics` strips `oauth:` prefix before sending to PubSub | `settings.oauth_token` may contain `oauth:` prefix from old manual-paste login; PubSub requires bare access token; inlined strip avoids calling private `_clean_token` across module boundary |
| `_handle_topics` returns early if auth token is empty | Defensive guard: if token is somehow falsy after login (shouldn't happen but possible race), skip topic update with warning rather than send `auth_token: null` to Twitch |
| `set_status(refresh_topics=True)` logs topic count on Android | Replaces upstream GUI websocket widget counter; keeps diagnostics visible in `ws_logger.debug` output |
| `start_device_login()` uses two independent `aiohttp.ClientSession` context managers | One for the device code POST, one for the polling loop — avoids polluting the main mining session; dedicated auth session torn down when polling completes or code expires |
| `start_device_login()` handles expiry via `datetime` comparison, not `invalidate_after` | Android `request()` ctx manager has no `invalidate_after` param; polling loop checks `datetime.now(utc) >= expires_at` and breaks to outer loop to fetch a new code |
| `start_device_login()` calls `close_session()` before `login()` on success | Forces `get_session()` to rebuild the main aiohttp session with the new `Authorization: OAuth <token>` header |
| `on_login_success` callback fired by `start_device_login()` after `login()` validates | UI registers this callback to navigate from LoginScreen to AppScreen (bottom nav) |
| `self.channels` typed as `OrderedDict[int, Channel]` in `TwitchClient.__init__` | Matches upstream; Python 3.7+ dicts are ordered but `OrderedDict` makes intent explicit and removes `type: ignore` on the `_run()` channels alias |
| `_watch_loop()` always queries GQL after each 20s sleep (no `minute_almost_done` guard) | Android has no GUI progress timer; GQL is the only source of drop progress truth; always querying is a safe, correct deviation from upstream |
| 4 unused imports removed from `core/twitch_client.py` | `deepcopy`, `CaptchaRequired`, `ExitRequest`, `create_nonce` — imported but never referenced in the module body; removed to keep the import block honest |
| All other imports in `core/` + `ui/` verified clean | Syntax OK + runtime import OK for all non-Kivy modules; `yarl` in `channel.py` is fine (transitive aiohttp dep); `aiohttp` guard in `notifications.py` is already correct |

---

## Current File Status

State of each file in `TwitchDropsMiner-Android/core/` as of the last completed session.

| File | Status | Notes |
|---|---|---|
| `core/version.py` | ✅ complete | Straight port; exposes `VERSION` tuple and `__version__` string |
| `core/exceptions.py` | ✅ complete | All upstream exceptions present; `RequestInvalid` added for device code expiry |
| `core/constants.py` | ✅ complete | Dead aliases and `BACKGROUND_WATCH_INTERVAL` removed; `get_app_paths()` deferred fn replaces hardcoded paths; `DEFAULT_CLIENT_TYPE = ClientType.WEB` |
| `core/utils.py` | ✅ complete | No changes needed; all upstream functions present; yarl optional; `webopen` uses Android Intent; `is_network_available` added |
| `core/settings.py` | ✅ complete | No changes needed; Android-specific fields added (`oauth_token`, `user_id`, `username`, `auto_claim`, etc.); deferred `load()`/`migrate()` |
| `core/cache.py` | ✅ complete | PIL wrapped in `try/except`; `_HAS_PIL` guard; returns `str` path not `PhotoImage`; deferred init; `clear()`/`invalidate()` added |
| `core/notifications.py` | ✅ complete | `AndroidNotification` (plyer) added; apprise/plyer both optional-import guarded; `AppriseNotifier` logic identical to upstream |
| `core/inventory.py` | ✅ complete | S6: bugs fixed (`generate_claim`, `_on_state_changed`); S7: post-claim `update_inventory()` added; `TimedDrop.status_text` + `DropsCampaign.status_text` added for InventoryTab |
| `core/channel.py` | ✅ complete | S8: 3 bugs fixed (display, remove, _check_drops_enabled); S9: dead `_gui_channels` slot removed; `Channel.status_text` + `Channel.__str__` added for ChannelsScreen |
| `core/websocket_client.py` | ✅ complete | S10: structure audit + `remove_topics` recycling bug fixed; S11: token cleaning (strip `oauth:` prefix), empty-token guard, topic-count logging in `set_status` |
| `core/twitch_client.py` | ✅ complete | S12: `start_device_login()` added; S13: `channels` typed as `OrderedDict`, `type:ignore` removed, `_watch_loop` logs "No active drop" when both GQL and active-campaign fallback fail |
| `core/translate.py` | 🔲 not audited | Present; not yet scheduled |
| `core/registry.py` | 🔲 not audited | Present; not yet scheduled |
| `main.py` | ✅ complete | S14: ScreenManager → LoginScreen+AppScreen+ChannelsScreen+LogsScreen; on_login_code/on_login_success callbacks; device code flow via _start_device_login/_start_login_validation; login() removed |
| `ui/screens.py` | ✅ complete | S15–S20: all screens done. MDNavigationBar shell, LoginScreen, MainTabScreen, InventoryTabScreen, SettingsTabScreen, HelpTabScreen, AppScreen, ChannelsScreen, LogsScreen — all implemented. ChannelsScreen.update_channels uses `channel.status_text` (fixed S20). |

---

## Goal

Adapt features from `TwitchDropsMiner` (JourneyDocker) into `TwitchDropsMiner-Android` (C0ffiz).

## Architecture difference
- **JourneyDocker**: Uses `tkinter` for GUI (`gui.py` at root level), 4 notebook tabs
- **C0ffiz (mine)**: Uses `Kivy/KivyMD` for Android UI (`ui/` folder), bottom navigation

## Key mapping
| JourneyDocker (source) | C0ffiz Android (target) |
|---|---|
| `gui.py` (tkinter) | `ui/screens.py` + KivyMD — DO NOT copy directly |
| Main tab | Main tab inside `MDBottomNavigation` |
| Inventory tab | Inventory tab inside `MDBottomNavigation` |
| Settings tab | Settings tab inside `MDBottomNavigation` |
| Help tab | Help tab inside `MDBottomNavigation` (new) |
| Login dialog (device code) | `LoginScreen` (full-screen overlay, device code flow) |
| `cache.py`, `channel.py`, etc. (root) | `core/` folder equivalents |
| `notifications.py` | KivyMD MDSnackbar + plyer for Android |
| `lang/` | `lang/` folder present; translation not yet wired into UI |
| `settings.py` | `core/settings.py` with `user_data_dir` paths |
| `twitch.py` `_oauth_login()` | `core/twitch_client.py` — device code flow NOT YET implemented |

## Rules for the agent
1. Never replace Kivy/Android UI code with tkinter code.
2. Core logic files (`twitch_client.py`, `websocket_client.py`, etc.) can be closely ported from upstream.
3. File paths and OS calls must be adapted for Android (`App.get_running_app().user_data_dir`).
4. GUI callbacks must use Kivy's `Clock.schedule_once()`, `StringProperty`, `ObjectProperty` — not tkinter variables.
5. Login MUST use the OAuth device code flow — never a manual token paste field.

---

## Implementation Plan

### Phase 1 — Navigation Architecture Redesign
**What:** Replace the flat `ScreenManager` with a proper two-level navigation structure.
**Target structure:**
```
ScreenManager
├── LoginScreen        (full-screen, shown when no token saved)
└── AppScreen          (full-screen shell that owns MDBottomNavigation)
    ├── MainTab        (status, current channel, drop + progress, Start/Stop)
    ├── InventoryTab   (scrollable campaigns list)
    ├── SettingsTab    (switches, account info, logout)
    └── HelpTab        (static help text + app version)
```
**Secondary screens** (pushed on top of AppScreen, back returns to AppScreen):
- `LogsScreen` — reached via top-bar icon on MainTab
- `ChannelsScreen` — reached via top-bar icon on MainTab
**Files to change:** `main.py`, `ui/screens.py`
**Reference:** No upstream equivalent; pure Android UX design decision.

---

### Phase 2 — Login Flow Redesign (Device Code)
**What:** Replace the current manual token-entry `LoginScreen` with the proper OAuth device code flow used by the desktop app.
**Step-by-step flow:**
1. User presses **"Login with Twitch"** button.
2. `TwitchClient.start_device_login()` is called (new async method):
   - POST `https://id.twitch.tv/oauth2/device` with `CLIENT_ID`
   - Receives: `user_code` (8 chars), `verification_uri`, `device_code`, `interval`, `expires_in`
3. Fires callback `on_login_code(user_code, verification_uri)` → `LoginScreen` displays:
   - The code prominently (e.g., `MCWVKSSZ`)
   - A **"Open Twitch Website"** button that calls `webbrowser.open(verification_uri)` (Android opens Chrome/browser intent)
   - A "Waiting for activation…" spinner
4. Background polling loop every `interval` seconds:
   - POST `https://id.twitch.tv/oauth2/token` with `device_code`
   - On HTTP 200: extract `access_token`, save to `settings.oauth_token`, call `on_login_success()`
   - On HTTP 400 (pending): continue polling
   - On code expiry (`expires_in` elapsed): restart from step 2; fire `on_login_code` again with new code
5. `on_login_success()` → navigate to `AppScreen` (bottom nav).
**Files to change:** `core/twitch_client.py` (add `start_device_login` and polling loop), `ui/screens.py` (`LoginScreen` redesign), `main.py` (add `on_login_code` callback route).
**Reference:** `TwitchDropsMiner/twitch.py` → `_AuthState._oauth_login()` — port this logic, removing all GUI calls and routing through callbacks.

---

### Phase 3 — Main Tab
**What:** The `MainTab` inside `MDBottomNavigation` replaces `HomeScreen`.
**UI elements:**
- `MDTopAppBar` with:
  - Title: "TwitchDropsMiner"
  - Trailing icons: channels icon (→ `ChannelsScreen`) and logs icon (→ `LogsScreen`)
- Status card: status string + current username (once logged in)
- Current channel card: channel display name
- Active drop card: drop name + game + `MDLinearProgressIndicator` (minutes progress)
- Start / Stop mining `MDButton`s
**Callbacks consumed:** `on_status`, `on_channel`, `on_drop`, `on_progress`
**Files to change:** `ui/screens.py` — replace `HomeScreen` logic inside new `MainTab` class.

---

### Phase 4 — Inventory Tab
**What:** The `InventoryTab` inside `MDBottomNavigation` replaces `InventoryScreen`.
**UI elements:**
- Scrollable `MDList` of campaigns
- Each `MDListItem` should show:
  - Headline: campaign name
  - Supporting text: game name
  - Trailing text/icon: status (In Progress / Completed / Not Started)
  - Optional: progress bar per drop benefit
**Callbacks consumed:** `on_inventory`
**Files to change:** `ui/screens.py`.
**Reference:** `TwitchDropsMiner/gui.py` → `DropsCampaignView` for data fields to display.

---

### Phase 5 — Settings Tab
**What:** The `SettingsTab` inside `MDBottomNavigation` replaces `SettingsScreen`.
**UI elements:**
- Auto-claim drops toggle (`MDSwitch`)
- Notifications toggle (`MDSwitch`)
- Account section: display username, **Logout** button
- (Optional future) Language selector
**Files to change:** `ui/screens.py`.

---

### Phase 6 — Help Tab (new)
**What:** A static informational screen — no upstream equivalent.
**UI elements:**
- How-to-use text (brief)
- Link to GitHub / README
- App version from `core/version.py`
**Files to change:** `ui/screens.py`.

---

### Phase 7 — Core: Device Code OAuth in `twitch_client.py`
**What:** Add the device code flow (currently missing; the current `login()` only validates an existing token).
**New method:** `start_device_login()` — async method that:
- POSTs to `/oauth2/device`
- Fires `on_login_code` callback
- Enters polling loop (mirrors `_AuthState._oauth_login` from upstream)
- On success, sets `settings.oauth_token = access_token`, calls `settings.save()`, fires `on_login_success`
**Keep existing `login()`** for the validation path (used when a saved token already exists at startup).
**Files to change:** `core/twitch_client.py`, `main.py` (add `on_login_code` and `on_login_success` callbacks).

---

### Phase 8 — Logs & Channels as Secondary Screens
**What:** `LogsScreen` and `ChannelsScreen` remain separate screens but are navigated to from MainTab's top bar, not from a button row inside the tab content.
**Back navigation:** Back button (hardware or toolbar) returns to `AppScreen`.
**Files to change:** `ui/screens.py`, `main.py` (screen registration).

---

## Current known gaps (to be resolved during implementation)
| Gap | Phase |
|---|---|
| No device code flow in `twitch_client.py` | 7 |
| `LoginScreen` uses manual token paste | 2 |
| No `MDBottomNavigation` — flat ScreenManager | 1 |
| No HelpTab | 6 |
| Inventory shows only name+game, no status/progress | 4 |
| `on_login_code` callback not defined anywhere | 2, 7 |
| Language/translation system not wired to UI | future |
| `apprise` added to `buildozer.spec` requirements | Optionally imported in `notifications.py` — must be present in the Android build for webhook notification feature |
| `requests` removed from `requirements.txt` | Never imported; project uses `aiohttp` exclusively; was copied verbatim from upstream |
| `pyjnius` removed from `requirements.txt` | It is a p4a recipe, not a pip package; it cannot install on a Windows dev machine; remains in `buildozer.spec` requirements where it belongs |
| `apprise>=1.9.0` added to `requirements.txt` | Mirrors the addition to `buildozer.spec`; allows local dev/testing of webhook notification paths |
| `apprise` removed from `buildozer.spec` requirements | No p4a recipe; C-extension deps fail cross-compile; `notifications.py` already guards with `_APPRISE_AVAILABLE`; plyer handles on-device notifications |
| `android.archs = arm64-v8a` (was armeabi-v7a) | Samsung S23 FE (Snapdragon 8 Gen 1) is 64-bit only; Android 14 One UI 6.1 has no 32-bit userspace; 32-bit-only APK rejected by Package Manager |
| `android.api = 34`, `android.minapi = 24`, `android.ndk_api = 24` | Targets Android 14 requirements; minapi 24 aligns with Kivy's real minimum and avoids ndk_api mismatch |
| `package.domain = io.github.c0ffiz` | `org.example` is a placeholder; changed to GitHub-convention domain before any distribution |
| `WRITE_EXTERNAL_STORAGE`/`READ_EXTERNAL_STORAGE` removed from permissions | Deprecated API 29+, ignored on API 33+; no code path uses external storage — all I/O uses `user_data_dir` |
| `source.exclude_dirs = venv` added to `buildozer.spec` | Ensures entire `venv/` tree is excluded; `venv/*` pattern only excluded top-level children |
| `ssl.create_default_context(cafile=certifi.where())` + `aiohttp.TCPConnector(ssl=...)` | p4a's OpenSSL does not see Android system CA store; explicit certifi bundle required for all HTTPS/WSS |
| `cython>=3.0.0,<4.0.0` in CI (was `cython==0.29.37`) | Kivy 2.3.0 p4a recipe requires Cython 3.x; 0.29.x fails to compile Kivy `.pyx` files |
| `buildozer>=1.5.0`, `python-for-android>=2023.9.0,<2025.0.0` pinned in CI | Unpinned `--upgrade` installs caused non-reproducible builds on breaking p4a HEAD changes |
| `platforms;android-34` + `build-tools;34.0.0` installed in CI | Required to compile against `android.api = 34`; was android-33/33.0.2 |
| `on_start()` requests `Permission.POST_NOTIFICATIONS` at runtime | Android 13+ requires runtime grant; manifest declaration alone is silent-fail |
| `on_stop()` join timeout reduced 5 s → 3 s with alive-check warning | Stays under Android ANR watchdog threshold; logs warning instead of silently timing out |
| `MDNavigationBar` constructed with `add_widget()` loop (not positional args) | Kivy `Widget.__init__(**kwargs)` does not accept positional children; positional pattern raises `TypeError` at app start |

---

## 🛠️ Android Compatibility Remediation Plan

### Root Cause Statement

The error **"Este app não é compatível com a versão mais recente do Android"** on the Samsung Galaxy S23 FE (Android 14 / One UI 6.1) was caused by a **CPU architecture mismatch**.

The build targeted `android.archs = armeabi-v7a` (32-bit ARM only). The Samsung Galaxy S23 FE uses a Snapdragon 8 Gen 1 SoC which is `arm64-v8a` (64-bit ARM). Samsung's Android 14 ships without 32-bit userspace libraries on this device. The Package Manager rejected the APK with the "not compatible" dialog before any Python code ran.

**Primary fix:** `android.archs = arm64-v8a` — **✅ DONE**

**Secondary blockers fixed in the same pass:**
- Missing certifi SSL context → all HTTPS/WSS fails on Android (✅ DONE)
- Cython 0.29.x incompatible with Kivy 2.3.0 p4a recipe (✅ DONE)
- MDNavigationBar positional-arg constructor crash at startup (✅ DONE)

---

### Implementation Status Table

| Step | ID | Priority | Layer | Change | File(s) | Done? |
|---|---|---|---|---|---|---|
| 1 | S-ABI | 🔴 BLOCKER | Build | `android.archs = arm64-v8a` | `buildozer.spec` | ✅ |
| 2 | S-SSL | 🔴 BLOCKER | Network | certifi SSL context in `get_session()` | `core/twitch_client.py` | ✅ |
| 3 | S-API34 | 🟠 HIGH | Build/Manifest | `android.api = 34`; CI installs `platforms;android-34` | `buildozer.spec`, `build-android.yml` | ✅ |
| 4 | S-APPRISE | 🟠 HIGH | Build | Remove `apprise` from `buildozer.spec` requirements | `buildozer.spec` | ✅ |
| 5 | S-CYTHON | 🟠 HIGH | Build | `cython>=3.0.0,<4.0.0` in CI | `build-android.yml` | ✅ |
| 6 | S-P4A-PIN | 🟠 HIGH | Build | Pin `buildozer>=1.5.0`, `python-for-android>=2023.9.0` | `build-android.yml` | ✅ |
| 7 | S-NOTIF-RT | 🟠 HIGH | Permissions | `on_start()` requests `POST_NOTIFICATIONS` at runtime | `main.py` | ✅ |
| 8 | S-FGSTYPE | 🟠 HIGH | Manifest | Add `android:foregroundServiceType` when background service is added | `buildozer.spec` | ⏳ defer — no service declared yet |
| 9 | S-STORAGE | 🟡 MEDIUM | Manifest | Remove `WRITE_EXTERNAL_STORAGE`/`READ_EXTERNAL_STORAGE` | `buildozer.spec` | ✅ |
| 10 | S-VENV | 🟡 MEDIUM | Build | `source.exclude_dirs = venv` | `buildozer.spec` | ✅ |
| 11 | S-P4A-BRANCH | 🟡 MEDIUM | Build | pip-pinned p4a supersedes `p4a.branch`; left as `master` | `buildozer.spec` | ✅ (via pip pin) |
| 12 | S-DOMAIN | 🟡 MEDIUM | Manifest | `package.domain = io.github.c0ffiz` | `buildozer.spec` | ✅ |
| 13 | S-NAVBAR | 🟡 MEDIUM | UI | `MDNavigationBar` built with `add_widget()` loop | `ui/screens.py` | ✅ |
| 14 | S-MINAPI | 🟢 LOW | Manifest | `android.minapi = 24`, `android.ndk_api = 24` | `buildozer.spec` | ✅ |
| 15 | S-PATHS | 🟢 LOW | Build | Remove hardcoded `android.sdk_path`/`android.ndk_path` | `buildozer.spec` | ✅ |
| 16 | S-THEME | 🟢 LOW | UI | `"Purple"` palette — verify in KivyMD 2.x; change to `"DeepPurple"` if ValueError | `main.py` | ⏳ verify on first launch |
| 17 | S-JOIN | 🟢 LOW | Threading | `join(timeout=3)` + alive-check warning | `main.py` | ✅ |

### Post-fix Build Verification Checklist

After the next GitHub Actions run, verify:

1. `unzip -l app.apk | grep "lib/"` → only `lib/arm64-v8a/` entries
2. `aapt dump badging app.apk | grep -E "targetSdk|minSdk"` → `targetSdkVersion:'34'`, `minSdkVersion:'24'`
3. `aapt dump badging app.apk | grep "package: name="` → `io.github.c0ffiz.twitchdropsminer`
4. Side-load on S23 FE → no "not compatible" dialog
5. App opens to LoginScreen, completes device code login, navigates to AppScreen
6. No `CERTIFICATE_VERIFY_FAILED` in LogsScreen
7. Mining auto-starts after login; first notification shows Android permission dialog