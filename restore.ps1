# Uninstall HideSheathedLeft: put the game folder back to the state it had before install.ps1.
#
#   powershell -ExecutionPolicy Bypass -File restore.ps1
#   powershell -ExecutionPolicy Bypass -File restore.ps1 -DryRun       # only report what it would do
#   powershell -ExecutionPolicy Bypass -File restore.ps1 -KeepBackups  # keep .hsleft-backup\ and the manifest
#   powershell -ExecutionPolicy Bypass -File restore.ps1 -Force        # restore even if a file changed since
#                                                                     # (and ignore a running game - tests only)
#
# What it does, driven by <game>\.hsleft-manifest.json (written by install.ps1):
#   * every file the installer overwrote -> copied back from .hsleft-backup\<same relative path>,
#     byte for byte, then verified against the recorded SHA-256
#   * every file the installer created   -> deleted
#   * every directory the installer made -> removed when it ends up empty
#   * character models: the 382/383 dummies disappear with the original bytes; as a second
#     check tools\ds3tae.exe verify proves no model still carries them
#
# If the file is not the one we installed any more (you replaced it, or another mod did), the
# restore stops and tells you instead of overwriting someone else's work; -Force overrides that.
#
# Without a manifest (an installation from 1.0.4 or older) it falls back to the old behaviour:
# strip the dummies structurally, put chr\c0000.chrbnd.dcx back from its .vanilla-backup and
# remove the mod files.  A structural strip is *not* byte-identical (see README), which is
# exactly why install.ps1 now keeps native copies.

param(
    [string]$GameDir = '',
    [switch]$DryRun,
    [switch]$KeepBackups,
    [switch]$Force,
    [switch]$AllowLegacy
)

$ErrorActionPreference = 'Stop'
$ManifestName = '.hsleft-manifest.json'
$BackupName   = '.hsleft-backup'

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
if ($DryRun) { Write-Host 'dry run: nothing will be changed' }

$running = Get-Process -Name 'DarkSoulsIII' -ErrorAction SilentlyContinue
if ($running) {
    if (-not $Force) {
        throw "DarkSoulsIII.exe is running (pid $($running.Id)) - close the game first.  -Force overrides this for tests only: the running game keeps writing its own files."
    }
    Write-Host "WARNING: DarkSoulsIII.exe is running (pid $($running.Id)) - continuing because of -Force"
}

$manifestPath = Join-Path $GameDir $ManifestName
$backupRoot   = Join-Path $GameDir $BackupName
$chrDir       = Join-Path $GameDir 'chr'
$tool         = Join-Path $PSScriptRoot 'tools\ds3tae.exe'

function Remove-It([string]$path, [string]$what) {
    if (-not (Test-Path -LiteralPath $path)) { return }
    if ($DryRun) { Write-Host "  would remove $what" }
    else { Remove-Item -LiteralPath $path -Force; Write-Host "  removed $what" }
}

$problems = New-Object System.Collections.ArrayList
$restored = 0
$deleted  = 0
$skipped  = 0

