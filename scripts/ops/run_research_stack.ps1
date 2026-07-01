<#
.SYNOPSIS
    Supervisor that keeps the read-only research API and the ngrok tunnel alive
    on the Windows VPS, so the deployed console (tradingbotai.it) never loses its
    backend when a window is closed or the machine reboots.

.DESCRIPTION
    Starts:
      1. the research API  (.venv\Scripts\python.exe scripts\serve_research_api.py)
      2. the ngrok tunnel  (<NgrokExe> http --domain=<NgrokDomain> <Port>)
    then loops forever and restarts either one if it exits. This process sends NO
    orders: it only launches the diagnostics-only API and a tunnel. Logs go under
    reports\ops\ (git-ignored, runtime only).

.NOTES
    Run manually:
        powershell -ExecutionPolicy Bypass -File scripts\ops\run_research_stack.ps1
    Or install it at startup with scripts\ops\install_research_stack_task.ps1.
#>
param(
    [string]$RepoRoot     = "C:\Users\Administrator\xau_auto_trader",
    [string]$NgrokExe     = "C:\ngrok\ngrok.exe",
    [string]$NgrokDomain  = "smith-agreed-princess.ngrok-free.dev",
    [int]   $Port         = 8000,
    [int]   $CheckSeconds = 30
)

$ErrorActionPreference = "Stop"

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$logDir = Join-Path $RepoRoot "reports\ops"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$apiLog   = Join-Path $logDir "research_api.log"
$ngrokLog = Join-Path $logDir "ngrok.log"

function Test-PortListening([int]$p) {
    try { Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction Stop | Out-Null; return $true }
    catch { return $false }
}

function Start-Api {
    # Skip if something is already serving the port (e.g. a manual run): leave it
    # be instead of fighting for the bind.
    if (Test-PortListening $Port) { return $null }
    return Start-Process -FilePath $python `
        -ArgumentList @("scripts\serve_research_api.py", "--host", "0.0.0.0", "--port", "$Port") `
        -WorkingDirectory $RepoRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $apiLog -RedirectStandardError "$apiLog.err"
}

function Start-Ngrok {
    # ngrok's local inspector listens on 4040; if it's up, a tunnel already runs.
    if (Test-PortListening 4040) { return $null }
    return Start-Process -FilePath $NgrokExe `
        -ArgumentList @("http", "--domain=$NgrokDomain", "$Port", "--log=stdout") `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $ngrokLog -RedirectStandardError "$ngrokLog.err"
}

Write-Host "[run_research_stack] supervising API (:$Port) + ngrok ($NgrokDomain)"
$api   = Start-Api
$ngrok = Start-Ngrok

while ($true) {
    Start-Sleep -Seconds $CheckSeconds
    if (($null -eq $api)   -or $api.HasExited)   { $api   = Start-Api }
    if (($null -eq $ngrok) -or $ngrok.HasExited) { $ngrok = Start-Ngrok }
}
