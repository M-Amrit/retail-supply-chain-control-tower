# Pre-demo helper for Windows PowerShell. UNTESTED (written without a PowerShell available); it only chains commands that
# were already run by hand during the project. If it misbehaves, use the manual checklist in docs\DEMO_SCRIPT.md.
#
# Run from anywhere:   powershell -ExecutionPolicy Bypass -File scripts\demo_prep.ps1
# Optional:            add -InsertTestAlert to queue one demo alert, so the next hourly run posts to Slack.
param([switch]$InsertTestAlert)

Set-Location (Split-Path -Parent $PSScriptRoot)      # project root

function Wait-Http([string]$Name, [string]$Url, [int]$MaxSeconds = 300) {
    $start = Get-Date
    while (((Get-Date) - $start).TotalSeconds -lt $MaxSeconds) {
        $code = curl.exe -s -o NUL -w "%{http_code}" $Url
        if ($code -eq "200") { Write-Host "[ok]  $Name is up" -ForegroundColor Green; return $true }
        Write-Host "      waiting for $Name ..."
        Start-Sleep -Seconds 10
    }
    Write-Host "[!!]  $Name did not answer 200 within $MaxSeconds s ($Url)" -ForegroundColor Red
    return $false
}

Write-Host "`n== 1. Docker ==" -ForegroundColor Cyan
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker Desktop is not running. Open it, wait for 'Engine running', then run this script again." -ForegroundColor Red
    exit 1
}
docker compose up -d

Write-Host "`n== 2. Waiting for services (up to 5 minutes each) ==" -ForegroundColor Cyan
$superset = Wait-Http "Superset" "http://localhost:8088/health"
$airflow  = Wait-Http "Airflow"  "http://localhost:8080/health"
$whatif   = Wait-Http "What-If"  "http://localhost:8501"

Write-Host "`n== 3. Airflow login ==" -ForegroundColor Cyan
Write-Host "Username: admin"
Write-Host -NoNewline "Password: "
docker compose exec airflow cat /opt/airflow/standalone_admin_password.txt
Write-Host "`nUse a PRIVATE window for Airflow (a normal one may show 'CSRF session token is missing')."
Write-Host "Then switch the DAG control_tower_hourly_pipeline ON and trigger it once."

if ($InsertTestAlert) {
    Write-Host "`n== 4. Queueing a demo alert ==" -ForegroundColor Cyan
    docker compose exec postgres psql -U tower -d control_tower -c "insert into alerts_log (alert_type,severity,entity_type,entity_id,message,dedup_key) values ('TEST','high','demo','demo','Demo alert: Supplier-01 delay test', 'TEST:' || now());"
}

Write-Host "`n== 5. Opening tabs ==" -ForegroundColor Cyan
Start-Process "http://localhost:8088/superset/dashboard/1/"     # Superset (admin / admin)
Start-Process "http://localhost:8501"                           # What-If
try { Start-Process "msedge" "-inprivate http://localhost:8080" } catch { Write-Host "Open http://localhost:8080 in a private window yourself." }

Write-Host "`nStill to do by hand: open Slack #alerts, set What-If to Supplier-01 at 14 days, close notifications." -ForegroundColor Yellow
if (-not ($superset -and $airflow -and $whatif)) { Write-Host "At least one service did not come up; see the [!!] lines above." -ForegroundColor Red }
