#Requires -Version 5.1
# deploy.ps1 — Download latest APK from GitHub Actions and install via ADB
# Usage: .\deploy.ps1
# Requirements: adb (Android SDK platform-tools), gh (GitHub CLI, authenticated)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$DEVICE_IP      = '192.168.68.53:5555'
$REPO           = 'C0ffiz/TwitchDropsMiner-Android'
$ARTIFACT_NAME  = 'apk'
$PACKAGE        = 'io.github.c0ffiz.twitchdropsminer'
$TEMP_DIR       = Join-Path $env:TEMP 'tdm-android-deploy'

function Write-Step([string]$msg) {
    Write-Host "`n==> $msg" -ForegroundColor Cyan
}
function Write-OK([string]$msg) {
    Write-Host "    [OK] $msg" -ForegroundColor Green
}
function Write-Fail([string]$msg) {
    Write-Host "    [FAIL] $msg" -ForegroundColor Red
}

# ── 1. ADB connect ────────────────────────────────────────────────────────────
Write-Step "Connecting ADB to $DEVICE_IP"
$connectOut = adb connect $DEVICE_IP 2>&1
Write-Host "    $connectOut"
if ($connectOut -notmatch 'connected') {
    Write-Fail "ADB could not connect to $DEVICE_IP. Is the device on the same WiFi network and ADB over WiFi enabled?"
    exit 1
}
Write-OK "ADB connected"

# Verify the device is authorised
$devicesStr = (adb devices 2>&1) -join "`n"
if ($devicesStr -notmatch "$([regex]::Escape($DEVICE_IP))\s+device") {
    Write-Fail "Device $DEVICE_IP is listed but not authorised (check for 'unauthorized' state). Accept the RSA fingerprint dialog on the device."
    exit 1
}
Write-OK "Device authorised"

# ── 2. Download latest APK artifact ──────────────────────────────────────────
Write-Step "Downloading latest '$ARTIFACT_NAME' artifact from $REPO"

# Ensure temp directory is clean
if (Test-Path $TEMP_DIR) { Remove-Item $TEMP_DIR -Recurse -Force }
New-Item -ItemType Directory -Path $TEMP_DIR | Out-Null

try {
    # gh run download picks the most recent successful run that produced the artifact
    $ghOut = gh run download `
        --repo $REPO `
        --name $ARTIFACT_NAME `
        --dir $TEMP_DIR 2>&1
    if ($ghOut) { Write-Host ($ghOut -join "`n") }
} catch {
    Write-Fail "gh run download failed: $_"
    Write-Host "    Make sure 'gh' is installed and authenticated (run: gh auth login)"
    exit 1
}
if ($LASTEXITCODE -ne 0) {
    Write-Fail "gh run download exited with code $LASTEXITCODE — no successful artifact found, or not authenticated."
    Write-Host "    Run: gh auth login   and confirm the latest Actions workflow run succeeded."
    exit 1
}

# Find the APK
$apkFiles = Get-ChildItem -Path $TEMP_DIR -Filter '*.apk' -Recurse
if ($apkFiles.Count -eq 0) {
    Write-Fail "No .apk file found in the downloaded artifact. Check the artifact name ('$ARTIFACT_NAME') and confirm the latest workflow run succeeded."
    exit 1
}
if ($apkFiles.Count -gt 1) {
    Write-Host "    Multiple APKs found — using the first one:" -ForegroundColor Yellow
    $apkFiles | ForEach-Object { Write-Host "      $_" }
}
$apkPath = $apkFiles[0].FullName
Write-OK "APK found: $apkPath"

# ── 3. Uninstall previous version (removes app + all data for a clean install) ─
Write-Step "Uninstalling previous version of $PACKAGE (if installed)"
$uninstallOut = adb uninstall $PACKAGE 2>&1
Write-Host "    $uninstallOut"
if ($uninstallOut -match 'Success') {
    Write-OK "Previous version uninstalled and all app data removed"
} elseif ($uninstallOut -match 'not installed|Unknown package') {
    Write-Host "    (App was not previously installed — skipping)" -ForegroundColor Yellow
} else {
    Write-Host "    Warning: unexpected uninstall output (continuing anyway)" -ForegroundColor Yellow
}

# ── 4. Install APK ───────────────────────────────────────────────────────────
Write-Step "Installing APK on device ($PACKAGE)"
$installOut = adb install $apkPath 2>&1
Write-Host "    $installOut"
if ($installOut -match 'Success') {
    Write-OK "Install succeeded"
} else {
    Write-Fail "adb install reported a failure. See output above."
    exit 1
}

# ── 5. Launch the app ────────────────────────────────────────────────────────
Write-Step "Launching $PACKAGE"
adb shell am start -n "$PACKAGE/org.kivy.android.PythonActivity" | Out-Null
Write-OK "App launched"

Write-Host "`nDeploy complete. App should be running on the device." -ForegroundColor Green
