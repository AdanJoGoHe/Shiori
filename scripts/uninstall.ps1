$ErrorActionPreference = 'Stop'
& (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\second-brain.exe') uninstall
if ($LASTEXITCODE -ne 0) { throw 'Shiori uninstall failed.' }
