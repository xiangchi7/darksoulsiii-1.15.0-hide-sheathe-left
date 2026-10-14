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

# ds3tae parkdir has no per-file argument, so a -Only run gets a private folder with just
# those files hardlinked into it: no copying, and the tool edits are still in place.
$scanRoot = $chr
$links = $null
if ($Only) {
    $names = @($Only.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $links = Join-Path ([System.IO.Path]::GetTempPath()) ("hsleft-park-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $links | Out-Null
    foreach ($n in $names) {
        $src = Join-Path $chr $n
        if (Test-Path -LiteralPath $src) {
            try { New-Item -ItemType HardLink -Path (Join-Path $links $n) -Target $src -ErrorAction Stop | Out-Null }
            catch { Copy-Item -LiteralPath $src -Destination (Join-Path $links $n) -Force }
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
} finally {
    if ($links -and (Test-Path -LiteralPath $links)) { Remove-Item -LiteralPath $links -Recurse -Force -ErrorAction SilentlyContinue }
}
if ($code -ne 0) { Write-Host "WARNING: parkdir exited with $code - check the lines above" }

Write-Host ''
Write-Host 'done. Every chr\*.chrbnd.dcx named above now carries dummy 382/383 at (0,-1000,0).'
Write-Host 'install.ps1 keeps a byte-exact copy of every model before patching it, so restore.ps1 can'
Write-Host 'undo this exactly.  If you patched by hand, your own backup is what makes that possible.'
