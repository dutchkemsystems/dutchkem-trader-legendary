# ============================================================
#  DUTCHKEM TRADER - AUTO STARTUP SCRIPT
#  Starts: MT5 Terminal + FastAPI Server + Trading Engine + Frontend
#  Register with Task Scheduler to run at user logon
# ============================================================

$ErrorActionPreference = "Continue"
$ProjectRoot = "C:\DUTCHKEM-TRADER-LEGENDARY-INTELLIGENCE-EDITION"
$BackendDir  = "$ProjectRoot\backend"
$LogFile     = "$ProjectRoot\startup_log.txt"
$PidDir      = "$ProjectRoot\pids"

# Create PID directory
if (-not (Test-Path $PidDir)) { New-Item -ItemType Directory -Path $PidDir -Force | Out-Null }

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $msg" | Out-File -FilePath $LogFile -Append -Encoding utf8
    Write-Output $msg
}

function Kill-ByPidFile($name) {
    $pidFile = "$PidDir\$name.pid"
    if (Test-Path $pidFile) {
        $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue
        if ($oldPid) {
            $proc = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
            if ($proc) {
                Log "Stopping old $name (PID $oldPid)..."
                Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
            }
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

function Save-Pid($name, $proc) {
    if ($proc -and $proc.Id) {
        "$($proc.Id)" | Out-File -FilePath "$PidDir\$name.pid" -Encoding ascii -Force
        Log "  $name PID: $($proc.Id)"
    }
}

function Wait-ForPort($port, $timeout = 60) {
    $elapsed = 0
    while ($elapsed -lt $timeout) {
        $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($conn) { return $true }
        Start-Sleep -Seconds 2
        $elapsed += 2
    }
    return $false
}

Log "=========================================="
Log "  DUTCHKEM TRADER - AUTO STARTUP"
Log "=========================================="

# ─────────────────────────────────────────────
# STEP 1: Kill old instances
# ─────────────────────────────────────────────
Log ""
Log "STEP 1: Cleaning old processes..."
Kill-ByPidFile "fastapi"
Kill-ByPidFile "engine"
Kill-ByPidFile "frontend"

# ─────────────────────────────────────────────
# STEP 2: Start MT5 Terminal (if not running)
# ─────────────────────────────────────────────
Log ""
Log "STEP 2: Checking MT5 Terminal..."
$mt5Path = "C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
$mt5Running = Get-Process -Name "terminal64" -ErrorAction SilentlyContinue
if ($mt5Running) {
    Log "  MT5 already running (PID: $($mt5Running[0].Id))"
} else {
    if (Test-Path $mt5Path) {
        Log "  Starting MT5 Terminal..."
        $mt5Proc = Start-Process -FilePath $mt5Path -WindowStyle Minimized -PassThru
        Log "  MT5 started (PID: $($mt5Proc.Id))"
        Log "  Waiting 15s for MT5 to initialize..."
        Start-Sleep -Seconds 15
    } else {
        Log "  WARNING: MT5 not found at $mt5Path"
    }
}

# ─────────────────────────────────────────────
# STEP 3: Start FastAPI Server
# ─────────────────────────────────────────────
Log ""
Log "STEP 3: Starting FastAPI Server..."

# Check if port 8000 is already in use
$portCheck = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($portCheck) {
    Log "  Port 8000 already in use - server likely running"
} else {
    $env:DJANGO_SETTINGS_MODULE = "config.settings"
    $fastapiProc = Start-Process -FilePath "python" `
        -ArgumentList "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000" `
        -WorkingDirectory $BackendDir `
        -WindowStyle Minimized `
        -RedirectStandardOutput "$ProjectRoot\fastapi_output.log" `
        -RedirectStandardError "$ProjectRoot\fastapi_error.log" `
        -PassThru
    Save-Pid "fastapi" $fastapiProc
    Log "  FastAPI server starting..."
    Start-Sleep -Seconds 5
}

# Wait for server to be ready
Log "  Waiting for FastAPI server..."
if (Wait-ForPort -port 8000 -timeout 30) {
    Log "  FastAPI server READY on port 8000"
} else {
    Log "  WARNING: FastAPI server may not be ready"
}

# ─────────────────────────────────────────────
# STEP 4: Start Frontend (Next.js)
# ─────────────────────────────────────────────
Log ""
Log "STEP 4: Starting Frontend..."

$FrontendDir = "$ProjectRoot\frontend"
$fePortCheck = Get-NetTCPConnection -LocalPort 8888 -State Listen -ErrorAction SilentlyContinue
if ($fePortCheck) {
    Log "  Port 8888 already in use - frontend likely running"
} else {
    $frontendProc = Start-Process -FilePath "powershell" `
        -ArgumentList "-Command", "Set-Location '$FrontendDir'; npm run dev 2>&1 | Tee-Object -FilePath '$ProjectRoot\frontend\dev_live.log'" `
        -WindowStyle Minimized `
        -PassThru
    Save-Pid "frontend" $frontendProc
    Log "  Frontend starting..."
    Start-Sleep -Seconds 5
}

# Wait for frontend to be ready
Log "  Waiting for Frontend..."
if (Wait-ForPort -port 8888 -timeout 60) {
    Log "  Frontend READY on port 8888"
} else {
    Log "  WARNING: Frontend may not be ready"
}

# ─────────────────────────────────────────────
# STEP 5: Start Unified Trading Engine
# ─────────────────────────────────────────────
Log ""
Log "STEP 4: Starting Unified Trading Engine..."

$enginePidFile = "$PidDir\engine.pid"
$engineRunning = $false
if (Test-Path $enginePidFile) {
    $epid = Get-Content $enginePidFile -ErrorAction SilentlyContinue
    if ($epid) { $engineRunning = [bool](Get-Process -Id ([int]$epid) -ErrorAction SilentlyContinue) }
}
if ($engineRunning) {
    Log "  Engine already running (PID $epid)"
} else {
    $env:DJANGO_SETTINGS_MODULE = "config.settings"
    $engineProc = Start-Process -FilePath "python" `
        -ArgumentList "unified_engine.py" `
        -WorkingDirectory $BackendDir `
        -WindowStyle Minimized `
        -RedirectStandardOutput "$ProjectRoot\engine_out.log" `
        -RedirectStandardError "$ProjectRoot\engine_err.log" `
        -PassThru
    Save-Pid "engine" $engineProc
    Log "  Trading engine starting..."
    Start-Sleep -Seconds 10
}

# ─────────────────────────────────────────────
# STEP 6: Verify Everything
# ─────────────────────────────────────────────
Log ""
Log "STEP 6: Verification..."

# Check health endpoint
Start-Sleep -Seconds 5
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health" -TimeoutSec 10
    Log "  Server health: $($health.status)"
    Log "  Database: $($health.checks.database)"
    Log "  Redis: $($health.checks.redis)"
} catch {
    Log "  WARNING: Health check failed - $_"
}

# Check frontend
try {
    $fe = Invoke-WebRequest -Uri "http://localhost:8888/" -TimeoutSec 15 -UseBasicParsing
    Log "  Frontend: OK (Status $($fe.StatusCode))"
} catch {
    Log "  WARNING: Frontend check failed - $_"
}

# Check MT5 via API
try {
    $mt5Status = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/live/mt5/status" -TimeoutSec 10
    Log "  MT5 connected: $($mt5Status.connected)"
} catch {
    Log "  MT5 status check timed out (engine may still be loading)"
}

# Final summary
$fastapiOk = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
$feOk = Get-NetTCPConnection -LocalPort 8888 -State Listen -ErrorAction SilentlyContinue
$mt5Proc = Get-Process -Name "terminal64" -ErrorAction SilentlyContinue

Log ""
Log "=========================================="
Log "  STARTUP COMPLETE"
Log "  FastAPI Server: $(if ($fastapiOk) {'OK (port 8000)'} else {'FAILED'})"
Log "  Frontend:       $(if ($feOk) {'OK (port 8888)'} else {'FAILED'})"
Log "  MT5 Terminal:   $(if ($mt5Proc) {'RUNNING'} else {'NOT FOUND'})"
Log "  API Docs:       http://localhost:8000/docs"
Log "  Dashboard:      http://localhost:8888"
Log "=========================================="
