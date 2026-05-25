$Root = "C:\Users\Administrator\xau_auto_trader"
$Python = "$Root\.venv\Scripts\python.exe"
$LogDir = "$Root\reports\demo_execution"
$Log = "$LogDir\v51_live_safe_cycle_task.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Set-Location $Root

"============================================================" | Out-File $Log -Append
"V51 LIVE SAFE CYCLE START $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $Log -Append

& $Python scripts\run_v51_live_safe_cycle.py --execute-demo *>> $Log

"V51 LIVE SAFE CYCLE END $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $Log -Append
