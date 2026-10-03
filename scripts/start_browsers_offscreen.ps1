# start_browsers_offscreen.ps1
# Launches Chrome with the debugging port and the window pushed off-screen
# so the user never sees it. Attach via CDP and everything works headless.

param(
  [string]$Provider = "deepseek",   # deepseek | claude | chatgpt | gemini
  [int]$Port = 0
)

$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
if (!(Test-Path $chrome)) { $chrome = 'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe' }
if (!(Test-Path $chrome)) { Write-Error "chrome.exe not found"; exit 1 }

$map = @{
  deepseek = @{ Port = 9223; Url = "https://chat.deepseek.com/"; Profile = "chrome-profile-deepseek" }
  claude   = @{ Port = 9222; Url = "https://claude.ai/";        Profile = "chrome-profile-claude" }
  chatgpt  = @{ Port = 9224; Url = "https://chatgpt.com/";      Profile = "chrome-profile-chatgpt" }
  gemini   = @{ Port = 9225; Url = "https://gemini.google.com/";Profile = "chrome-profile-gemini" }
}
if (-not $map.ContainsKey($Provider)) { Write-Error "unknown provider $Provider"; exit 1 }
if ($Port -eq 0) { $Port = $map[$Provider].Port }

$profileDir = Join-Path $env:USERPROFILE "..\..\Projects\AInterceptor-M1.5\.ainterceptor\$($map[$Provider].Profile)"
$profileDir = [System.IO.Path]::GetFullPath("C:\Projects\AInterceptor-M1.5\.ainterceptor\$($map[$Provider].Profile)")
New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

Start-Process $chrome -ArgumentList @(
  "--remote-debugging-port=$Port",
  "--user-data-dir=$profileDir",
  "--no-first-run",
  "--no-default-browser-check",
  "--window-position=-32000,-32000",   # off-screen: invisible to the user
  "--window-size=1280,900",
  $map[$Provider].Url
)

Write-Host "launched $Provider Chrome off-screen on port $Port"
Write-Host "attach via CDP: http://127.0.0.1:$Port"
