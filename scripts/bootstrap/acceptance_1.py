$base = "http://localhost:8000"

Write-Host "==> 1. Signup" -ForegroundColor Cyan
$body = '{"email":"me@example.com","password":"changeme123"}'
$r = Invoke-RestMethod -Uri "$base/api/auth/signup" -Method POST `
       -ContentType "application/json" -Body $body
$token = $r.token
Write-Host "   user_id : $($r.user_id)"
Write-Host "   email   : $($r.email)"
Write-Host "   token   : $($token.Substring(0,32))..." -ForegroundColor DarkGray

Write-Host "`n==> 2. Create API key" -ForegroundColor Cyan
$headers = @{ Authorization = "Bearer $token" }
$r = Invoke-RestMethod -Uri "$base/api/keys" -Method POST `
       -Headers $headers -ContentType "application/json" `
       -Body '{"name":"CareerOS"}'
Write-Host "   key_id  : $($r.id)"
Write-Host "   prefix  : $($r.prefix)"
Write-Host "   key     : $($r.key)" -ForegroundColor Yellow
$apiKey = $r.key

Write-Host "`n==> 3. List keys" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri "$base/api/keys" -Method GET -Headers $headers
$r | ForEach-Object { Write-Host "   $($_.prefix)  $($_.name)" }

Write-Host "`n==> 4. List sessions (expect empty)" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri "$base/api/sessions" -Method GET -Headers $headers
Write-Host "   count: $($r.Count)"

# Save credentials to disk for next steps
"TOKEN=$token" | Out-File -Encoding ascii .\.env.test
"API_KEY=$apiKey" | Out-File -Encoding ascii -Append .\.env.test
Write-Host "`n==> Saved creds to .env.test" -ForegroundColor Green
Write-Host "   token   : $($token.Substring(0,24))..." -ForegroundColor DarkGray
Write-Host "   api_key : $apiKey" -ForegroundColor Yellow
Write-Host "`nNext: install agent, upload session for one provider."
