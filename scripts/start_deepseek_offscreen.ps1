# start and verify deepseek Chrome off-screen
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
if (!(Test-Path $chrome)) { $chrome = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" }
if (!(Test-Path $chrome)) { Write-Host "FAIL: chrome.exe not found"; exit 1 }

$profile = "C:\Projects\AInterceptor-M1.5\.ainterceptor\chrome-profile-deepseek"
New-Item -ItemType Directory -Force -Path $profile | Out-Null

$listening = (Get-NetTCPConnection -LocalPort 9223 -State Listen -ErrorAction SilentlyContinue) -ne $null
if ($listening) {
    Write-Host "Chrome on 9223 already running"
} else {
    Write-Host "Launching deepseek Chrome off-screen on 9223"
    Start-Process $chrome -ArgumentList @(
        "--remote-debugging-port=9223",
        "--user-data-dir=$profile",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-position=-32000,-32000",
        "--window-size=1280,900",
        "https://chat.deepseek.com/"
    )
    Start-Sleep -Seconds 4
}

# verify
$ok = (Get-NetTCPConnection -LocalPort 9223 -State Listen -ErrorAction SilentlyContinue) -ne $null
if ($ok) {
    Write-Host "PASS: CDP 9223 is alive"
    Write-Host ""
    Write-Host "If login is needed, move the window back on-screen temporarily:"
    Write-Host "  use the Windows taskbar preview -> right-click -> Move"
    Write-Host "Then back in AIRouter run:"
    Write-Host "  AIRouter(config-ai-provider-deepseek)# login"
} else {
    Write-Host "FAIL: 9223 did not come up"
}
