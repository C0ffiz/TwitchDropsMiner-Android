[app]
title = TwitchDropsMiner
package.name = twitchdropsminer
package.domain = io.github.c0ffiz

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt

version = 0.1
requirements = python3,kivy==2.3.0,https://github.com/kivymd/KivyMD/archive/master.zip,materialyoucolor,pillow,pyjnius,certifi,android,plyer,aiohttp,yarl,aiosignal,frozenlist,multidict,attrs,propcache,idna,aiohappyeyeballs,typing-extensions,async-timeout,charset-normalizer==2.3.0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,FOREGROUND_SERVICE,POST_NOTIFICATIONS,WAKE_LOCK,RECEIVE_BOOT_COMPLETED

android.api = 34
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.archs = arm64-v8a

# android.sdk_path and android.ndk_path intentionally omitted — CI sets ANDROID_HOME env var
# p4a is pinned via pip install in the workflow; branch=master is the fallback
p4a.branch = master

fullscreen = 0

source.exclude_dirs = venv
source.exclude_patterns = venv/*,tests/*,docs/*,README.md,LICENSE,*.pyc,*.pyo,__pycache__/*,*.log,*.zip,*.tar.gz,*.tar.bz2,*.rar,*.7z,*.dmg,*.exe,*.msi,*.deb,*.rpm,*.pkg,*.apk,*.ipa,*.dSYM/*,*.so,*.dylib,*.dll,*.lib,*.a,*.o,*.obj,*.class,*.jar,*.war,*.ear,*.sar,*.par,*.rar,*.tar,*.gz,*.bz2,*.xz,*.lzma,*.lz,*.lzo,*.lz4,*.snappy,*.zst,*.zstd,*.br,*.bz2,*.gz,*.lzma,*.xz,*.z,*.Z,*.zip,*.7z,*.rar,*.tar.gz,*.tar.bz2,*.tar.xz,*.tar.lzma,*.tar.lz,*.tar.lz4,*.tar.snappy,*.tar.zst,*.tar.zstd,*.tar.br,*.tar.bz2,*.tar.gz,*.tar.lzma,*.tar.lz,*.tar.lz4,*.tar.snappy,*.tar.zst,*.tar.zstd,*.tar.br,*.tar.bz2,*.tar.gz,*.tar.lzma,*.tar.lz,*.tar.lz4,*.tar.snappy,*.tar.zst,*.tar.zstd,*.tar.br

[buildozer]
log_level = 2
warn_on_root = 1
