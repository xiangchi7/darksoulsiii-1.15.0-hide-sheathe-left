# Give EVERY character model the parking dummies (382 / 383) that HideSheathedLeft
# points the parameter table at.  install.ps1 calls this automatically; run it by hand
# after any mod that replaces files in the game's chr\ folder.
#
#   powershell -ExecutionPolicy Bypass -File patch-character-models.ps1 -DryRun
#   powershell -ExecutionPolicy Bypass -File patch-character-models.ps1
#   powershell -ExecutionPolicy Bypass -File patch-character-models.ps1 -GameDir "F:\...\Game"
#   powershell -ExecutionPolicy Bypass -File patch-character-models.ps1 -Only c0000.chrbnd.dcx,c1000.chrbnd.dcx
#
# The tool appends two dummies at (0, -1000, 0) to each chr\*.chrbnd.dcx and verifies
# per file that the bone list, materials, meshes and buffer layouts are unchanged and
# that no original dummy entry moved; a file that fails the check is left untouched.
# Files that already have 382/383 are skipped, so running it twice is harmless.
#
# -Only limits the run to those file names.  install.ps1 uses it so a re-install never
# touches a model it has already patched (and already has the original of).

param(
    [switch]$DryRun,
    [string]$GameDir = 'D:\Steam\steamapps\common\DARK SOULS III\Game',
    [string]$Only = ''
)

$ErrorActionPreference = 'Stop'
$tool = Join-Path $PSScriptRoot 'ds3tae.exe'
if (-not (Test-Path -LiteralPath $tool)) { throw "missing patcher tool: $tool" }

$chr = Join-Path $GameDir 'chr'
if (-not (Test-Path -LiteralPath $chr)) {
    Write-Host "no chr folder at $chr"
    Write-Host 'Nothing to patch: this game has no loose character models.  HideSheathedLeft then works'
    Write-Host 'with the packed models as they are - the parking dummies only matter for loose files.'
    exit 0
}

$running = Get-Process -Name 'DarkSoulsIII' -ErrorAction SilentlyContinue
if ($running) { throw "DarkSoulsIII.exe is running (pid $($running.Id)) - close the game first" }

# ds3tae parkdir has no per-file argument, so a -Only run patches a private folder that holds
# just those files.  That folder MUST live on the same volume as chr\: a hardlink across drives
# throws, and a silent copy fallback then patches a temp copy that is deleted again -- which is
# exactly how 1.0.5 shipped unpatched models and the 1.0.0 flicker came back.  Anything that
# cannot be hardlinked is copied back over the original after the run.
$scanRoot = $chr
$links = $null
$copied = New-Object System.Collections.ArrayList
if ($Only) {
    $names = @($Only.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $links = Join-Path $chr ('.hsleft-park-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $links -Force | Out-Null
    foreach ($n in $names) {
        $src = Join-Path $chr $n
        $dst = Join-Path $links $n
        if (-not (Test-Path -LiteralPath $src)) { continue }
        try { New-Item -ItemType HardLink -Path $dst -Target $src -ErrorAction Stop | Out-Null }
        catch {
            Copy-Item -LiteralPath $src -Destination $dst -Force
            [void]$copied.Add($n)
        }
    }
    $scanRoot = $links
    Write-Host ("patching {0} selected model(s)" -f $names.Count)
}

try {
    Write-Host "patching character models under $chr"
    if ($DryRun) {
        & $tool parkdir $scanRoot INPLACE "382,383" "0,-1000,0" 0 "chrbnd" DRYRUN
    } else {
        & $tool parkdir $scanRoot INPLACE "382,383" "0,-1000,0" 0 "chrbnd"
    }
    $code = $LASTEXITCODE

    if (-not $DryRun -and $copied.Count -gt 0) {
        foreach ($n in $copied) {
            $staged = Join-Path $links $n
            $orig = Join-Path $chr $n
            if (-not (Test-Path -LiteralPath $staged)) { continue }
            $a = (Get-FileHash -LiteralPath $staged -Algorithm SHA256).Hash
            $b = (Get-FileHash -LiteralPath $orig -Algorithm SHA256).Hash
            if ($a -ne $b) {
                Copy-Item -LiteralPath $staged -Destination $orig -Force
                Write-Host ("  copied {0} back (no hardlink possible on this volume)" -f $n)
            }
        }
    }
} finally {
    if ($links -and (Test-Path -LiteralPath $links)) { Remove-Item -LiteralPath $links -Recurse -Force -ErrorAction SilentlyContinue }
}
if ($code -ne 0) { Write-Host "WARNING: parkdir exited with $code - check the lines above" }

# Never claim success without checking: every model that has an FLVER must now carry 382/383.
# A model without them is exactly what produces the black triangles / full-screen flicker.
if (-not $DryRun) {
    $vtext = (& $tool verify $chr 'chrbnd' '382,383' 2>&1 | Out-String)
    $verified = 0
    $expected = 0
    if ($vtext -match 'scanned \d+ file\(s\), (\d+) with an FLVER') { $expected = [int]$Matches[1] }
    if ($vtext -match 'files still carrying 382,383: (\d+)') { $verified = [int]$Matches[1] }
    Write-Host ''
    Write-Host ("verification: {0} of {1} character model(s) carry dummy 382/383" -f $verified, $expected)
    if ($expected -gt 0 -and $verified -lt $expected) {
        Write-Host ''
        Write-Host ("ERROR: {0} model(s) still carry no parking dummy - the sheathed item would flash" -f ($expected - $verified))
        Write-Host '       (black triangles / full-screen flicker).  Re-run this script; if it keeps'
        Write-Host '       failing, make sure the game folder is writable and no antivirus blocks the'
        Write-Host '       files.  restore.ps1 puts every model back to its pre-install bytes.'
        exit 1
    }
}

Write-Host ''
Write-Host 'done. Every chr\*.chrbnd.dcx named above now carries dummy 382/383 at (0,-1000,0).'
Write-Host 'install.ps1 keeps a byte-exact copy of every model before patching it, so restore.ps1 can'
Write-Host 'undo this exactly.  If you patched by hand, your own backup is what makes that possible.'
exit 0
