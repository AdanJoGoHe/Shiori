param([string]$ConfigPath = $(if ($env:SECOND_BRAIN_CONFIG) { $env:SECOND_BRAIN_CONFIG } else { Join-Path $env:LOCALAPPDATA 'SecondBrain\personal\config.json' }))
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $PythonExe)) { throw 'Create the project .venv first; see README.md.' }
$InitializationOutput = & $PythonExe (Join-Path $PSScriptRoot 'init-personal.py') --config $ConfigPath
if ($LASTEXITCODE -ne 0) { throw 'Personal deployment initialization failed.' }
$EffectiveConfigPath = ($InitializationOutput | ConvertFrom-Json).config_path
if (-not [System.IO.Path]::IsPathRooted($EffectiveConfigPath)) { throw 'Initializer did not return an absolute configuration path.' }
& (Join-Path $PSScriptRoot 'secure-personal.ps1') -ConfigPath $EffectiveConfigPath
& $PythonExe -m second_brain.cli --config $EffectiveConfigPath install-codex
if ($LASTEXITCODE -ne 0) { throw 'Codex installation failed; inspect the recovery manifest.' }
