# setup.ps1 - Register Windows Task Scheduler tasks for fileSorter
# Run with: powershell -ExecutionPolicy Bypass -File setup.ps1

$ProjectDir = $PSScriptRoot
$PythonW = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
$Python  = Join-Path $ProjectDir ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonW)) {
    Write-Host "Virtual environment not found. Set it up first:" -ForegroundColor Red
    Write-Host "  python -m venv .venv"
    Write-Host "  .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

# --- Task 1: Real-time watcher on logon ---
$watchAction = New-ScheduledTaskAction `
    -Execute $PythonW `
    -Argument "main.py watch --log-dir logs" `
    -WorkingDirectory $ProjectDir

$watchTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$watchSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName "FileSorter-Watch" `
    -Action $watchAction `
    -Trigger $watchTrigger `
    -Settings $watchSettings `
    -Description "Real-time file sorter watching the Downloads folder" `
    -Force | Out-Null

Write-Host "[OK] FileSorter-Watch  - runs on logon (real-time watcher)" -ForegroundColor Green

# --- Task 2: Daily sweep at 2 AM ---
$sweepAction = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "main.py sweep --log-dir logs" `
    -WorkingDirectory $ProjectDir

$sweepTrigger = New-ScheduledTaskTrigger -Daily -At "2:00AM"

$sweepSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName "FileSorter-Sweep" `
    -Action $sweepAction `
    -Trigger $sweepTrigger `
    -Settings $sweepSettings `
    -Description "Daily sweep of Downloads folder at 2 AM" `
    -Force | Out-Null

Write-Host "[OK] FileSorter-Sweep - runs daily at 2:00 AM" -ForegroundColor Green
Write-Host ""
Write-Host "The watcher will start automatically on next logon." -ForegroundColor Cyan
Write-Host "To start it right now:" -ForegroundColor Cyan
Write-Host "  Start-ScheduledTask -TaskName 'FileSorter-Watch'"
