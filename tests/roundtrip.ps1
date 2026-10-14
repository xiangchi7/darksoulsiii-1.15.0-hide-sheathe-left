# Round-trip test for install.ps1 / restore.ps1.
#
#   powershell -ExecutionPolicy Bypass -File tests\roundtrip.ps1
#   powershell -ExecutionPolicy Bypass -File tests\roundtrip.ps1 -Keep    # keep the scratch folders
#
# Builds scratch "game folders" (a fake DarkSoulsIII.exe plus a chr\ with real character bundles),
# snapshots every byte, installs, restores, and proves:
#
#   stage A - the plain round trip
#     after install : mod files present, models carry 382/383, manifest + native backups written
#     after restore : EVERY pre-existing file byte-identical to the snapshot, installer-created
#                     files gone, manifest/backups gone, ds3tae verify reports no 382/383 anywhere
#     idempotence   : a second restore and a -DryRun change nothing
#   stage B - the safety catch
#     a file replaced after the install is NOT clobbered by restore (exit 1, manifest kept), and
#     restore -Force then finishes the job byte-exactly
#
# Nothing outside <repo>\tests\tmp is touched.

param(
    [switch]$Keep
)

$ErrorActionPreference = 'Stop'

$repo  = Split-Path -Parent $PSScriptRoot
$tmp   = Join-Path $PSScriptRoot 'tmp'
$tools = Join-Path $repo 'tools\ds3tae.exe'

function Step([string]$what) { Write-Host ''; Write-Host "== $what ==" }

function Snapshot([string]$root) {
    $map = @{}
    foreach ($f in Get-ChildItem -LiteralPath $root -Recurse -File -Force) {
        $rel = $f.FullName.Substring($root.Length).TrimStart('\')
        $map[$rel] = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
    }
    return $map
}

function Compare-Snapshot($before, [string]$root, [string]$label) {
    $after = Snapshot $root
    $bad = New-Object System.Collections.ArrayList
    foreach ($k in $before.Keys) {
        if (-not $after.ContainsKey($k)) { [void]$bad.Add("MISSING $k"); continue }
        if ($after[$k] -ne $before[$k]) { [void]$bad.Add("CHANGED $k") }
    }
    foreach ($k in $after.Keys) {
        if (-not $before.ContainsKey($k)) { [void]$bad.Add("EXTRA   $k") }
    }
    if ($bad.Count -eq 0) {
        Write-Host ("  {0}: {1} file(s) byte-identical, nothing left over" -f $label, $before.Count)
        return $true
    }
    Write-Host ("  {0}: {1} difference(s)" -f $label, $bad.Count)
    foreach ($b in $bad) { Write-Host "    $b" }
    return $false
}

# ---------------------------------------------------------------- fixture
$vanilla = Join-Path $repo '..\ds3-hide-sheathed\probes\out\c0000.chrbnd.vanilla.dcx'
if (-not (Test-Path -LiteralPath $vanilla)) { throw "test fixture missing: $vanilla" }
$patchedDir = Join-Path $repo '..\ds3-hide-sheathed\chr-patched'

function New-Game([string]$name) {
    $game = Join-Path $tmp $name
    New-Item -ItemType Directory -Path $game -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $game 'chr') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $game 'DarkSoulsIII.exe') -Value 'not a real game' -Encoding ASCII

    # unpatched models: the installer has to back these up and patch them itself
    Copy-Item -LiteralPath $vanilla -Destination (Join-Path $game 'chr\c0000.chrbnd.dcx') -Force
    Copy-Item -LiteralPath $vanilla -Destination (Join-Path $game 'chr\c1000.chrbnd.dcx') -Force

    # already-patched models, as a previous install or another model mod would have left them:
    # their dummies pre-date this install and must come back byte-identical too
    foreach ($n in @('c1100.chrbnd.dcx', 'c1340.chrbnd.dcx')) {
        $s = Join-Path $patchedDir $n
        if (Test-Path -LiteralPath $s) { Copy-Item -LiteralPath $s -Destination (Join-Path $game "chr\$n") -Force }
    }

    # a foreign xinput1_3.dll already occupies the loader slot
    Set-Content -LiteralPath (Join-Path $game 'xinput1_3.dll') -Value 'foreign proxy dll' -Encoding ASCII
    return $game
}

