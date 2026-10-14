# Give EVERY character model the parking dummies (382 / 383) that HideSheathedLeft
# points the parameter table at.  Run this once after installing the mod, and again
# after any mod that replaces files in the game's chr\ folder.
#
#   powershell -ExecutionPolicy Bypass -File patch-character-models.ps1 -DryRun
#   powershell -ExecutionPolicy Bypass -File patch-character-models.ps1
#
# The tool appends two dummies at (0, -1000, 0) to each chr\*.chrbnd.dcx and verifies
# per file that the bone list, materials, meshes and buffer layouts are unchanged and
# that no original dummy entry moved; a file that fails the check is left untouched.
# Files that already have 382/383 are skipped, so running it twice is harmless.

param(
    [switch]$DryRun,
    [string]$GameDir = 'D:\Steam\steamapps\common\DARK SOULS III\Game'
)

$ErrorActionPreference = 'Stop'
$tool = Join-Path $PSScriptRoot 'ds3tae.exe'
if (-not (Test-Path -LiteralPath $tool)) { throw "missing patcher tool: $tool" }

$chr = Join-Path $GameDir 'chr'
if (-not (Test-Path -LiteralPath $chr)) { throw "no chr folder at $chr" }

$running = Get-Process -Name 'DarkSoulsIII' -ErrorAction SilentlyContinue
if ($running) { throw "DarkSoulsIII.exe is running (pid $($running.Id)) - close the game first" }

Write-Host "patching character models under $chr"
if ($DryRun) {
    & $tool parkdir $chr INPLACE "382,383" "0,-1000,0" 0 "chrbnd" DRYRUN
} else {
    & $tool parkdir $chr INPLACE "382,383" "0,-1000,0" 0 "chrbnd"
}
Write-Host ''
Write-Host 'done. Every chr\*.chrbnd.dcx now carries dummy 382/383 at (0,-1000,0).'
Write-Host 'To undo: delete the loose chr\*.chrbnd.dcx files (the game then uses the packed originals again).'
