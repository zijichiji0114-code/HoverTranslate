$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv venv --python 3.12 .venv
    if ($LASTEXITCODE -ne 0) { throw 'Creating Python environment failed.' }
    uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
} else {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12, or install uv, then retry.' }
    & .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
}
if ($LASTEXITCODE -ne 0) { throw 'Installing dependencies failed.' }
Write-Host 'Ready. Double-click start.cmd to launch.'
