param([string]$ConfigPath = $(if ($env:SECOND_BRAIN_CONFIG) { $env:SECOND_BRAIN_CONFIG } else { Join-Path $env:LOCALAPPDATA 'SecondBrain\personal\config.json' }))
$ErrorActionPreference = 'Stop'
$PersonalConfig = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
if ($PersonalConfig.scope -ne 'personal') { throw 'Only the personal deployment can be hardened here.' }
$OwnerSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$AclBackup = Join-Path $PersonalConfig.state_path 'acl-before.json'
$PreviousAcls = @()
foreach ($TargetPath in @($PersonalConfig.vault_path, $PersonalConfig.state_path)) {
    $ResolvedTarget = (Resolve-Path -LiteralPath $TargetPath).Path
    $TaskRoot = [System.IO.Path]::GetPathRoot($ResolvedTarget)
    $TaskRepository = Split-Path -Parent $PSScriptRoot
    $TaskTargetPrefix = $ResolvedTarget.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    $TaskRepoPrefix = $TaskRepository.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    $TaskProtected = @($TaskRoot, $env:USERPROFILE, $env:LOCALAPPDATA, $TaskRepository)
    $TaskBroad = $TaskProtected | Where-Object {
        $_ -and ($_ -eq $ResolvedTarget -or $_.StartsWith($TaskTargetPrefix, [System.StringComparison]::OrdinalIgnoreCase))
    }
    if ($TaskBroad -or $ResolvedTarget.StartsWith($TaskRepoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Deployment roots must be private directories outside the source repository.'
    }
    $PreviousAcls += @{ path = $ResolvedTarget; sddl = (Get-Acl -LiteralPath $ResolvedTarget).Sddl }
}
if (-not (Test-Path -LiteralPath $AclBackup)) {
    $PreviousAcls | ConvertTo-Json | Set-Content -LiteralPath $AclBackup -Encoding utf8
}
foreach ($TargetPath in @($PersonalConfig.vault_path, $PersonalConfig.state_path)) {
    $NewAcl = [System.Security.AccessControl.DirectorySecurity]::new()
    $NewAcl.SetOwner($OwnerSid)
    $NewAcl.SetAccessRuleProtection($true, $false)
    foreach ($AllowedSid in @($OwnerSid.Value, 'S-1-5-18', 'S-1-5-32-544')) {
        $IdentitySid = [System.Security.Principal.SecurityIdentifier]::new($AllowedSid)
        $Rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
            $IdentitySid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $NewAcl.AddAccessRule($Rule)
    }
    Set-Acl -LiteralPath $TargetPath -AclObject $NewAcl
}
Write-Output 'Personal vault and state restricted to owner, SYSTEM and administrators. Previous ACLs saved locally.'
