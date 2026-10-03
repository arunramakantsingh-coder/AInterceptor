# enable_cdp_portproxy.ps1
# Forward 0.0.0.0:9222-9225 -> 127.0.0.1:9222-9225 so Docker containers can reach the host's Chrome.

$needAdmin = -not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($needAdmin) {
    Write-Host "Requesting admin..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","$PSCommandPath"
    exit
}

Write-Host "==> Removing any existing rules for 9222-9225" -ForegroundColor Cyan
foreach ($port in 9222,9223,9224,9225) {
    netsh interface portproxy delete v4tov4 listenport=$port listenaddress=0.0.0.0 2>$null | Out-Null
}

Write-Host "==> Adding portproxy rules" -ForegroundColor Cyan
foreach ($port in 9222,9223,9224,9225) {
    netsh interface portproxy add v4tov4 listenport=$port listenaddress=0.0.0.0 connectport=$port connectaddress=127.0.0.1
}

Write-Host "`n==> Current portproxy table" -ForegroundColor Cyan
netsh interface portproxy show v4tov4

Write-Host "`n==> Firewall rule for 9222-9225" -ForegroundColor Cyan
$existing = Get-NetFirewallRule -DisplayName "AInterceptor CDP" -ErrorAction SilentlyContinue
if (-not $existing) {
    New-NetFirewallRule -DisplayName "AInterceptor CDP" `
        -Direction Inbound -Action Allow -Protocol TCP `
        -LocalPort 9222,9223,9224,9225 -Profile Any | Out-Null
    Write-Host "  added firewall rule"
} else {
    Write-Host "  firewall rule already exists"
}

Write-Host "`n==> Testing from this machine" -ForegroundColor Cyan
foreach ($port in 9222,9223,9224,9225) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/json/version" -TimeoutSec 3 -UseBasicParsing
        Write-Host "  port $port : OK" -ForegroundColor Green
    } catch {
        Write-Host "  port $port : NOT RESPONDING" -ForegroundColor Red
    }
}

Write-Host "`nDONE. Container should now reach Chrome at host.docker.internal:9222-9225." -ForegroundColor Green
Write-Host "Press Enter to close." -ForegroundColor Gray
Read-Host
