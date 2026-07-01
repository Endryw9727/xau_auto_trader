<#
.SYNOPSIS
    Register the research-stack supervisor as a Windows scheduled task that runs
    at system startup and restarts on failure. Idempotent: re-running replaces
    the existing task.

.DESCRIPTION
    The task runs run_research_stack.ps1 (API + ngrok supervisor) as the current
    user via S4U (LogonType "run whether the user is logged on or not", no stored
    password). Running as the current user — rather than SYSTEM — matters so that
    ngrok finds this user's auth token / config. No credentials or secrets are
    handled by this script.

.NOTES
    Run once, elevated (Administrator PowerShell):
        powershell -ExecutionPolicy Bypass -File scripts\ops\install_research_stack_task.ps1

    Manage afterwards:
        Get-ScheduledTask XauResearchStack
        Start-ScheduledTask XauResearchStack
        Stop-ScheduledTask  XauResearchStack
        Unregister-ScheduledTask XauResearchStack -Confirm:$false
#>
param(
    [string]$RepoRoot = "C:\Users\Administrator\xau_auto_trader",
    [string]$TaskName = "XauResearchStack"
)

$ErrorActionPreference = "Stop"

$supervisor = Join-Path $RepoRoot "scripts\ops\run_research_stack.ps1"
if (-not (Test-Path $supervisor)) {
    throw "Supervisor script not found: $supervisor (did you 'git pull'?)"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$supervisor`""

$trigger = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew

# Run as the current user, whether logged on or not, without storing a password.
$userId    = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType S4U -RunLevel Highest

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Keep the XAU read-only research API and ngrok tunnel alive (diagnostics only, no orders)." | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "[install] Task '$TaskName' registered and started (runs at every boot as $userId)."
