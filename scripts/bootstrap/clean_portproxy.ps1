$script = @"
-noprofile -command "& {
  foreach (`$p in 9222,9223,9224,9225) {
    netsh interface portproxy delete v4tov4 listenport=`$p listenaddress=0.0.0.0
  }
  netsh interface portproxy show v4tov4
  Read-Host 'Press Enter to close'
}"
"@
$script | Out-File -Encoding ascii -Path $env:TEMP\clean_portproxy.ps1
Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "$env:TEMP\clean_portproxy.ps1"
