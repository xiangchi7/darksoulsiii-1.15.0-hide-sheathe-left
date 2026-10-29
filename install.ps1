# Install HideSheathedLeft (DS3 1.15.0).
#
#   powershell -ExecutionPolicy Bypass -File install.ps1
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Status
#   powershell -ExecutionPolicy Bypass -File install.ps1 -SkipModels
#   powershell -ExecutionPolicy Bypass -File install.ps1 -GameDir "F:\...\DARK SOULS III\Game"
#
# -Force skips the "close the game first" check.  Tests and scripted round trips only: a running
# game keeps writing its own files, so the result is undefined.
#
# Writes into <game>\:
#   HideSheathedLeft.dll / .ini   the mod core and its configuration
#   xinput1_3.dll                 the loader shell (mirrors the real XInput exports)
#   chr\c0000.chrbnd.dcx          the player model, and every chr\*.chrbnd.dcx is given
#                                 the parking dummies 382/383 (see tools\patch-character-models.ps1)
#
# EVERY file this script is about to overwrite is copied first -- byte for byte -- into
#
#   <game>\.hsleft-backup\<same relative path>
#
# and every action is recorded in <game>\.hsleft-manifest.json:
#
#   * files that already existed and were overwritten -> native copy in .hsleft-backup\
#   * files that did NOT exist (this installer created them) -> restored by deleting them
#   * directories this installer created -> removed again when they end up empty
#
# restore.ps1 replays that manifest, so an uninstall puts the game back to the exact bytes it
# had before the install.  Without the backups the character models could only be "stripped"
# again, which is structural and not byte-identical (re-serialising the bundle and
# re-compressing the DCX always produces a slightly different file) -- that is why the
# pre-patch originals are kept.

param(
    [switch]$Status,
    [switch]$SkipModels,
    [string]$GameDir = '',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ManifestName = '.hsleft-manifest.json'
$BackupName   = '.hsleft-backup'
$Version      = '1.0.5'

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

$manifestPath = Join-Path $GameDir $ManifestName
$backupRoot   = Join-Path $GameDir $BackupName

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
    if (Test-Path -LiteralPath $manifestPath) {
        $m = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        Write-Host ''
        Write-Host ("manifest: installed {0} ({1}); {2} file(s) recorded, native backups in {3}" -f `
                    $m.installedAt, $m.version, @($m.files).Count, $BackupName)
    } else {
        Write-Host ''
        Write-Host "manifest: none - nothing installed here with this version (restore.ps1 would change"
        Write-Host "          nothing; -AllowLegacy is the explicit structural fallback for 1.0.4 and older)"
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
if ($running) {
    if (-not $Force) {
        throw "DarkSoulsIII.exe is running (pid $($running.Id)) - close the game first (the model and DLLs are read at start-up).  -Force overrides this for tests only: the running game keeps writing its own files."
    }
    Write-Host "WARNING: DarkSoulsIII.exe is running (pid $($running.Id)) - continuing because of -Force"
}

$records = New-Object System.Collections.ArrayList
$createdDirs = New-Object System.Collections.ArrayList

# A previous install of this mod already knows the true originals.  Re-installing on top of it
# must keep THOSE, not save the patched files as "the original": that is how you end up with an
# uninstall that restores a modded model.
$prev = @{}
if (Test-Path -LiteralPath $manifestPath) {
    try {
        $pm = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        foreach ($r in @($pm.files)) { $prev[[string]$r.path] = $r }
        Write-Host ("previous install found ({0}); its native backups are kept" -f $pm.installedAt)
    } catch {
        Write-Host "WARNING: $ManifestName could not be read - a backup of the CURRENT files will be taken"
    }
}

function Get-Rel([string]$full) { $full.Substring($GameDir.Length).TrimStart('\') }

# park a native copy of <dst> (as it is right now, before we touch it) and return the record
function Save-Native([string]$dst, [string]$rel) {
    $bak = Join-Path $backupRoot $rel
    $bakDir = Split-Path -Parent $bak
    if (-not (Test-Path -LiteralPath $bakDir)) { New-Item -ItemType Directory -Path $bakDir -Force | Out-Null }
    Copy-Item -LiteralPath $dst -Destination $bak -Force
    $item = Get-Item -LiteralPath $dst
    return [pscustomobject]@{
        path      = $rel
        existed   = $true
        before    = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash
        after     = ''
        size      = $item.Length
        backup    = (Get-Rel $bak)
        installedAt = (Get-Date).ToString('s')
    }
}

# record a file that did not exist before this install, so restore.ps1 deletes it again
function New-CreatedRecord([string]$rel) {
    return [pscustomobject]@{
        path    = $rel
        existed = $false
        before  = ''
        after   = ''
        size    = 0
        backup  = ''
        installedAt = (Get-Date).ToString('s')
    }
}

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
        throw ("missing kit file: $src`n" +
               "This folder looks like the git repository, not the release package.`n" +
               "Download HideSheathedLeft-1.0.5.zip from https://github.com/xiangchi7/darksoulsiii-1.15.0-hide-sheathe-left/releases/latest and run install.ps1 from the extracted folder.")
    }

    $dstDir = Split-Path -Parent $dst
    if (-not (Test-Path -LiteralPath $dstDir)) {
        New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
        [void]$createdDirs.Add((Get-Rel $dstDir))
    }

    $rel = Get-Rel $dst
    if (Test-Path -LiteralPath $dst) {
        # A previous install recorded the truth for this path.  If the file on disk is still the
        # one that install left, keep its record: its native backup is the original, and a file
        # that already did not exist before must stay a "delete me on uninstall" record (saving
        # it now would resurrect the previous install's own DLL on uninstall).
        $p = $prev[$rel]
        $nowHash = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash
        if ($p -and $nowHash -eq [string]$p.after) {
            if ($p.existed -and (Test-Path -LiteralPath (Join-Path $GameDir ([string]$p.backup)))) {
                Write-Host "keeping the original backup of $rel from the previous install"
                [void]$records.Add([pscustomobject]@{
                    path = $rel; existed = $true; before = [string]$p.before; after = ''
                    size = $p.size; backup = [string]$p.backup; installedAt = (Get-Date).ToString('s')
                })
            } else {
                Write-Host "$rel was created by the previous install - it will be deleted on uninstall"
                [void]$records.Add((New-CreatedRecord $rel))
            }
        } else {
            $rec = Save-Native $dst $rel
            [void]$records.Add($rec)
            Write-Host "backed up $rel -> $(Join-Path $BackupName $rel)"
        }
    } else {
        [void]$records.Add((New-CreatedRecord $rel))
    }

    Copy-Item -LiteralPath $src -Destination $dst -Force
    Write-Host ("installed {0,-28} <- {1}" -f $t.dst, $t.src)
}

