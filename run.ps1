# Highlight Radar - setup + run (Windows PowerShell)
if (-not (Test-Path .venv)) { python -m venv .venv }
& .\.venv\Scripts\Activate.ps1
pip install -q -r requirements.txt
python -m radar
