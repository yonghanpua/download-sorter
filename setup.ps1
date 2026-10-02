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

# --- Task 1: System tray icon on logon (watcher + dashboard) ---
$watchAction = New-ScheduledTaskAction `
    -Execute $PythonW `
    -Argument "main.py tray" `
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
    -Description "fileSorter system tray icon with real-time watcher and dashboard" `
    -Force | Out-Null

Write-Host "[OK] FileSorter-Watch  - runs on logon (system tray with watcher + dashboard)" -ForegroundColor Green

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
Write-Host "The tray icon will appear automatically on next logon." -ForegroundColor Cyan
Write-Host "To start it right now:" -ForegroundColor Cyan
Write-Host "  Start-ScheduledTask -TaskName 'FileSorter-Watch'"
