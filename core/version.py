# Single source of truth for application version.
#
# Keep in sync with the `version` field in buildozer.spec when cutting a release.
# The string here is used at runtime (UI display, log headers, User-Agent, etc.).
# buildozer.spec controls the APK versionName/versionCode independently.

# PEP-440 version string
__version__: str = "1.0.0-android"

# Tuple form for programmatic comparisons: (major, minor, patch)
VERSION_TUPLE: tuple[int, int, int] = (1, 0, 0)

# Short human-readable alias — matches __version__
VERSION: str = __version__
