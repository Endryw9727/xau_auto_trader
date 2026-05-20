$Root = "C:\Users\Administrator\xau_auto_trader"
$Python = "$Root\.venv\Scripts\python.exe"
$LogDir = "$Root\reports\demo_execution"
$Log = "$LogDir\demo_cycle.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Set-Location $Root

"============================================================" | Out-File $Log -Append
"DEMO CYCLE START $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $Log -Append

& $Python scripts\check_mt5_demo_execution_readiness.py *>> $Log
& $Python scripts\run_demo_execution_once.py --execute-demo *>> $Log

"DEMO CYCLE END $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $Log -Append
