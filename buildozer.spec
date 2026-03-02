[app]
title = TwitchDropsMiner
package.name = twitchdropsminer
package.domain = org.example

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt

version = 0.1
requirements = python3,kivy,kivymd,pillow,pyjnius,certifi,android,plyer,aiohttp,yarl,aiosignal,frozenlist,multidict,apprise

android.permissions = INTERNET,ACCESS_NETWORK_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,FOREGROUND_SERVICE,POST_NOTIFICATIONS,WAKE_LOCK,RECEIVE_BOOT_COMPLETED

android.api = 33
android.minapi = 21
android.ndk = 25b
android.ndk_api = 21
android.archs = armeabi-v7a

android.sdk_path = /home/runner/android-sdk
android.ndk_path = /home/runner/android-sdk/ndk/25.1.8937393

p4a.branch = master

fullscreen = 0

source.exclude_patterns = venv/*,tests/*,docs/*,README.md,LICENSE,*.pyc,*.pyo,__pycache__/*,*.log,*.zip,*.tar.gz,*.tar.bz2,*.rar,*.7z,*.dmg,*.exe,*.msi,*.deb,*.rpm,*.pkg,*.apk,*.ipa,*.dSYM/*,*.so,*.dylib,*.dll,*.lib,*.a,*.o,*.obj,*.class,*.jar,*.war,*.ear,*.sar,*.par,*.rar,*.tar,*.gz,*.bz2,*.xz,*.lzma,*.lz,*.lzo,*.lz4,*.snappy,*.zst,*.zstd,*.br,*.bz2,*.gz,*.lzma,*.xz,*.z,*.Z,*.zip,*.7z,*.rar,*.tar.gz,*.tar.bz2,*.tar.xz,*.tar.lzma,*.tar.lz,*.tar.lz4,*.tar.snappy,*.tar.zst,*.tar.zstd,*.tar.br,*.tar.bz2,*.tar.gz,*.tar.lzma,*.tar.lz,*.tar.lz4,*.tar.snappy,*.tar.zst,*.tar.zstd,*.tar.br,*.tar.bz2,*.tar.gz,*.tar.lzma,*.tar.lz,*.tar.lz4,*.tar.snappy,*.tar.zst,*.tar.zstd,*.tar.br

[buildozer]
log_level = 2
warn_on_root = 1
