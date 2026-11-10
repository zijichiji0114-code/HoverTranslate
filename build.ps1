param([string]$OutputDirectory = 'dist')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& .venv\Scripts\python.exe -c "from comtypes.client import GetModule; GetModule('UIAutomationCore.dll')"
if ($LASTEXITCODE -ne 0) { throw 'Generating UI Automation interfaces failed.' }
& .venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name HoverTranslate --distpath $OutputDirectory --collect-all rapidocr_onnxruntime --collect-data onnxruntime --collect-binaries onnxruntime --hidden-import comtypes.gen.UIAutomationClient --hidden-import comtypes.stream --exclude-module pytest --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick main.py
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
$appOutput = Join-Path $OutputDirectory 'HoverTranslate'
Copy-Item -LiteralPath README.md -Destination (Join-Path $appOutput 'README.md')
foreach ($notice in @('LICENSE', 'THIRD_PARTY_NOTICES.md')) {
    if (Test-Path -LiteralPath $notice) { Copy-Item -LiteralPath $notice -Destination (Join-Path $appOutput $notice) }
}
if (Test-Path -LiteralPath 'assets\hovertranslate.ico') {
    Copy-Item -LiteralPath 'assets\hovertranslate.ico' -Destination (Join-Path $appOutput 'hovertranslate.ico')
}
& .venv\Scripts\python.exe scripts\collect_licenses.py $appOutput
if ($LASTEXITCODE -ne 0) { throw 'Collecting license notices failed.' }
Write-Host "Built $appOutput\HoverTranslate.exe"
