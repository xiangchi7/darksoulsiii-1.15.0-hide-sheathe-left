# Put the game folder back to the state it had before install.ps1.
#
#   powershell -ExecutionPolicy Bypass -File restore.ps1

param(
    [string]$GameDir = ''
)

$ErrorActionPreference = 'Stop'

# Same lookup as install.ps1: -GameDir, else the folder this package sits in, else every Steam
# library, else the historical default.  A hard-coded path breaks installs on other drives.
function Find-GameDir {
    if ($GameDir) {
        if (-not (Test-Path -LiteralPath $GameDir)) { throw "the -GameDir you passed does not exist: $GameDir" }
        return (Resolve-Path -LiteralPath $GameDir).Path
    }

    $candidates = @($PSScriptRoot)
    $steam = (Get-ItemProperty -Path 'HKCU:\Software\Valve\Steam' -Name SteamPath -ErrorAction SilentlyContinue).SteamPath
    if ($steam) {
        $libs = @($steam)
        $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
        if (Test-Path -LiteralPath $vdf) {
            $text = [System.IO.File]::ReadAllText($vdf)
            foreach ($m in [regex]::Matches($text, '"path"\s+"([^"]+)"')) {
                $libs += ($m.Groups[1].Value -replace '\\\\', '\')
            }
            if ($libs.Count -eq 1) {    # older Steam lists them as "1"  "D:\Steam"
                foreach ($m in [regex]::Matches($text, '"\d+"\s+"([A-Za-z]:[^"]+)"')) {
                    $libs += ($m.Groups[1].Value -replace '\\\\', '\')
                }
            }
        }
        foreach ($lib in $libs) { $candidates += (Join-Path $lib 'steamapps\common\DARK SOULS III\Game') }
    }
    $candidates += 'D:\Steam\steamapps\common\DARK SOULS III\Game'
    $candidates = $candidates | Select-Object -Unique

    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath (Join-Path $c 'DarkSoulsIII.exe'))) { return (Resolve-Path -LiteralPath $c).Path }
    }
    throw ("game dir not found.  Tried:`n  " + ($candidates -join "`n  ") +
           "`n`nPass the folder that contains DarkSoulsIII.exe, for example:`n" +
           "  powershell -ExecutionPolicy Bypass -File restore.ps1 -GameDir `"F:\STEAM\steamapps\common\DARK SOULS III\Game`"")
}
$GameDir = Find-GameDir
Write-Host "game dir: $GameDir"

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