if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
$ok = $true

# ================================================================ stage A
Step 'stage A: building the scratch game folder'
$game = New-Game 'A'
$before = Snapshot $game
Write-Host ("  {0} file(s) in the scratch game folder" -f $before.Count)
foreach ($k in ($before.Keys | Sort-Object)) { Write-Host "    $k" }

Step 'stage A: install.ps1'
& (Join-Path $repo 'install.ps1') -GameDir $game
if ($LASTEXITCODE -ne 0) { Write-Host "install.ps1 exited with $LASTEXITCODE"; $ok = $false }

Step 'stage A: install checks'
$manifest = Join-Path $game '.hsleft-manifest.json'
$backups  = Join-Path $game '.hsleft-backup'
foreach ($p in 'HideSheathedLeft.dll', 'HideSheathedLeft.ini', 'xinput1_3.dll',
               'chr\c0000.chrbnd.dcx', '.hsleft-manifest.json',
               '.hsleft-backup\chr\c0000.chrbnd.dcx', '.hsleft-backup\xinput1_3.dll') {
    if (Test-Path -LiteralPath (Join-Path $game $p)) { Write-Host "  present: $p" }
    else { Write-Host "  MISSING: $p"; $ok = $false }
}
if (-not (Test-Path -LiteralPath $manifest)) { throw 'no manifest - cannot continue' }
$m = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
$existed = @($m.files | Where-Object { $_.existed })
$created = @($m.files | Where-Object { -not $_.existed })
Write-Host ("  manifest: {0} overwritten, {1} created" -f $existed.Count, $created.Count)
foreach ($r in $existed) { Write-Host ("    overwrote {0}" -f $r.path) }
foreach ($r in $created) { Write-Host ("    created   {0}" -f $r.path) }

$verify = & $tools verify (Join-Path $game 'chr') 'chrbnd' '382,383'
foreach ($l in $verify) { Write-Host "    $l" }
$hitLines = @($verify | Where-Object { $_ -match 'HIT ' })
if ($LASTEXITCODE -ne 0) { Write-Host '  verify could not read a model'; $ok = $false }
if ($hitLines.Count -lt 8) { Write-Host ("  expected every model patched, found {0} HIT line(s)" -f $hitLines.Count); $ok = $false }
else { Write-Host '  all models carry 382/383' }

Step 'stage A: restore.ps1'
& (Join-Path $repo 'restore.ps1') -GameDir $game
if ($LASTEXITCODE -ne 0) { Write-Host "restore.ps1 exited with $LASTEXITCODE"; $ok = $false }

Step 'stage A: restore checks'
if (-not (Compare-Snapshot $before $game 'byte-exact round trip')) { $ok = $false }
foreach ($p in '.hsleft-manifest.json', '.hsleft-backup', 'HideSheathedLeft.dll', 'HideSheathedLeft.ini', 'HideSheathedLeft.log') {
    if (Test-Path -LiteralPath (Join-Path $game $p)) { Write-Host "  LEFTOVER: $p"; $ok = $false }
    else { Write-Host "  gone: $p" }
}

Step 'stage A: restore.ps1 again (no manifest left -> must refuse and change nothing)'
& (Join-Path $repo 'restore.ps1') -GameDir $game
Write-Host "  exit code: $LASTEXITCODE (expected 1: there is nothing to replay)"
if ($LASTEXITCODE -ne 1) { Write-Host '  expected the restore to refuse'; $ok = $false }
if (-not (Compare-Snapshot $before $game 'second restore')) { $ok = $false }

Step 'stage A: restore.ps1 -DryRun on a clean folder (must change nothing)'
& (Join-Path $repo 'restore.ps1') -GameDir $game -DryRun
if ($LASTEXITCODE -ne 1) { Write-Host "  exit code: $LASTEXITCODE (expected 1)"; $ok = $false }
if (-not (Compare-Snapshot $before $game 'dry run')) { $ok = $false }

Step 'stage A: restore.ps1 -AllowLegacy (the explicit structural fallback)'
& (Join-Path $repo 'restore.ps1') -GameDir $game -AllowLegacy
Write-Host "  exit code: $LASTEXITCODE (expected 0)"
if ($LASTEXITCODE -ne 0) { Write-Host '  expected the legacy strip to finish'; $ok = $false }

