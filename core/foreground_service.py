"""
core/foreground_service.py — Android foreground service + persistent notification manager
==========================================================================================
This module runs on the **activity** (main) side.  It:

  • Starts / stops the p4a background Service (service/main.py) that calls
    startForeground() to keep our process at foreground priority.
  • Keeps a PARTIAL_WAKE_LOCK so the CPU stays on when the screen turns off.
  • Creates the same notification channel as the service and updates the
    persistent notification via NotificationManager.notify() with mining status.
  • Requests battery-optimisation exemption (Android ≥ M) so the OS doesn't
    throttle our background network work.

No IPC is needed: the service keeps the process alive; this module drives all
notification content directly from the activity's callbacks.

Usage in main.py
----------------
    from core.foreground_service import ForegroundServiceManager
    fg = ForegroundServiceManager()

    # After app is fully running (on_start):
    fg.setup()
    fg.request_battery_exemption()

    # On mining start / stop:
    fg.start_mining()
    fg.stop_mining()

    # From on_status / on_drop / on_progress callbacks:
    fg.set_status("Fetching channels…")
    fg.set_drop(game_name, current_mins, total_mins)

    # On app exit (on_stop):
    fg.shutdown()
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger("TwitchDrops")

# Shared constants — must match service/main.py
NOTIFICATION_ID: int = 7001
CHANNEL_ID: str = "tdm_fg_service"
CHANNEL_NAME: str = "TwitchDropsMiner"

_IS_ANDROID: bool = False
try:
    from jnius import autoclass as _autoclass  # noqa: F401  (availability check only)
    _IS_ANDROID = True
except ImportError:
    pass


class ForegroundServiceManager:
    """
    Activity-side manager for background keepalive and persistent notification.

    All public methods are safe to call on non-Android platforms (they become
    no-ops), so main.py doesn't need any platform guards.
    """

    def __init__(self) -> None:
        self._context = None           # android.content.Context (PythonActivity)
        self._nm = None                # android.app.NotificationManager
        self._pending_intent = None    # PendingIntent → re-open the app
        self._wake_lock = None         # PowerManager.WakeLock (PARTIAL)
        self._service = None           # android.AndroidService handle
        self._initialized: bool = False

        # Current notification state
        self._mining: bool = False
        self._status: str = "Idle"
        self._game: str = ""
        self._drop_name: str = ""
        self._current_mins: int = 0
        self._total_mins: int = 0

    # ── Setup ─────────────────────────────────────────────────────────────────

    def setup(self) -> None:
        """
        Initialise Android context, create notification channel, build the
        reusable PendingIntent.  Call once from App.on_start() after Kivy is
        fully running so that PythonActivity.mActivity is available.
        """
        if not _IS_ANDROID:
            return
        try:
            from jnius import autoclass, cast

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            self._context = PythonActivity.mActivity

            Context = autoclass("android.content.Context")
            Build_VERSION = autoclass("android.os.Build$VERSION")
            sdk_int: int = Build_VERSION.SDK_INT

            # ── Notification channel (API 26+) ───────────────────────────────
            if sdk_int >= 26:
                NotificationManager = autoclass("android.app.NotificationManager")
                self._nm = cast(
                    NotificationManager,
                    self._context.getSystemService(Context.NOTIFICATION_SERVICE),
                )
                NotificationChannel = autoclass("android.app.NotificationChannel")
                channel = NotificationChannel(
                    CHANNEL_ID,
                    CHANNEL_NAME,
                    NotificationManager.IMPORTANCE_LOW,   # silent
                )
                channel.setDescription("Mining status and drop progress")
                channel.setShowBadge(False)
                self._nm.createNotificationChannel(channel)
            else:
                # Android 7 (API 24-25) — no channel concept
                self._nm = cast(
                    autoclass("android.app.NotificationManager"),
                    self._context.getSystemService(Context.NOTIFICATION_SERVICE),
                )

            # ── Reusable PendingIntent (tap notification → open app) ─────────
            Intent = autoclass("android.content.Intent")
            PendingIntent = autoclass("android.app.PendingIntent")
            intent = Intent(self._context, PythonActivity)
            intent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
            pi_flags = (
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
                if sdk_int >= 23
                else PendingIntent.FLAG_UPDATE_CURRENT
            )
            self._pending_intent = PendingIntent.getActivity(
                self._context, 0, intent, pi_flags
            )

            self._initialized = True
            logger.info("[FG] setup complete (SDK %d)", sdk_int)
        except Exception:
            import traceback
            logger.warning("[FG] setup failed:\n%s", traceback.format_exc())

    # ── Battery optimisation exemption ────────────────────────────────────────

    def request_battery_exemption(self) -> None:
        """
        Open the system dialog asking the user to disable battery
        optimisation for our package.  Only shown if not already exempted.
        On Android < M (API 23) this is a no-op.
        """
        if not _IS_ANDROID or self._context is None:
            return
        try:
            from jnius import autoclass, cast

            Build_VERSION = autoclass("android.os.Build$VERSION")
            if Build_VERSION.SDK_INT < 23:
                return

            PowerManager = autoclass("android.os.PowerManager")
            pm = cast(
                PowerManager,
                self._context.getSystemService(self._context.POWER_SERVICE),
            )
            pkg: str = self._context.getPackageName()
            if pm.isIgnoringBatteryOptimizations(pkg):
                logger.info("[FG] battery optimisation already exempted")
                return

            Intent = autoclass("android.content.Intent")
            Settings = autoclass("android.provider.Settings")
            Uri = autoclass("android.net.Uri")
            intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            intent.setData(Uri.parse(f"package:{pkg}"))
            self._context.startActivity(intent)
            logger.info("[FG] battery optimisation exemption dialog opened")
        except Exception as exc:
            logger.warning("[FG] battery exemption request failed: %s", exc)

    # ── Wake lock ─────────────────────────────────────────────────────────────

    def _acquire_wake_lock(self) -> None:
        """Acquire PARTIAL_WAKE_LOCK — keeps CPU on while screen is off."""
        if not _IS_ANDROID:
            return
        try:
            from jnius import autoclass, cast

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            PowerManager = autoclass("android.os.PowerManager")
            pm = cast(
                PowerManager,
                PythonActivity.mActivity.getSystemService(
                    PythonActivity.mActivity.POWER_SERVICE
                ),
            )
            self._wake_lock = pm.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                "TwitchDropsMiner::MiningWakeLock",
            )
            if not self._wake_lock.isHeld():
                self._wake_lock.acquire()
                logger.info("[FG] PARTIAL_WAKE_LOCK acquired")
        except Exception as exc:
            logger.warning("[FG] acquire_wake_lock failed: %s", exc)

    def _release_wake_lock(self) -> None:
        """Release PARTIAL_WAKE_LOCK."""
        try:
            if self._wake_lock is not None and self._wake_lock.isHeld():
                self._wake_lock.release()
                logger.info("[FG] PARTIAL_WAKE_LOCK released")
        except Exception as exc:
            logger.warning("[FG] release_wake_lock failed: %s", exc)

    # ── Android service lifecycle ─────────────────────────────────────────────

    def _start_android_service(self) -> None:
        """Start service/main.py as an Android Foreground Service."""
        if not _IS_ANDROID:
            return
        try:
            from android import AndroidService  # type: ignore[import]
            self._service = AndroidService(
                "TwitchDropsMiner",
                "Mining drops in background",
            )
            self._service.start("start")
            logger.info("[FG] Android background service started")
        except Exception as exc:
            logger.warning("[FG] _start_android_service failed: %s", exc)

    def _stop_android_service(self) -> None:
        """Stop the Android Service."""
        if self._service is not None:
            try:
                self._service.stop()
                logger.info("[FG] Android background service stopped")
            except Exception as exc:
                logger.warning("[FG] _stop_android_service failed: %s", exc)
            self._service = None

    # ── Notification ─────────────────────────────────────────────────────────

    def _build_notification(self, title: str, text: str):
        """Return a new android.app.Notification or None on failure."""
        if not self._initialized or self._context is None:
            return None
        try:
            from jnius import autoclass

            Build_VERSION = autoclass("android.os.Build$VERSION")
            sdk_int: int = Build_VERSION.SDK_INT

            if sdk_int >= 26:
                Builder = autoclass("android.app.Notification$Builder")
                builder = Builder(self._context, CHANNEL_ID)
            else:
                Builder = autoclass("android.app.Notification$Builder")
                builder = Builder(self._context)

            Rdrawable = autoclass("android.R$drawable")
            builder.setSmallIcon(Rdrawable.ic_dialog_info)
            builder.setContentTitle(title)
            builder.setContentText(text)
            builder.setOngoing(True)          # user cannot swipe it away
            builder.setOnlyAlertOnce(True)    # no repeat sound/vibration on updates
            if sdk_int >= 21:
                builder.setVisibility(1)      # VISIBILITY_PUBLIC — show on lock screen

            if self._pending_intent is not None:
                builder.setContentIntent(self._pending_intent)

            return builder.build()
        except Exception as exc:
            logger.warning("[FG] _build_notification failed: %s", exc)
            return None

    def _post_notification(self, title: str, text: str) -> None:
        """Push an updated notification to the Android notification shade."""
        if not self._initialized or self._nm is None:
            return
        notif = self._build_notification(title, text)
        if notif is None:
            return
        try:
            self._nm.notify(NOTIFICATION_ID, notif)
        except Exception as exc:
            logger.warning("[FG] _post_notification failed: %s", exc)

    def _cancel_notification(self) -> None:
        if self._initialized and self._nm is not None:
            try:
                self._nm.cancel(NOTIFICATION_ID)
            except Exception as exc:
                logger.warning("[FG] _cancel_notification failed: %s", exc)

    # ── Notification text helpers ─────────────────────────────────────────────

    def _build_notification_text(self) -> tuple[str, str]:
        """Return (title, body) for the current mining state."""
        if not self._mining:
            return CHANNEL_NAME, "Idle"

        if self._game:
            title = f"Watching: {self._game}"
            if self._total_mins > 0:
                body = f"{self._current_mins}/{self._total_mins} min"
                if self._drop_name:
                    body = f"{self._drop_name} • {body}"
            else:
                body = self._status or "Watching…"
        else:
            title = CHANNEL_NAME
            body = self._status or "Fetching…"

        return title, body

    def _refresh_notification(self) -> None:
        """Re-post the notification with current state."""
        title, body = self._build_notification_text()
        self._post_notification(title, body)

    # ── Public API (called from main.py callbacks) ────────────────────────────

    def start_mining(self) -> None:
        """Call when the mining loop starts."""
        self._mining = True
        self._status = "Fetching…"
        self._game = ""
        self._drop_name = ""
        self._current_mins = 0
        self._total_mins = 0
        self._start_android_service()
        self._acquire_wake_lock()
        self._refresh_notification()

    def stop_mining(self) -> None:
        """Call when the mining loop stops (user pressed Stop or logout)."""
        self._mining = False
        self._game = ""
        self._drop_name = ""
        self._refresh_notification()
        self._release_wake_lock()
        # Delay service stop slightly so the "Idle" notification renders first.
        threading.Timer(1.5, self._stop_android_service).start()

    def set_status(self, status: str) -> None:
        """Update from the on_status callback."""
        self._status = status
        if not self._game:
            # Show status in notification only when we don't have a richer drop line
            self._refresh_notification()

    def set_channel(self, channel_name: str) -> None:
        """Update from the on_channel callback (not used in notification body, kept for future)."""
        pass  # channel name already visible on-screen; drop/game name is more informative

    def set_drop(
        self,
        game_name: str,
        drop_name: str,
        current_mins: int,
        total_mins: int,
    ) -> None:
        """Update from the on_drop callback (pass extracted fields from TimedDrop)."""
        self._game = game_name
        self._drop_name = drop_name
        self._current_mins = current_mins
        self._total_mins = total_mins
        self._refresh_notification()

    def update_progress(self, current: int, total: int) -> None:
        """Update from the on_progress callback."""
        self._current_mins = current
        self._total_mins = total
        if self._game:
            self._refresh_notification()

    def shutdown(self) -> None:
        """Call from App.on_stop() — release resources, cancel notification."""
        self._release_wake_lock()
        self._cancel_notification()
        self._stop_android_service()
