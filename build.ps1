# Build a one-file Windows executable -> dist\radar.exe
# Usage:  ./build.ps1      then double-click dist\radar.exe (no Python needed to run it)
python -m pip install -q pyinstaller
python -m PyInstaller --noconfirm --onefile --name radar `
  --add-data "web/panel.html;web" `
  --collect-all aiohttp `
  run_radar.py
Write-Host ""
Write-Host "Built dist\radar.exe - double-click it to run." -ForegroundColor Green
