$ErrorActionPreference = "Continue"

Set-Location "C:\Users\Administrator\xau_auto_trader"

$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content ".\reports\paper_forward\paper_cycle.log" "`n================ $ts ================"

.\.venv\Scripts\python.exe scripts\force_overwrite_m15_xauusd_p.py 2>&1 | Tee-Object -Append ".\reports\paper_forward\paper_cycle.log"

.\.venv\Scripts\python.exe scripts\paper_preflight_check.py 2>&1 | Tee-Object -Append ".\reports\paper_forward\paper_cycle.log"

.\.venv\Scripts\python.exe scripts\run_paper_forward_once.py 2>&1 | Tee-Object -Append ".\reports\paper_forward\paper_cycle.log"

.\.venv\Scripts\python.exe scripts\paper_forward_status.py 2>&1 | Tee-Object -Append ".\reports\paper_forward\paper_cycle.log"
