# Install / restore the "parking dummy" build of HideSheathedLeft (DS3 1.15.0)
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Status
#   powershell -ExecutionPolicy Bypass -File restore.ps1
#
# Installs four files into <game>\Game:
#   chr\c0000.chrbnd.dcx   player model with the parking dummy appended (id 382)
#   HideSheathedLeft.dll   the mod core (writes HidePoly instead of -1)
#   xinput1_3.dll          the loader shell (mirrors the real XInput exports)
#   HideSheathedLeft.ini   configuration (re-read every few seconds)
#
# Every file that is overwritten is first copied to *.vanilla-backup (or renamed
# to *.dkp-off), so restore.ps1 can always put the original state back.

param(
    [switch]$Status,
    [switch]$SkipModels,
    [string]$GameDir = ''
)

$ErrorActionPreference = 'Stop'

# Where is the game?  A hard-coded D:\... path (as in 1.0.3 and earlier) fails for everyone whose
# game lives on another drive or in another Steam library, so go looking for it instead:
#   1. -GameDir, when given (authoritative, even if DarkSoulsIII.exe is not in it)
#   2. the folder this package was extracted into -- people unzip it next to DarkSoulsIII.exe
#   3. every Steam library: HKCU\Software\Valve\Steam\SteamPath + steamapps\libraryfolders.vdf
#   4. the historical default
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
           "  powershell -ExecutionPolicy Bypass -File install.ps1 -GameDir `"F:\STEAM\steamapps\common\DARK SOULS III\Game`"")
}
$GameDir = Find-GameDir
if (-not $Status) { Write-Host "game dir: $GameDir" }

# The payload lives in files\ inside the install package.  The plain (repository) zip has no files\
# folder -- there the payload sits next to this script -- so fall back to the script directory and
# both layouts install exactly the same way.
$files = Join-Path $PSScriptRoot 'files'
if (-not (Test-Path -LiteralPath $files)) { $files = $PSScriptRoot }

$targets = @(
    @{ src = 'c0000.chrbnd.dcx';        dst = 'chr\c0000.chrbnd.dcx' },
    @{ src = 'HideSheathedLeft.dll';    dst = 'HideSheathedLeft.dll' },
    @{ src = 'HideSheathedLeft.ini';    dst = 'HideSheathedLeft.ini' },
    @{ src = 'xinput1_3.dll';           dst = 'xinput1_3.dll' }
)

if (-not (Test-Path -LiteralPath $GameDir)) { throw "game dir not found: $GameDir" }

if ($Status) {
    Write-Host "game dir: $GameDir"
    foreach ($t in $targets) {
        $dst = Join-Path $GameDir $t.dst
        if (Test-Path -LiteralPath $dst) {
            $item = Get-Item -LiteralPath $dst
            $hash = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.Substring(0, 16)
            Write-Host ("  {0,-28} {1,10} bytes  {2}  {3}" -f $t.dst, $item.Length, $item.LastWriteTime.ToString('yyyy-MM-dd HH:mm'), $hash)
        } else {
            Write-Host ("  {0,-28} MISSING" -f $t.dst)
        }
    }
    foreach ($b in @('chr\c0000.chrbnd.dcx.vanilla-backup', 'xinput1_3.dll.dkp-off')) {
        $p = Join-Path $GameDir $b
        if (Test-Path -LiteralPath $p) { Write-Host ("  backup: {0} ({1} bytes)" -f $b, (Get-Item -LiteralPath $p).Length) }
    }
    # character-model patch state: every chr\*.chrbnd.dcx needs dummy 382/383
    $chrDir = Join-Path $GameDir 'chr'
    $scanner = Join-Path $PSScriptRoot 'tools\ds3tae.exe'
    if ((Test-Path -LiteralPath $chrDir) -and (Test-Path -LiteralPath $scanner)) {
        Write-Host ''
        Write-Host 'character models:'
        $total = (Get-ChildItem -LiteralPath $chrDir -Filter '*.chrbnd.dcx' -File).Count
        Write-Host ("  chr\*.chrbnd.dcx files: {0}" -f $total)
        & $scanner scanid $chrDir '382,383' 'chrbnd' | Select-Object -Last 2 | ForEach-Object { Write-Host ("  " + $_) }
    }
    return
}

$running = Get-Process -Name 'DarkSoulsIII' -ErrorAction SilentlyContinue
if ($running) { throw "DarkSoulsIII.exe is running (pid $($running.Id)) - close the game first (the model and DLLs are read at start-up)" }

foreach ($t in $targets) {
    $src = Join-Path $files $t.src
    $dst = Join-Path $GameDir $t.dst
    if (-not (Test-Path -LiteralPath $src)) {
        if ($t.src -eq 'c0000.chrbnd.dcx') {
            # release without game assets: the character-model patch below adds 382/383 to
            # every chr\*.chrbnd.dcx, the player's model included
            Write-Host "no prebuilt chr\c0000.chrbnd.dcx in this package - the model patcher will handle it"
            continue
        }
        throw "missing kit file: $src"
    }

    $dstDir = Split-Path -Parent $dst
    if (-not (Test-Path -LiteralPath $dstDir)) { New-Item -ItemType Directory -Path $dstDir | Out-Null }

    if (Test-Path -LiteralPath $dst) {
        # Is the file that is already there one of ours (byte-identical to the payload)?
        # Then there is nothing to preserve -- never park our own file as a "backup".
        $mine = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash -eq
                (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash

        if ($mine) {
            Remove-Item -LiteralPath $dst -Force
        } elseif ($t.dst -eq 'xinput1_3.dll') {
            # a foreign proxy DLL (DynamicKeyPrompts and friends) owns the import slot
            $off = "$dst.dkp-off"
            if (-not (Test-Path -LiteralPath $off)) {
                Rename-Item -LiteralPath $dst -NewName 'xinput1_3.dll.dkp-off'
                Write-Host "renamed existing xinput1_3.dll -> xinput1_3.dll.dkp-off (kept, not loaded)"
            } else {
                Copy-Item -LiteralPath $dst -Destination "$dst.foreign-backup" -Force
                Write-Host "kept the foreign xinput1_3.dll as xinput1_3.dll.foreign-backup (dkp-off already occupied)"
            }
        } else {
            # keep the very first original; a later re-install must not overwrite it
            $bak = "$dst.vanilla-backup"
            if (-not (Test-Path -LiteralPath $bak)) {
                Copy-Item -LiteralPath $dst -Destination $bak -Force
                Write-Host "backed up $($t.dst) -> $(Split-Path -Leaf $bak)"
            } else {
                Write-Host "replacing $($t.dst) (backup already exists: $(Split-Path -Leaf $bak))"
            }
        }
    }

    Copy-Item -LiteralPath $src -Destination $dst -Force
    Write-Host ("installed {0,-28} <- {1}" -f $t.dst, $t.src)
}

# The 382/383 parking dummies must exist in EVERY character model (player and NPC),
# otherwise a character that resolves them gets the invalid-poly artifacts.  The
# player's model came with the kit; the other 164 are patched here by the bundled
# tool, which verifies each file before writing and skips files that already have
# the dummies.
if (-not $SkipModels) {
    $patcher = Join-Path $PSScriptRoot 'tools\patch-character-models.ps1'
    if (Test-Path -LiteralPath $patcher) {
        Write-Host ''
        Write-Host 'character models: adding dummy 382/383 to chr\*.chrbnd.dcx ...'
        & $patcher -GameDir $GameDir
    } else {
        Write-Host ''
        Write-Host 'WARNING: tools\patch-character-models.ps1 not found - character models were NOT patched.'
        Write-Host '         Copy the tools\ folder next to install.ps1 and run install.ps1 again.'
    }
}

Write-Host ''
Write-Host 'Done. Start the game from Steam and follow README.md in this folder.'
Write-Host 'HideSheathedLeft.log in the game folder must contain "HidePoly=" and the id you expect.'