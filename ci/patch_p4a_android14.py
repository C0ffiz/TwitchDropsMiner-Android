"""
ci/patch_p4a_android14.py
=========================
Patch python-for-android for Android 14 (targetSdk=34) foreground service
compatibility. Two patches are applied:

  1. AndroidManifest.tmpl.xml — add android:foregroundServiceType="dataSync"
     to the PythonService <service> element so Android 14 accepts the service.

  2. PythonService.java — change the Java-level startForeground() call to use
     the 3-argument form (with FOREGROUND_SERVICE_TYPE_DATA_SYNC) on API >= 29.
     Without this Android 14 throws MissingForegroundServiceTypeException
     before our Python service/main.py even gets a chance to run.

Usage:
    python3 ci/patch_p4a_android14.py <p4a_root_dir>
"""
import pathlib
import re
import sys

P4A_ROOT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(".")


def patch_manifest_template() -> None:
    """Add android:foregroundServiceType="dataSync" to the service element."""
    templates = list(P4A_ROOT.rglob("AndroidManifest.tmpl.xml"))
    if not templates:
        print("[patch] WARNING: AndroidManifest.tmpl.xml not found", file=sys.stderr)
        return
    for tmpl in templates:
        txt = tmpl.read_text()
        if "foregroundServiceType" in txt:
            print(f"[patch] manifest template already patched: {tmpl}")
            continue
        # Insert the attribute directly after android:name="org.kivy.android.PythonService"
        patched = txt.replace(
            'android:name="org.kivy.android.PythonService"',
            'android:name="org.kivy.android.PythonService"\n'
            '           android:foregroundServiceType="dataSync"',
            1,
        )
        if patched == txt:
            print(f"[patch] WARNING: PythonService pattern not found in {tmpl}", file=sys.stderr)
            continue
        tmpl.write_text(patched)
        print(f"[patch] manifest template patched: {tmpl}")


def patch_python_service_java() -> None:
    """
    Wrap the Java startForeground() call so Android 14 gets the 3-arg form.

    Searches for PythonService.java files and replaces:
        startForeground(NOTIFY_FOREGROUND, notification);
    with an API-guarded block that uses the 3-arg form on API 29+.
    The exact identifier names vary across p4a versions, so we use a
    pattern that is tolerant of minor differences.
    """
    java_files = list(P4A_ROOT.rglob("PythonService.java"))
    if not java_files:
        print("[patch] WARNING: PythonService.java not found", file=sys.stderr)
        return
    for jf in java_files:
        txt = jf.read_text()
        if "FOREGROUND_SERVICE_TYPE_DATA_SYNC" in txt:
            print(f"[patch] PythonService.java already patched: {jf}")
            continue

        # Match startForeground calls with exactly 2 arguments (not 3).
        # The call is typically: startForeground(NOTIFY_FOREGROUND, notification);
        # Regex captures the 2 args so we can wrap them.
        pattern = re.compile(
            r'([ \t]+)(startForeground\s*\((\s*[A-Za-z_][A-Za-z_0-9]*\s*,\s*[A-Za-z_][A-Za-z_0-9]*\s*)\);)',
            re.MULTILINE,
        )
        matches = list(pattern.finditer(txt))
        if not matches:
            print(f"[patch] WARNING: startForeground 2-arg pattern not found in {jf}", file=sys.stderr)
            continue

        for m in reversed(matches):  # reverse so offsets stay valid
            indent = m.group(1)
            args = m.group(3)  # e.g. "NOTIFY_FOREGROUND, notification"
            replacement = (
                f"{indent}if (android.os.Build.VERSION.SDK_INT >= 29) {{\n"
                f"{indent}    startForeground({args},\n"
                f"{indent}        android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);\n"
                f"{indent}}} else {{\n"
                f"{indent}    startForeground({args});\n"
                f"{indent}}}"
            )
            txt = txt[: m.start()] + replacement + txt[m.end():]

        jf.write_text(txt)
        print(f"[patch] PythonService.java patched: {jf}")


if __name__ == "__main__":
    patch_manifest_template()
    patch_python_service_java()
    print("[patch] Done.")
