$ErrorActionPreference = 'Stop'
& (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\second-brain.exe') doctor
if ($LASTEXITCODE -ne 0) { throw 'Shiori diagnostic failed.' }
