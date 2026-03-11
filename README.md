# Twitch Drops Miner — Android

[![Build](https://github.com/C0ffiz/TwitchDropsMiner-Android/actions/workflows/build-android.yml/badge.svg)](https://github.com/C0ffiz/TwitchDropsMiner-Android/actions/workflows/build-android.yml)
[![Release](https://img.shields.io/github/v/release/C0ffiz/TwitchDropsMiner-Android?label=latest)](https://github.com/C0ffiz/TwitchDropsMiner-Android/releases/latest)
[![Android](https://img.shields.io/badge/Android-7.0%2B%20(API%2024)-brightgreen?logo=android)](https://github.com/C0ffiz/TwitchDropsMiner-Android/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://www.python.org/)

An Android app that mines Twitch channel point drops automatically — runs in the background, claims drops, and keeps you notified without touching your desktop.

Based on [JourneyDocker/TwitchDropsMiner](https://github.com/JourneyDocker/TwitchDropsMiner), rewritten for Android using Python + [Kivy](https://kivy.org/) / [KivyMD](https://kivymd.readthedocs.io/).

---

## Screenshots

<p align="center">
  <img src="https://github.com/user-attachments/assets/107b23e4-7bd8-4c0f-92e5-8e1bec81fc38" width="18%" />
  <img src="https://github.com/user-attachments/assets/879fda21-58df-4198-92c7-cd4c2b88948d" width="18%" />
  <img src="https://github.com/user-attachments/assets/0fd5372f-63c6-4856-b50c-f5d10cc92851" width="18%" />
  <img src="https://github.com/user-attachments/assets/4231a1a6-7804-4a6d-84f1-e93147cf28cf" width="18%" />
  <img src="https://github.com/user-attachments/assets/971ad2ee-c40e-4b7d-a480-b8f8c3206627" width="18%" />
</p>

---

## Features

- **Automatic drop mining** — watches eligible channels, claims drops the moment they unlock
- **OAuth device code login** — no password entry; just enter a short code on Twitch's website
- **Inventory tab** — browse all active campaigns and track your progress
- **Channels tab** — see which channels are being watched and their live status
- **Logs tab** — real-time log output straight from the mining engine
- **Foreground service** — keeps mining alive when the app is backgrounded or the screen is off
- **Wake lock** — prevents the CPU from sleeping mid-watch
- **Auto-claim** — configurable toggle in Settings
- **Portrait-only UI** — clean Material You design via KivyMD 2

---

## Requirements

| | |
|---|---|
| **Android** | 7.0 Nougat (API 24) or higher |
| **Architecture** | `arm64-v8a` (64-bit) |
| **Internet** | Required (Twitch API + WebSocket) |

> Tested on **Samsung Galaxy S23 FE** running Android 14 (One UI 6.1).

---

## Install

1. Go to the [**Releases**](https://github.com/C0ffiz/TwitchDropsMiner-Android/releases/latest) page.
2. Download the latest `TwitchDropsMiner-*.apk`.
3. On your Android device, enable **Install from unknown sources** (Settings → Apps → Special app access), then open the APK.
4. Launch **TwitchDropsMiner**, tap **Login with Twitch**, enter the code shown on [https://www.twitch.tv/activate](https://www.twitch.tv/activate).
5. Mining starts automatically once logged in.

---

## How it works

```
App start
  │
  ├─ Saved token found ──► validate token ──► start mining
  │
  └─ No token ──► device code login flow
                    │
                    ├─ Show 8-character code on screen
                    ├─ Poll Twitch every few seconds
                    └─ On activation ──► save token ──► start mining
                              │
                              ▼
                    Mining loop (runs in background)
                      • Fetch inventory (campaigns + drops)
                      • Find best eligible channel to watch
                      • Watch via WebSocket + HTTP heartbeat
                      • Claim drop when progress reaches 100%
                      • Repeat
```

---

## Build from source

**Requirements:** Linux (or WSL2 on Windows), Python 3.10+, Android SDK / NDK (handled automatically by the CI).

```bash
# Install dependencies
pip install "buildozer>=1.5.0" "cython==0.29.37"
pip install "python-for-android>=2023.9.0,<2025.0.0"

# Build debug APK
buildozer android debug
# → bin/twitchdropsminer-*.apk
```

Or trigger the GitHub Actions workflow manually:
**Actions → Build TwitchDropsMiner APK → Run workflow**

### Local dev / desktop testing

```bat
:: Windows
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

---

## Credits

- **Original project:** [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner)
- **Desktop reference:** [JourneyDocker/TwitchDropsMiner](https://github.com/JourneyDocker/TwitchDropsMiner)


