# Build the two release zips so their contents ARE the repository contents.
#
#   powershell -ExecutionPolicy Bypass -File make-release-zips.ps1 -Version 1.0.5
#   powershell -ExecutionPolicy Bypass -File make-release-zips.ps1 -Version 1.0.5 -FullSource <dir>
#
# Two traps this script exists to avoid, both hit for real during the 1.0.5 release:
#
#  1. .NET 5+'s ZipFile.CreateFromDirectory writes Windows BACKSLASHES into entry names when run on
#     Windows.  The archive is then a zip-spec violation and standard unzip on Linux/macOS cannot
#     create the directories.  Entries are created by hand here, always with '/'.
#  2. Staging directories go stale: the 1.0.5 lean zip was built from a copy that still held the
#     previous CHANGELOG.md.  So every file that the repository has is read straight out of git
#     (`git cat-file blob`), which also means the zip matches a `git clone` byte for byte -- not the
#     CRLF-normalised working tree.
#
# The lean zip is a complete mirror of the repository (sources, tools, tests, docs, research).
# The full zip is the install package: the lean zip's user-facing parts plus files\ (payload),
# evidence\ and reference\.  Anything the full package needs that is not in the repository
# (screenshots, the pre-patched player model, the parameter dumps) is copied from -FullSource,
# which defaults to the previous -full package.

param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$RepoDir    = 'C:\Users\35866\Documents\deepseek-harness\default-workspace\HideSheathedLeft-release',
    [string]$OutDir     = '',
    [string]$FullSource = ''
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

if (-not (Test-Path -LiteralPath (Join-Path $RepoDir '.git'))) { throw "not a git repository: $RepoDir" }
if (-not $OutDir) { $OutDir = Join-Path (Split-Path -Parent $RepoDir) "publish-$Version" }
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

function Get-RepoPaths {
    $out = & git -C $RepoDir ls-tree -r --name-only HEAD
    if ($LASTEXITCODE -ne 0) { throw 'git ls-tree failed' }
    return @($out | Where-Object { $_ })
}

function Get-RepoBytes([string]$path) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'git'
    $psi.Arguments = 'cat-file blob ' + ('HEAD:' + $path)
    $psi.WorkingDirectory = $RepoDir
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $p = [System.Diagnostics.Process]::Start($psi)
    $ms = New-Object System.IO.MemoryStream
    $p.StandardOutput.BaseStream.CopyTo($ms)
    $err = $p.StandardError.ReadToEnd()
    $p.WaitForExit()
    if ($p.ExitCode -ne 0) { throw "git cat-file blob HEAD:$path failed: $err" }
    return $ms.ToArray()
}

function New-Zip([string]$zipPath, $items) {
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    $fs = [System.IO.File]::Open($zipPath, [System.IO.FileMode]::CreateNew)
    $zip = New-Object System.IO.Compression.ZipArchive($fs, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($it in $items) {
            $name = $it.Name.Replace('\', '/')
            $entry = $zip.CreateEntry($name, [System.IO.Compression.CompressionLevel]::Optimal)
            $es = $entry.Open()
            $es.Write($it.Bytes, 0, $it.Bytes.Length)
            $es.Close()
        }
    } finally { $zip.Dispose(); $fs.Close() }
}

# ---------------------------------------------------------------- lean = the repository
Write-Host "== lean zip = the repository at HEAD =="
$repoPaths = Get-RepoPaths
$leanItems = New-Object System.Collections.ArrayList
foreach ($p in $repoPaths) { [void]$leanItems.Add([pscustomobject]@{ Name = $p; Bytes = (Get-RepoBytes $p) }) }
$leanZip = Join-Path $OutDir "HideSheathedLeft-$Version.zip"
New-Zip $leanZip $leanItems
Write-Host ("  {0}  {1} file(s)  {2:N0} bytes" -f (Split-Path -Leaf $leanZip), $leanItems.Count, (Get-Item $leanZip).Length)

# ---------------------------------------------------------------- full = lean + payload/evidence/reference
Write-Host '== full zip = install package =='if (-not $FullSource) {
    $prev = Get-ChildItem (Split-Path -Parent $RepoDir) -Directory -Filter 'publish-*' -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ne "publish-$Version" } | Sort-Object Name -Descending
    foreach ($c in $prev) {
        $f = Get-ChildItem $c.FullName -Directory -Filter '*-full' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($f -and (Test-Path (Join-Path $f.FullName 'evidence'))) { $FullSource = $f.FullName; break }
    }
}
if (-not $FullSource -or -not (Test-Path -LiteralPath $FullSource)) {
    throw 'no -FullSource and no previous *-full package found for the evidence/reference assets'
}
Write-Host "  extra assets from: $FullSource"

