# Measure DarkSoulsIII.exe's memory footprint for one configuration.
#
#   powershell -ExecutionPolicy Bypass -File ram-ab.ps1 -Label 'mod ON'  -LoadCore 1
#   powershell -ExecutionPolicy Bypass -File ram-ab.ps1 -Label 'mod OFF' -LoadCore 0
#   powershell -ExecutionPolicy Bypass -File ram-ab.ps1 -Label 'build X' -Dll x\HideSheathedLeft.dll -Ini x\HideSheathedLeft.ini
#
# -LoadCore switches the *already installed* mod on and off through the ini: 1 loads the mod core,
# 0 leaves the loader shell in place but does not load HideSheathedLeft.dll.  That is the cleanest
# on/off comparison, because nothing else about the installation changes.  -Dll / -Ini install a
# specific build first (used to compare one build against another).
#
# The game is launched, the working set of the largest DarkSoulsIII.exe process is sampled every
# 2 s, and the run is summarised with a steady-state average over the last 30 s.  Results are
# appended to -OutFile as one tab-separated line.  The game is left running at the end.
#
# Reference data: docs\MEMORY-FIX-1.0.2.md.  The companion harness that does not need the game is
# research\runtime\scan-test.cpp.
param(
  [Parameter(Mandatory = $true)][string]$Label,
  [int]$LoadCore = -1,
  [string]$Dll = '',
  [string]$Ini = '',
  [string]$GameDir = 'D:\Steam\steamapps\common\DARK SOULS III\Game',
  [int]$Seconds = 100,
  [string]$OutFile = ''
)

$ErrorActionPreference = 'Stop'

Get-Process DarkSoulsIII -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 4

if ($Dll) { Copy-Item -LiteralPath $Dll -Destination (Join-Path $GameDir 'HideSheathedLeft.dll') -Force }
if ($Ini) { Copy-Item -LiteralPath $Ini -Destination (Join-Path $GameDir 'HideSheathedLeft.ini') -Force }

$iniPath = Join-Path $GameDir 'HideSheathedLeft.ini'
if ($LoadCore -ge 0) {
  # keep the file's own encoding: ASCII stays ASCII, anything else is written back as UTF-8 (no BOM)
  # read as UTF-8 explicitly: Get-Content would decode it with the ANSI codepage and mangle
  # any non-ASCII character in the comments when the file is written back
  $txt = [System.IO.File]::ReadAllText($iniPath, [System.Text.Encoding]::UTF8)
  if ($txt -notmatch '(?m)^LoadCore=\d+') { throw "no LoadCore= line in $iniPath" }
  $txt = [regex]::Replace($txt, '(?m)^LoadCore=\d+', "LoadCore=$LoadCore")
  $bytes = [System.IO.File]::ReadAllBytes($iniPath)
  $nonAscii = $false
  foreach ($b in $bytes) { if ($b -gt 127) { $nonAscii = $true; break } }
  if ($nonAscii) {
    [System.IO.File]::WriteAllText($iniPath, $txt, (New-Object System.Text.UTF8Encoding($false)))
  } else {
    [System.IO.File]::WriteAllText($iniPath, $txt, [System.Text.Encoding]::ASCII)
  }
}

$log = Join-Path $GameDir 'HideSheathedLeft.log'
Remove-Item -LiteralPath $log -ErrorAction SilentlyContinue

$osBefore     = Get-CimInstance Win32_OperatingSystem
$freeBefore   = [int]($osBefore.FreePhysicalMemory / 1KB)
$commitBefore = [int](($osBefore.TotalVirtualMemorySize - $osBefore.FreeVirtualMemory) / 1KB)

$t0 = Get-Date
Start-Process -FilePath (Join-Path $GameDir 'DarkSoulsIII.exe') -WorkingDirectory $GameDir | Out-Null

$rows = @()
for ($i = 1; $i -le [int]($Seconds / 2); ++$i) {
  Start-Sleep -Seconds 2
  $t  = [int]((Get-Date) - $t0).TotalSeconds
  $ps = Get-Process DarkSoulsIII -ErrorAction SilentlyContinue
  if ($ps) {
    $p = $ps | Sort-Object WorkingSet64 -Descending | Select-Object -First 1
    $rows += [pscustomobject]@{
      t = $t; pid = $p.Id
      ws   = [int]($p.WorkingSet64 / 1MB)
      priv = [int]($p.PrivateMemorySize64 / 1MB)
      peak = [int]($p.PeakWorkingSet64 / 1MB)
    }
  } else {
    $rows += [pscustomobject]@{ t = $t; pid = 0; ws = 0; priv = 0; peak = 0 }
  }
}

$osAfter     = Get-CimInstance Win32_OperatingSystem
$freeAfter   = [int]($osAfter.FreePhysicalMemory / 1KB)
$commitAfter = [int](($osAfter.TotalVirtualMemorySize - $osAfter.FreeVirtualMemory) / 1KB)

$steady   = $rows | Where-Object { $_.t -ge ($Seconds - 30) -and $_.ws -gt 0 }
$steadyWs = if ($steady) { [int](($steady | Measure-Object ws   -Average).Average) } else { 0 }
$steadyPr = if ($steady) { [int](($steady | Measure-Object priv -Average).Average) } else { 0 }
$maxWs    = ($rows | Measure-Object ws -Maximum).Maximum

Write-Output "=== $Label (LoadCore=$LoadCore) ==="
foreach ($r in $rows) {
  if ($r.t -le 20 -or ($r.t % 20) -eq 0) {
    Write-Output ("{0,4}s  pid={1,-6} ws={2,5} MB  priv={3,5} MB  peak={4,5} MB" -f $r.t, $r.pid, $r.ws, $r.priv, $r.peak)
  }
}
Write-Output ("steady state (last 30 s avg): ws = {0} MB, private = {1} MB ; max ws = {2} MB" -f $steadyWs, $steadyPr, $maxWs)
Write-Output ("system free RAM {0} -> {1} MB (delta {2}) ; system commit {3} -> {4} MB (delta {5})" -f `
  $freeBefore, $freeAfter, ($freeAfter - $freeBefore), $commitBefore, $commitAfter, ($commitAfter - $commitBefore))
Write-Output "--- mod log ---"
if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log } else { Write-Output '(no log: the mod was not loaded)' }

if ($OutFile) {
  Add-Content -LiteralPath $OutFile -Value ("{0}`tLoadCore={1}`tsteady_ws={2}`tmax_ws={3}`tsteady_priv={4}`tfree_after={5}`tfree_delta={6}" -f `
    $Label, $LoadCore, $steadyWs, $maxWs, $steadyPr, $freeAfter, ($freeAfter - $freeBefore))
}
