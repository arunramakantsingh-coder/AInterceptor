import subprocess, pathlib
BIN = "C:\\Projects\\AInterceptor-M1.5\\bin"
ps = (
    f'$p=[Environment]::GetEnvironmentVariable("Path","User"); '
    f'if ($p -notlike "*{BIN}*") {{ '
    f'  [Environment]::SetEnvironmentVariable("Path", "$p;{BIN}", "User"); '
    f'  Write-Host "added" }} else {{ Write-Host "already present" }}'
)
r = subprocess.run(["powershell","-NoProfile","-Command", ps],
                   capture_output=True, text=True, shell=True)
print(r.stdout.strip() or r.stderr.strip())
