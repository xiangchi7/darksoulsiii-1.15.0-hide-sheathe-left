# Put the game folder back to the state it had before install.ps1.
#
#   powershell -ExecutionPolicy Bypass -File restore.ps1

param(
    [string]$GameDir = 'D:\Steam\steamapps\common\DARK SOULS III\Game'
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $GameDir)) { throw "game dir not found: $GameDir" }

$running = Get-Process -Name 'DarkSoulsIII' -ErrorAction SilentlyContinue
if ($running) { throw "DarkSoulsIII.exe is running (pid $($running.Id)) - close the game first" }

# 1. the player model: bring the pre-install copy back
$model = Join-Path $GameDir 'chr\c0000.chrbnd.dcx'
$modelBak = "$model.vanilla-backup"
if (Test-Path -LiteralPath $modelBak) {
    Copy-Item -LiteralPath $modelBak -Destination $model -Force
    Write-Host "restored chr\c0000.chrbnd.dcx from its vanilla-backup"
} else {
    Write-Host "no chr\c0000.chrbnd.dcx.vanilla-backup present - leaving the file alone"
}

# 2. the mod files: remove them, put the original xinput1_3.dll back
foreach ($f in @('HideSheathedLeft.dll', 'HideSheathedLeft.ini', 'HideSheathedLeft.log', 'xinput1_3_proxy.log')) {
    $p = Join-Path $GameDir $f
    if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force; Write-Host "removed $f" }
}
$proxy = Join-Path $GameDir 'xinput1_3.dll'
if (Test-Path -LiteralPath $proxy) { Remove-Item -LiteralPath $proxy -Force; Write-Host 'removed xinput1_3.dll (loader shell)' }

$dkp = Join-Path $GameDir 'xinput1_3.dll.dkp-off'
if (Test-Path -LiteralPath $dkp) {
    Rename-Item -LiteralPath $dkp -NewName 'xinput1_3.dll'
    Write-Host 'renamed xinput1_3.dll.dkp-off back to xinput1_3.dll'
}

Write-Host 'Restore finished.'