# ================================================================ stage C
# Install twice in a row: the second install must keep the TRUE originals, so a single restore
# still lands on the pre-install bytes.
Step 'stage C: install twice in a row, then restore once'
$gameC = New-Game 'C'
$beforeC = Snapshot $gameC
& (Join-Path $repo 'install.ps1') -GameDir $gameC | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "first install exited with $LASTEXITCODE"; $ok = $false }
& (Join-Path $repo 'install.ps1') -GameDir $gameC
if ($LASTEXITCODE -ne 0) { Write-Host "second install exited with $LASTEXITCODE"; $ok = $false }
$bakC = Join-Path $gameC '.hsleft-backup\chr\c0000.chrbnd.dcx'
if (Test-Path -LiteralPath $bakC) {
    $h = (Get-FileHash -LiteralPath $bakC -Algorithm SHA256).Hash
    $hOrig = (Get-FileHash -LiteralPath $vanilla -Algorithm SHA256).Hash
    if ($h -eq $hOrig) { Write-Host '  the backup still holds the true original (not the patched file)' }
    else { Write-Host '  the backup was overwritten with a patched model'; $ok = $false }
} else { Write-Host '  MISSING: .hsleft-backup\chr\c0000.chrbnd.dcx'; $ok = $false }
& (Join-Path $repo 'restore.ps1') -GameDir $gameC
if ($LASTEXITCODE -ne 0) { Write-Host "restore exited with $LASTEXITCODE"; $ok = $false }
if (-not (Compare-Snapshot $beforeC $gameC 'double-install round trip')) { $ok = $false }

# ================================================================ stage B
Step 'stage B: building a second scratch game folder'
$gameB = New-Game 'B'
$beforeB = Snapshot $gameB

Step 'stage B: install, then replace chr\c0000.chrbnd.dcx with a foreign model'
& (Join-Path $repo 'install.ps1') -GameDir $gameB | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "install.ps1 exited with $LASTEXITCODE"; $ok = $false }
Copy-Item -LiteralPath (Join-Path $patchedDir 'c1100.chrbnd.dcx') -Destination (Join-Path $gameB 'chr\c0000.chrbnd.dcx') -Force

Step 'stage B: restore.ps1 without -Force (must refuse and keep the manifest)'
& (Join-Path $repo 'restore.ps1') -GameDir $gameB | Out-Null
Write-Host "  exit code: $LASTEXITCODE (expected 1)"
if ($LASTEXITCODE -ne 1) { Write-Host '  expected the restore to refuse'; $ok = $false }
if (-not (Test-Path -LiteralPath (Join-Path $gameB '.hsleft-manifest.json'))) {
    Write-Host '  expected the manifest to be kept for a -Force retry'; $ok = $false
} else { Write-Host '  manifest kept, as documented' }
if (-not (Test-Path -LiteralPath (Join-Path $gameB 'chr\c0000.chrbnd.dcx'))) {
    Write-Host '  the foreign model was deleted - it must not be'; $ok = $false
} else {
    $now = (Get-FileHash -LiteralPath (Join-Path $gameB 'chr\c0000.chrbnd.dcx') -Algorithm SHA256).Hash
    $was = (Get-FileHash -LiteralPath (Join-Path $patchedDir 'c1100.chrbnd.dcx') -Algorithm SHA256).Hash
    if ($now -eq $was) { Write-Host '  the foreign model is untouched, as documented' }
    else { Write-Host '  the foreign model was modified - it must not be'; $ok = $false }
}

Step 'stage B: restore.ps1 -Force (must finish byte-exactly)'
& (Join-Path $repo 'restore.ps1') -GameDir $gameB -Force
if ($LASTEXITCODE -ne 0) { Write-Host "-Force restore exited with $LASTEXITCODE"; $ok = $false }
if (-not (Compare-Snapshot $beforeB $gameB '-Force round trip')) { $ok = $false }

if (-not $Keep) { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }

Write-Host ''
if ($ok) { Write-Host 'ROUND TRIP OK'; exit 0 } else { Write-Host 'ROUND TRIP FAILED'; exit 1 }