# Which repository paths belong in the install package.  The payload lives in files\ (built
# explicitly below), so the repository copies of the mod files must NOT also sit in the root of the
# full package: 1.0.5 shipped them twice (root + files\) and nothing installs from the root copy.
$skip = @('src/', 'validator/', 'research/', 'tools/maintainer/', '.gitignore',
          'HideSheathedLeft.dll', 'HideSheathedLeft.ini', 'xinput1_3.dll')
$fullItems = New-Object System.Collections.ArrayList
foreach ($it in $leanItems) { if (-not ($skip | Where-Object { $it.Name.StartsWith($_) })) { [void]$fullItems.Add($it) } }
# payload: files\ comes from the repository copies of the mod files, plus the pre-patched model
foreach ($f in 'HideSheathedLeft.dll', 'HideSheathedLeft.ini', 'xinput1_3.dll') {
    [void]$fullItems.Add([pscustomobject]@{ Name = "files/$f"; Bytes = (Get-RepoBytes $f) })
}
foreach ($extra in 'files\c0000.chrbnd.dcx') {
    $src = Join-Path $FullSource $extra
    if (-not (Test-Path -LiteralPath $src)) { throw "missing extra asset: $src" }
    [void]$fullItems.Add([pscustomobject]@{ Name = ($extra -replace '\\', '/'); Bytes = [System.IO.File]::ReadAllBytes($src) })
}
foreach ($dir in 'evidence', 'reference') {
    $srcDir = Join-Path $FullSource $dir
    if (-not (Test-Path -LiteralPath $srcDir)) { throw "missing extra asset dir: $srcDir" }
    foreach ($f in Get-ChildItem -LiteralPath $srcDir -Recurse -File | Sort-Object FullName) {
        $rel = $f.FullName.Substring($FullSource.Length + 1)
        [void]$fullItems.Add([pscustomobject]@{ Name = ($rel -replace '\\', '/'); Bytes = [System.IO.File]::ReadAllBytes($f.FullName) })
    }
}
$fullZip = Join-Path $OutDir "HideSheathedLeft-$Version-full.zip"
New-Zip $fullZip $fullItems
Write-Host ("  {0}  {1} file(s)  {2:N0} bytes" -f (Split-Path -Leaf $fullZip), $fullItems.Count, (Get-Item $fullZip).Length)

