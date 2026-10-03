New-NetFirewallRule -DisplayName "AInterceptor CDP" `
  -Direction Inbound -Action Allow -Protocol TCP `
  -LocalPort 9222,9223,9224,9225 `
  -Profile Any
Write-Host "Firewall rule added." -ForegroundColor Green
Write-Host "Press Enter to close."
Read-Host
