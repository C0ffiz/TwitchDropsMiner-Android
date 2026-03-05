"""
TwitchDropsMiner — Android background service
==============================================
This file is the entry-point for the p4a-generated Android Service
(see ``services = TDMService:service/main.py:foreground`` in buildozer.spec).

Its sole job is to:
  1. Create the notification channel.
  2. Call startForeground() with a branded notification.
  3. Loop forever so the Service object stays alive, which keeps the
     owning process marked as a foreground-service process by Android.
     The activity thread (mining loop) lives in the same process and
     therefore also benefits from elevated OOM priority.

Notification content is updated from the activity side via
NotificationManager.notify(NOTIFICATION_ID, new_notification).
No IPC is needed because both sides share the same NotificationManager.
"""

import time
import logging

logger = logging.getLogger("TwitchDropsMiner.service")

# Must match core/foreground_service.py
NOTIFICATION_ID = 7001
CHANNEL_ID = "tdm_fg_service"
CHANNEL_NAME = "TwitchDropsMiner"


def _start_foreground() -> None:
    """
    Build a persistent foreground notification and call startForeground().

    Called once at service startup.  On Android 14 (API 34) this must
    happen within 5 seconds of onStartCommand(); running it synchronously
    at module import time satisfies that constraint.
    """
    try:
        from jnius import autoclass, cast  # type: ignore[import]

        PythonService = autoclass("org.kivy.android.PythonService")
        svc = PythonService.mService

        Context = autoclass("android.content.Context")
        Build = autoclass("android.os.Build")
        sdk_int = Build.VERSION.SDK_INT

        # ── Notification channel (API 26 / Android 8+) ──────────────────────
        if sdk_int >= 26:
            NotificationManager = autoclass("android.app.NotificationManager")
            nm = cast(
                NotificationManager,
                svc.getSystemService(Context.NOTIFICATION_SERVICE),
            )
            NotificationChannel = autoclass("android.app.NotificationChannel")
            channel = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_LOW,  # silent — no sound/vibration
            )
            channel.setDescription("Mining status and drop progress")
            channel.setShowBadge(False)
            nm.createNotificationChannel(channel)
            Builder = autoclass("android.app.Notification$Builder")
            builder = Builder(svc, CHANNEL_ID)
        else:
            # Android 7 (API 24-25) — channels don't exist
            Builder = autoclass("android.app.Notification$Builder")
            builder = Builder(svc)

        # ── Build initial notification ───────────────────────────────────────
        Rdrawable = autoclass("android.R$drawable")
        # ic_dialog_info is present on all API levels; we override it in activity
        # once a proper mining state is known.
        builder.setSmallIcon(Rdrawable.ic_dialog_info)
        builder.setContentTitle("TwitchDropsMiner")
        builder.setContentText("Running in background…")
        builder.setOngoing(True)
        builder.setOnlyAlertOnce(True)

        # Tap notification → bring app to foreground
        Intent = autoclass("android.content.Intent")
        PendingIntent = autoclass("android.app.PendingIntent")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        intent = Intent(svc, PythonActivity)
        intent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
        pi_flags = (
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
            if sdk_int >= 23
            else PendingIntent.FLAG_UPDATE_CURRENT
        )
        pi = PendingIntent.getActivity(svc, 0, intent, pi_flags)
        builder.setContentIntent(pi)

        notification = builder.build()

        # ── Foreground service ───────────────────────────────────────────────
        # On Android 14 the FOREGROUND_SERVICE_DATA_SYNC permission and the
        # android:foregroundServiceType="dataSync" manifest attribute (added by
        # p4a when ":foreground" is in buildozer.spec) are required.
        if sdk_int >= 29:
            # ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC = 0x00000004
            ServiceInfo = autoclass("android.content.pm.ServiceInfo")
            svc.startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
            )
        else:
            svc.startForeground(NOTIFICATION_ID, notification)

        logger.info("[Service] startForeground() called, notification ID=%d", NOTIFICATION_ID)

    except Exception:
        import traceback
        logger.error("[Service] startForeground() failed:\n%s", traceback.format_exc())


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("[Service] background service starting (PID=%s)", __import__("os").getpid())
    _start_foreground()

    # Keep the service alive indefinitely.
    # The activity calls android.AndroidService.stop() to terminate us.
    while True:
        time.sleep(30)
