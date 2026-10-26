<# Install a new, separate work memory from reviewed local release assets. Preview by default. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ReleaseDir,
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [string]$Timezone = 'UTC',
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$releasePath = (Resolve-Path -LiteralPath $ReleaseDir).Path
$installPath = [System.IO.Path]::GetFullPath($InstallDir)
if (Test-Path -LiteralPath $installPath) { throw 'Choose a new installation directory.' }
$hashes = @{}
foreach ($line in (Get-Content -LiteralPath (Join-Path $releasePath 'SHA256SUMS'))) {
    if ($line -cnotmatch '^([a-f0-9]{64})  ([a-zA-Z0-9_.-]+)$') { throw 'Invalid checksums.' }
    if ($hashes.ContainsKey($Matches[2])) { throw 'Duplicate checksum entry.' }
    $hashes[$Matches[2]] = $Matches[1]
}
$wheels = @($hashes.Keys | Where-Object { $_ -cmatch '^second_brain-(\d+\.\d+\.\d+a\d+)-py3-none-any\.whl$' })
if ($wheels.Count -ne 1) { throw 'Expected one versioned Shiori wheel.' }
$wheelName = $wheels[0]
$null = $wheelName -cmatch '^second_brain-(\d+\.\d+\.\d+a\d+)-py3-none-any\.whl$'
$releaseVersion = $Matches[1]
$constraintsName = "second_brain-$releaseVersion-constraints.txt"
foreach ($name in @($wheelName, $constraintsName)) {
    $asset = Join-Path $releasePath $name
    $stream = [System.IO.File]::OpenRead($asset)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try { $actual = [System.BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $hasher.Dispose() }
    if ($actual -cne $hashes[$name]) {
        throw 'Release checksum mismatch.'
    }
}
# Constraints are parsed by uv before the package's own verifier can run.
foreach ($line in (Get-Content -LiteralPath (Join-Path $releasePath $constraintsName))) {
    if ($line.Trim() -eq '' -or $line.TrimStart().StartsWith('#')) { continue }
    if ($line -cnotmatch '^[a-zA-Z0-9][a-zA-Z0-9_.-]*==[a-zA-Z0-9_.+!-]+(\s*;\s*[^\r\n]+)?$') {
        throw 'Only exact registry pins are allowed in release constraints.'
    }
}
if (-not $Apply) {
    [pscustomobject]@{ Status = 'ready'; Scope = 'work'; Version = $releaseVersion; InstallDir = $installPath }
    return
}
$null = Get-Command uv -ErrorAction Stop
$wheelUri = ([System.Uri](Join-Path $releasePath $wheelName)).AbsoluteUri
$constraintsUri = ([System.Uri](Join-Path $releasePath $constraintsName)).AbsoluteUri
& uv --no-config tool run --isolated --no-env-file --python 3.12 `
    --from $wheelUri --constraints $constraintsUri `
    shiori-runtime --root $installPath install --release-dir $releasePath --timezone $Timezone --apply
if ($LASTEXITCODE -ne 0) { throw 'Installation failed; inspect the partial directory before retrying.' }