if (Test-Path -LiteralPath $manifestPath) {
    # ------------------------------------------------------------------ manifest replay
    $m = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    Write-Host ("manifest: installed {0} by version {1}" -f $m.installedAt, $m.version)

    Write-Host ''
    Write-Host 'files:'
    foreach ($rec in @($m.files)) {
        $rel  = [string]$rec.path
        $dst  = Join-Path $GameDir $rel
        $bak  = Join-Path $GameDir ([string]$rec.backup)
        $what = $rel

        if ($rec.existed) {
            if (-not (Test-Path -LiteralPath $bak)) {
                [void]$problems.Add("backup missing for $rel")
                Write-Host "  PROBLEM  $rel : native backup missing ($($rec.backup))"
                $skipped++
                continue
            }
            # Is the file still the one WE installed?  Then the original goes back.  If it is
            # neither our file nor the original any more, someone else owns it now: stop and
            # say so instead of overwriting their work (unless -Force).
            if (Test-Path -LiteralPath $dst) {
                $now = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash
                $ours = ($now -eq [string]$rec.after)
                if ($now -eq [string]$rec.before) {
                    Write-Host "  already original: $rel (nothing to do)"
                    continue
                }
                if (-not $ours -and -not $Force) {
                    [void]$problems.Add("$rel changed since install (restore skipped; -Force to overwrite)")
                    Write-Host "  SKIP     $rel : changed since the install - not overwriting it (use -Force)"
                    $skipped++
                    continue
                }
            }
            if ($DryRun) {
                Write-Host "  would restore $rel from $($rec.backup)"
            } else {
                $d = Split-Path -Parent $dst
                if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
                Copy-Item -LiteralPath $bak -Destination $dst -Force
                $back = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash
                if ($back -eq $rec.before) {
                    Write-Host "  restored $rel (byte-exact, $($rec.size) bytes)"
                    $restored++
                } else {
                    [void]$problems.Add("$rel restored but its hash does not match the record")
                    Write-Host "  PROBLEM  $rel : restored file does not match the recorded hash"
                }
            }
        } else {
            if (Test-Path -LiteralPath $dst) {
                if ($DryRun) { Write-Host "  would delete $rel (this installer created it)" }
                else { Remove-Item -LiteralPath $dst -Force; Write-Host "  deleted $rel (this installer created it)"; $deleted++ }
            } else {
                Write-Host "  gone already: $rel (installer-created)"
            }
        }
    }

    # the mod's own leftovers, whether or not the manifest mentioned them
    Write-Host ''
    Write-Host 'leftovers:'
    foreach ($f in 'HideSheathedLeft.log', 'xinput1_3_proxy.log') {
        Remove-It (Join-Path $GameDir $f) $f
    }

    # ---- backups first: an empty directory can only be judged after they are gone
    if (-not $KeepBackups -and $problems.Count -gt 0) {
        Write-Host ''
        Write-Host "kept $BackupName\ and $ManifestName because the restore was not complete"
        Write-Host '(--Force finishes it, -KeepBackups keeps them on purpose)'
    } elseif (-not $KeepBackups) {
        Write-Host ''
        Write-Host 'backups:'
        if ($DryRun) {
            Write-Host "  would remove $BackupName\ and $ManifestName"
        } else {
            if (Test-Path -LiteralPath $backupRoot) { Remove-Item -LiteralPath $backupRoot -Recurse -Force; Write-Host "  removed $BackupName\" }
            Remove-It $manifestPath $ManifestName
        }
    } else {
        Write-Host ''
        Write-Host "kept $BackupName\ and $ManifestName (-KeepBackups)"
    }

    # ---- directories we created, deepest first, only when empty
    Write-Host ''
    Write-Host 'directories:'
    $dirs = @($m.createdDirs) | Sort-Object -Property Length -Descending
    foreach ($d in $dirs) {
        $full = Join-Path $GameDir ([string]$d)
        if (-not (Test-Path -LiteralPath $full)) { continue }
        $left = @(Get-ChildItem -LiteralPath $full -Force)
        if ($left.Count -eq 0) {
            if ($DryRun) { Write-Host "  would remove empty $d\" }
            else { Remove-Item -LiteralPath $full -Force; Write-Host "  removed empty $d\" }
        } else {
            Write-Host ("  kept {0}\ ({1} item(s) left)" -f $d, $left.Count)
        }
    }
} else {
    # ------------------------------------------------------------------ legacy fallback
    # Only on request: without the manifest the dummies can only be stripped structurally,
    # which is not byte-identical, and doing that to a folder that is already clean would
    # damage it for no reason.
    if (-not $AllowLegacy) {
        Write-Host ''
        Write-Host "no $ManifestName in $GameDir - nothing to replay."
        Write-Host 'Nothing was changed.'
        Write-Host ''
        Write-Host 'There is nothing here to undo unless you installed HideSheathedLeft with a version'
        Write-Host 'that did not write a manifest (1.0.4 or older).  In that case run:'
        Write-Host ''
        Write-Host '  powershell -ExecutionPolicy Bypass -File restore.ps1 -AllowLegacy'
        Write-Host ''
        Write-Host 'which strips dummy 382/383 out of chr\*.chrbnd.dcx structurally.  That is NOT'
        Write-Host 'byte-identical (the bundle is re-serialised and the DCX re-compressed) - for exact'
        Write-Host 'bytes delete the loose chr\*.chrbnd.dcx files and re-extract them from the game'
        Write-Host 'archives (UXM).'
        exit 1
    }
    Write-Host ''
    Write-Host "no $ManifestName - falling back to the structural uninstall (installation from 1.0.4 or older)"

    Write-Host ''
    Write-Host 'character models:'
    if (-not (Test-Path -LiteralPath $tool)) {
        Write-Host "  WARNING: $tool not found - the dummies 382/383 stay in chr\*.chrbnd.dcx"
    } elseif (-not (Test-Path -LiteralPath $chrDir)) {
        Write-Host '  no chr folder in the game dir - nothing to strip'
    } else {
        $stripArgs = @('stripdir', $chrDir, 'INPLACE', '382,383', 'chrbnd')
        if ($DryRun) { $stripArgs += 'DRYRUN' }
        $eap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'   # a native tool printing to stderr must not abort the script
        $lines = & $tool @stripArgs 2>&1
        $code  = $LASTEXITCODE
        $ErrorActionPreference = $eap
        foreach ($l in $lines) { Write-Host ("  " + $l) }
        if ($code -ne 0) { [void]$problems.Add("stripdir exited with $code") }
        Write-Host '  note: a structural strip is not byte-identical (the bundle is re-serialised and the'
        Write-Host '        DCX re-compressed) - only a .hsleft-backup\ copy or a fresh unpack is.'
    }

    $model    = Join-Path $chrDir 'c0000.chrbnd.dcx'
    $modelBak = "$model.vanilla-backup"
    if (Test-Path -LiteralPath $modelBak) {
        if ($DryRun) {
            Write-Host '  would restore chr\c0000.chrbnd.dcx from its vanilla-backup'
        } else {
            Copy-Item -LiteralPath $modelBak -Destination $model -Force
            Write-Host '  restored chr\c0000.chrbnd.dcx from its vanilla-backup (byte-exact original)'
        }
    }

    Write-Host ''
    Write-Host 'mod files:'
    foreach ($f in 'HideSheathedLeft.dll', 'HideSheathedLeft.ini', 'HideSheathedLeft.log', 'xinput1_3_proxy.log') {
        Remove-It (Join-Path $GameDir $f) $f
    }

    Write-Host ''
    Write-Host 'loader shell:'
    Remove-It (Join-Path $GameDir 'xinput1_3.dll') 'xinput1_3.dll (loader shell)'
    $displaced = @('xinput1_3.dll.dkp-off', 'xinput1_3.dll.foreign-backup', 'xinput1_3.dll.vanilla-backup')
    $put = $false
    foreach ($name in $displaced) {
        $p = Join-Path $GameDir $name
        if (-not $put -and (Test-Path -LiteralPath $p)) {
            if ($DryRun) { Write-Host ("  would rename {0} back to xinput1_3.dll" -f $name) }
            else { Rename-Item -LiteralPath $p -NewName 'xinput1_3.dll'; Write-Host ("  renamed {0} back to xinput1_3.dll" -f $name) }
            $put = $true
        }
    }
    if (-not $put) { Write-Host '  no displaced xinput1_3.dll found - nothing to put back' }

    if (-not $KeepBackups -and $modelBak -and -not $DryRun -and (Test-Path -LiteralPath $modelBak)) {
        Remove-Item -LiteralPath $modelBak -Force
        Write-Host '  removed chr\c0000.chrbnd.dcx.vanilla-backup'
    }
}

# ---------------------------------------------------------------------- proof, not prose
Write-Host ''
Write-Host 'verification:'
if ($DryRun) {
    Write-Host '  dry run - nothing was changed, nothing to verify'
} elseif (-not (Test-Path -LiteralPath $chrDir)) {
    Write-Host '  no chr folder - nothing to verify'
} elseif (-not (Test-Path -LiteralPath $tool)) {
    Write-Host "  tools\ds3tae.exe not found - run: ds3tae.exe verify `"$chrDir`" chrbnd 382,383"
} else {
    $eap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $lines = & $tool verify $chrDir 'chrbnd' '382,383' 2>&1
    $code  = $LASTEXITCODE
    $ErrorActionPreference = $eap
    foreach ($l in $lines) { Write-Host ("  " + $l) }
    # The HIT list is information: a model that already carried 382/383 before this install comes
    # back carrying them, and that IS the pre-install state.  Only an inconclusive scan is a problem.
    if ($code -ne 0) { [void]$problems.Add('ds3tae verify could not read some character model(s)') }
}

Write-Host ''
if ($problems.Count -gt 0) {
    Write-Host 'Restore finished WITH PROBLEMS:'
    foreach ($p in $problems) { Write-Host "  - $p" }
    exit 1
}
if ($DryRun) { Write-Host 'Dry run only - nothing was changed.' } else { Write-Host 'Restore finished: the game folder is back to its pre-install state.' }
exit 0