# ---------------------------------------------------------------- CHECKSUMS.txt
# Order matters: the full zip is final at this point, so its hash is real, and the file itself is
# written to CHECKSUMS-$Version.txt rather than into the archive.  Embedding it in the archive
# would change the hash it describes (the stale copy of this file shipped twice for that reason).
$sumPath = Join-Path $OutDir "CHECKSUMS-$Version.txt"
$leanHash = (Get-FileHash $leanZip -Algorithm SHA256).Hash
$fullHash = (Get-FileHash $fullZip -Algorithm SHA256).Hash
$sum = @(
    "HideSheathedLeft $Version - release package",
    ("Built:      {0}" -f (Get-Date).ToString('yyyy-MM-dd HH:mm')),
    "Game:       Dark Souls III, Steam, 1.15.0 (64-bit)",
    ("Repository: https://github.com/xiangchi7/HideSheathedLeft/releases/tag/v$Version"),
    ("Commit:     {0}" -f (& git -C $RepoDir rev-parse HEAD)),
    "",
    "ASSETS",
    ("  HideSheathedLeft-$Version.zip        {0,12:N0} bytes  sha256 {1}" -f (Get-Item $leanZip).Length, $leanHash),
    ("  HideSheathedLeft-$Version-full.zip   {0,12:N0} bytes  sha256 {1}" -f (Get-Item $fullZip).Length, $fullHash),
    "",
    "WHAT IS IN WHICH ZIP",
    ("  HideSheathedLeft-$Version.zip        repository layout: the whole repository at the tag"),
    "                                       (sources, tools\, tests\, docs\, research\)",
    ("  HideSheathedLeft-$Version-full.zip   install package: no sources/research, plus files\ (payload),"),
    "                                       evidence\ (screenshots) and reference\ (param dumps)",
    "",
    "INSTALL",
    "  Close the game, then run install.cmd (or install.ps1) in the unpacked package.",
    "  install.ps1 copies every file it is about to overwrite, byte for byte, into",
    "  <game>\.hsleft-backup\ and records it in <game>\.hsleft-manifest.json.",
    "",
    "UNINSTALL",
    "  Run restore.cmd (or restore.ps1).  It replays the manifest: originals come back byte-exact,",
    "  installer-created files (and an installer-created empty chr\) are removed, and",
    "  tools\ds3tae.exe verify proves no character model still carries dummy 382/383.",
    "  Installations from 1.0.4 or older have no manifest: restore.ps1 then changes nothing unless",
    "  you pass -AllowLegacy (structural strip; NOT byte-identical).",
    "",
    "  1.0.4 AND EARLIER COULD NOT UNINSTALL AT ALL: their tools\ds3tae.exe predates the",
    "  stripdir/parkdir/scanid sub-commands, so it printed a usage line and exited 2, and their",
    "  restore.ps1 reported success while leaving every character model patched.",
    "",
    "PERFORMANCE",
    "  Parameter writes are cheap and only happen when a value differs.  The expensive work is the",
    "  address-space scan that locates the parameter table: once at start-up, and again only when",
    "  the held addresses go stale (Rescan=1, the default).  Set Rescan=0 in HideSheathedLeft.ini to",
    "  stop those extra passes; HideSheathedLeft.log prints what each pass cost.",
    "  1.0.1 read non-resident pages as well, which inflated the game's working set by ~4 GB",
    "  (measured 6007 MB vs vanilla 1634 MB); 1.0.2 and later are resident-only.",
    "",
    "VERIFICATION (run from the unpacked package)",
    "  powershell -ExecutionPolicy Bypass -File tests\roundtrip.ps1",
    "      installs into a scratch game folder, restores, and fails unless every pre-existing file",
    "      is byte-identical and nothing is left over",
    "  tools\ds3tae.exe verify ""<game>\chr"" ""chrbnd"" ""382,383""",
    "      lists every model that still carries the parking dummies",
    "  powershell -ExecutionPolicy Bypass -File tools\maintainer\make-release-zips.ps1 -Version $Version",
    "      rebuilds both zips straight from git; the lean zip is verified entry by entry against HEAD",
    ""
)
[System.IO.File]::WriteAllLines($sumPath, $sum, (New-Object System.Text.UTF8Encoding($false)))
Write-Host ("  {0}  (generated)" -f (Split-Path -Leaf $sumPath))

# ---------------------------------------------------------------- report
Write-Host ''
Write-Host '== verification =='
$ok = $true
foreach ($z in @($leanZip, $fullZip)) {
    $zz = [System.IO.Compression.ZipFile]::OpenRead($z)
    $names = @($zz.Entries | Where-Object { $_.Name -ne '' } | ForEach-Object { $_.FullName })
    $back = @($names | Where-Object { $_ -like '*\*' }).Count
    $zz.Dispose()
    Write-Host ("  {0,-36} entries={1,4}  backslashes={2}" -f (Split-Path -Leaf $z), $names.Count, $back)
    if ($back -ne 0) { $ok = $false }
}
# every lean entry must be byte-identical to its git blob
$zz = [System.IO.Compression.ZipFile]::OpenRead($leanZip)
$bad = 0
foreach ($e in $zz.Entries) {
    if ($e.Name -eq '') { continue }
    $s = $e.Open(); $ms = New-Object System.IO.MemoryStream; $s.CopyTo($ms); $s.Close()
    $inZip = $ms.ToArray()
    $inRepo = Get-RepoBytes $e.FullName
    if ([Convert]::ToBase64String($inZip) -ne [Convert]::ToBase64String($inRepo)) { Write-Host "  DIFFERS from HEAD: $($e.FullName)"; $bad++ }
}
$zz.Dispose()
Write-Host "  lean entries that differ from git HEAD: $bad"
if ($bad -ne 0) { $ok = $false }

Write-Host ''
Get-FileHash $leanZip, $fullZip -Algorithm SHA256 | ForEach-Object { Write-Host ("  {0}  {1}" -f $_.Hash, (Split-Path -Leaf $_.Path)) }
Write-Host ''
if ($ok) { Write-Host 'OK: both zips are correct.'; exit 0 }
Write-Host 'PROBLEM: see the lines above.'
exit 1
