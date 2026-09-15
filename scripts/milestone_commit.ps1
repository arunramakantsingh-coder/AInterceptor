param([Parameter(Mandatory=$true)][string]$Milestone)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.git')) { Write-Host "BLOCKED: not a git repo"; exit 1 }
$branch = (& git rev-parse --abbrev-ref HEAD).Trim()
$remote = (& git remote get-url origin 2>$null)
if (-not $remote) { Write-Host "BLOCKED: no origin"; exit 1 }

New-Item -ItemType Directory -Force -Path '.evidence' | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$log = ".evidence\${Milestone}_$stamp.log"

& python scripts\validate_phase.py --milestone $Milestone 2>&1 | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) { Write-Host "RESULT: BLOCKED - validation"; exit 1 }

& git add -N . 2>$null | Out-Null
$diff = (& git diff --cached -U0) -join "`n"
$pats = @('sk-[A-Za-z0-9]{20,}','Bearer\s+[A-Za-z0-9._\-]{20,}',
  '-----BEGIN [A-Z ]+PRIVATE KEY-----','SECURE_1PSID')
foreach ($p in $pats) {
  if ($diff -match $p) { Write-Host "RESULT: BLOCKED - secret $p"; exit 1 }
}

foreach ($p in @('PROJECT','TEST','.ai','docs','scripts','backend','dashboard',
  'README.md','AGENTS.md','BLUEPRINT.md','KICKOFF_PROMPT.txt',
  'PROJECT_GOVERNANCE_STANDARD_v1.1.md','.gitignore')) {
  if (Test-Path $p) { & git add -- $p 2>$null }
}

$msg = "feat(${Milestone}): milestone checkpoint`n`nMilestone: $Milestone`nValidation: PASS`nEvidence: $log"
& git commit -m $msg
if ($LASTEXITCODE -ne 0) { Write-Host "RESULT: BLOCKED - commit"; exit 1 }

& git push origin $branch
if ($LASTEXITCODE -ne 0) { Write-Host "RESULT: BLOCKED - push"; exit 1 }

$sha = (& git rev-parse HEAD).Trim()
$ls = (& git ls-remote origin "refs/heads/$branch") -join "`n"
if ($ls -notmatch [regex]::Escape($sha)) {
  Write-Host "RESULT: BLOCKED - remote verify"; exit 1 }

Write-Host "============================================"
Write-Host "MILESTONE: $Milestone"
Write-Host "RESULT: PASS"
Write-Host "COMMIT: $sha"
Write-Host "BRANCH: $branch"
Write-Host "============================================"
