"""
CI helper: inject android.sdk_path and android.ndk_path into the [app]
section of buildozer.spec at build time.

Why this exists:
  Buildozer ignores ANDROID_HOME and downloads its own SDK when
  android.sdk_path is not present in buildozer.spec.  Hardcoding CI
  paths in the spec breaks local builds, so we inject them at runtime.
  A Python script avoids the bash-heredoc / YAML literal-block-scalar
  incompatibility (any line at column 0 inside a `run: |` block
  terminates the YAML block).

Usage:
  ANDROID_HOME=... ANDROID_NDK_HOME=... python3 ci/inject_sdk_paths.py
"""
import os
import re

spec_path = "buildozer.spec"
spec = open(spec_path).read()

# Remove any previously injected lines so this is idempotent.
spec = re.sub(r"^android\.sdk_path\s*=.*\n?", "", spec, flags=re.MULTILINE)
spec = re.sub(r"^android\.ndk_path\s*=.*\n?", "", spec, flags=re.MULTILINE)

sdk = os.environ["ANDROID_HOME"]
ndk = os.environ["ANDROID_NDK_HOME"]

# Insert before [buildozer] so the keys land in the [app] section.
spec = spec.replace(
    "[buildozer]",
    f"android.sdk_path = {sdk}\nandroid.ndk_path = {ndk}\n\n[buildozer]",
)


# Inject p4a.source_dir if P4A_SOURCE_DIR env var is set (CI only).
# When set, buildozer uses that directory as the p4a source instead of
# cloning from p4a.branch, so we can use a pre-patched local clone.
p4a_source = os.environ.get("P4A_SOURCE_DIR", "").strip()
if p4a_source:
    spec = re.sub(r"^p4a\.branch\s*=.*\n?", "", spec, flags=re.MULTILINE)
    spec = re.sub(r"^p4a\.source_dir\s*=.*\n?", "", spec, flags=re.MULTILINE)
    spec = spec.replace(
        "[buildozer]",
        f"p4a.source_dir = {p4a_source}\n\n[buildozer]",
    )

open(spec_path, "w").write(spec)
print("--- injected buildozer.spec ---")
print(open(spec_path).read())
