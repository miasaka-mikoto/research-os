$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip pyinstaller
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
& .\.venv\Scripts\python.exe scripts\verify_demo.py

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& .\.venv\Scripts\pyinstaller.exe `
  --noconfirm --clean --windowed --name ResearchOS `
  --paths . `
  --add-data "assets;assets" `
  run_researchos.py

Write-Host "Build complete: $projectRoot\dist\ResearchOS\ResearchOS.exe"
