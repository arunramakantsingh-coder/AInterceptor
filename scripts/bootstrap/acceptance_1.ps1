$base = "http://localhost:8000"
Write-Host "==> 1. Signup" -ForegroundColor Cyan
$body = '{"email":"me@example.com","password":"changeme123"}'
try {
  $r = Invoke-RestMethod -Uri "$base/api/auth/signup" -Method POST -ContentType "application/json" -Body $body
} catch {
  Write-Host "   signup failed (may already exist), trying login" -ForegroundColor Yellow
  $r = Invoke-RestMethod -Uri "$base/api/auth/login" -Method POST -ContentType "application/json" -Body $body
}
$token = $r.token
Write-Host "   user_id: $($r.user_id)"
Write-Host "   email  : $($r.email)"

Write-Host "`n==> 2. Create API key" -ForegroundColor Cyan
$headers = @{ Authorization = "Bearer $token" }
$r = Invoke-RestMethod -Uri "$base/api/keys" -Method POST -Headers $headers -ContentType "application/json" -Body '{"name":"CareerOS"}'
$apiKey = $r.key
Write-Host "   prefix : $($r.prefix)"
Write-Host "   key    : $apiKey" -ForegroundColor Yellow

Write-Host "`n==> 3. Sessions" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri "$base/api/sessions" -Method GET -Headers $headers
Write-Host "   count: $($r.Count)"

Set-Content -Path .\.env.test -Value "TOKEN=$token`nAPI_KEY=$apiKey"
Write-Host "`nSaved to .env.test" -ForegroundColor Green
