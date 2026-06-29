# V51 demo cycle for the Windows VPS (mirrors run_demo_cycle.ps1 for the V51 path).
#
# This does NOTHING until V51 demo execution is armed via the gitignored local
# override config\strategy_v51.local.yaml (see config\strategy_v51.local.yaml.example).
# While the committed config keeps allow_demo_execution/execution_enabled = false,
# run_v51_live_safe_cycle.py returns REJECTED and submits no orders.
#
# Schedule this with Task Scheduler the same way as run_demo_cycle.ps1 only after
# you have armed the local override and confirmed a clean --dry-run.

$Root = "C:\Users\Administrator\xau_auto_trader"
$Python = "$Root\.venv\Scripts\python.exe"
$LogDir = "$Root\reports\demo_execution"
$Log = "$LogDir\v51_demo_cycle.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Set-Location $Root

"============================================================" | Out-File $Log -Append
"V51 DEMO CYCLE START $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $Log -Append

& $Python scripts\update_mt5_timeframes.py *>> $Log
& $Python scripts\run_v51_mtf_context_report.py *>> $Log
& $Python scripts\run_v51_live_safe_cycle.py --execute-demo *>> $Log

"V51 DEMO CYCLE END $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $Log -Append