# The 382/383 parking dummies must exist in EVERY character model (player and NPC),
# otherwise a character that resolves them gets the invalid-poly artifacts.  Each file is
# copied into .hsleft-backup\chr\ before it is patched, so restore.ps1 can put the exact
# original bytes back -- a re-serialised bundle is never byte-identical.
if (-not $SkipModels) {
    $patcher = Join-Path $PSScriptRoot 'tools\patch-character-models.ps1'
    $chrDir  = Join-Path $GameDir 'chr'
    if ((Test-Path -LiteralPath $patcher) -and (Test-Path -LiteralPath $chrDir)) {
        Write-Host ''
        Write-Host 'character models: adding dummy 382/383 to chr\*.chrbnd.dcx ...'

        $tool = Join-Path $PSScriptRoot 'tools\ds3tae.exe'
        $scanned = @()
        if (Test-Path -LiteralPath $tool) {
            # only back up (and only patch) files that really miss the dummies
            $scanned = & $tool scanid $chrDir '382,383' 'chrbnd' 2>&1 |
                       Where-Object { $_ -match '^\s*HIT\s+' } |
                       ForEach-Object { ($_ -replace '^\s*HIT\s+', '') -replace ':.*$', '' }
        }

        $all = @(Get-ChildItem -LiteralPath $chrDir -Filter '*.chrbnd.dcx' -File)
        $already = @{}
        foreach ($h in $scanned) { $already[$h] = $true }

        # For every model decide three things:
        #   * does it still need the dummies?          -> it goes into the patch list
        #   * do we have the original (this run or a previous one)? -> otherwise back it up now
        #   * is it still exactly the file a previous install left? -> keep THAT original
        [void]$createdDirs.Add((Get-Rel $backupRoot))
        $need = New-Object System.Collections.ArrayList
        $stale = New-Object System.Collections.ArrayList
        $haveRecord = @{}
        foreach ($f in $all) {
            $rel = Get-Rel $f.FullName
            $p = $prev[$rel]
            $nowHash = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
            $isOurs = ($p -and $p.existed -and $nowHash -eq [string]$p.after)

            if ($already.ContainsKey($f.Name)) {
                # already carries the dummies
                if ($isOurs) {
                    # our own earlier patch: keep the original we recorded back then
                    [void]$records.Add([pscustomobject]@{
                        path = $rel; existed = $true; before = [string]$p.before; after = ''
                        size = $p.size; backup = [string]$p.backup; installedAt = (Get-Date).ToString('s')
                    })
                    $haveRecord[$rel] = $true
                } elseif (-not $haveRecord.ContainsKey($rel)) {
                    # was patched by someone else (an older install, another mod): no original exists
                    [void]$stale.Add($f)
                }
                continue
            }

            [void]$need.Add($f)
            if ($isOurs) {
                [void]$records.Add([pscustomobject]@{
                    path = $rel; existed = $true; before = [string]$p.before; after = ''
                    size = $p.size; backup = [string]$p.backup; installedAt = (Get-Date).ToString('s')
                })
            } else {
                [void]$records.Add((Save-Native $f.FullName $rel))
            }
            $haveRecord[$rel] = $true
        }

        $bytes = ($need | Measure-Object -Property Length -Sum).Sum
        if (-not $bytes) { $bytes = 0 }
        Write-Host ("  {0} model(s): {1} already patched, {2} to patch ({3:N1} MB to back up)" -f `
                    $all.Count, ($all.Count - $need.Count), $need.Count, ($bytes / 1MB))
        if ($need.Count -gt 0) { Write-Host ("  backed up {0} original model(s) -> {1}\chr\" -f $need.Count, $BackupName) }

        if ($stale.Count -gt 0) {
            Write-Host ''
            Write-Host ("  NOTE: {0} model(s) already carried dummy 382/383 before this install." -f $stale.Count)
            Write-Host "        For those there is no native backup, so an uninstall can only strip the"
            Write-Host "        dummies structurally (the bundle is re-serialised and the DCX re-compressed,"
            Write-Host "        so the bytes differ).  For a byte-exact model, delete the loose"
            Write-Host "        chr\*.chrbnd.dcx and re-extract them from the game archives (UXM)."
        }

        if ($need.Count -gt 0) {
            & $patcher -GameDir $GameDir -Only (($need | ForEach-Object { $_.Name }) -join ',')
        } else {
            Write-Host '  every model is already patched - nothing to do'
        }
    } else {
        Write-Host ''
        Write-Host 'WARNING: tools\patch-character-models.ps1 not found - character models were NOT patched.'
        Write-Host '         Copy the tools\ folder next to install.ps1 and run install.ps1 again.'
    }
}

$manifest = [pscustomobject]@{
    version     = $Version
    installedAt = (Get-Date).ToString('s')
    gameDir     = $GameDir
    hidePoly    = '382,383'
    files       = @($records)
    createdDirs = @($createdDirs)
}

# What we installed, so restore.ps1 can tell "still exactly our file" (safe to put the original
# back) from "somebody else replaced it after us" (stop and ask).  '' means the file our
# installer would have written is already gone again.
foreach ($rec in $records) {
    $dst = Join-Path $GameDir ([string]$rec.path)
    $rec.after = if (Test-Path -LiteralPath $dst) { (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash } else { '' }
}

$json = $manifest | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($manifestPath, $json, (New-Object System.Text.UTF8Encoding($false)))
Write-Host ''
Write-Host ("manifest written: {0}  ({1} file record(s), {2} native backup(s))" -f `
            $ManifestName, @($records).Count, @($records | Where-Object { $_.existed }).Count)

Write-Host ''
Write-Host 'Done. Start the game from Steam and follow README.md in this folder.'
Write-Host 'HideSheathedLeft.log in the game folder must contain "HidePoly=" and the id you expect.'
Write-Host 'To uninstall: run restore.ps1 (it replays the manifest, so the game returns to its exact'
Write-Host 'pre-install bytes) or install.ps1 -Status to see what is installed right now.'
# exit codes must be ours: the bundled tools report "hits found" with 1, which is not a failure here
exit 0
