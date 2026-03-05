# TwitchDropsMiner Android

> **⚠️ Under construction** — This project is not stable or feature-complete.
> Expect rough edges and breaking changes.

An Android port of TwitchDropsMiner built with Python + Kivy, packaged via Buildozer.

---

## Quick start (Desktop — development / testing)

**Windows**

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

---

## Build for Android (Buildozer)

Buildozer requires a Linux environment. On Windows, use WSL2 or a Linux VM.

```bash
pip install buildozer
buildozer android debug
```

The compiled APK will be in the `bin/` directory.

---

## GitHub Actions (CI)

The workflow at `.github/workflows/build-android.yml` automatically builds a
debug APK on every `push`, `pull_request`, and can be triggered manually via
`workflow_dispatch`.

- Runs on **Ubuntu** using Buildozer and the Android SDK.
- Triggered manually via **Actions → Build TwitchDropsMiner APK → Run workflow**.
- To download the built APK: open the **Actions** tab → select a run →
  **Artifacts → `apk`**.

---

## Credits

- **Original project:** [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner)
- **Desktop reference:** [JourneyDocker/TwitchDropsMiner](https://github.com/JourneyDocker/TwitchDropsMiner)


