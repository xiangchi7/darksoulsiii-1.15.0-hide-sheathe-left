# Build HideSheathedLeft (MSVC x64).
#
#   pwsh -ExecutionPolicy Bypass -File build.ps1                 # -> dist\
#   pwsh -ExecutionPolicy Bypass -File build.ps1 -Install        # + copy to the game
#
# The build uses the Visual Studio Build Tools that are already installed.

param(
  [string]$OutDir  = '',
  [string]$GameDir = 'D:\Steam\steamapps\common\DARK SOULS III\Game',
  [switch]$Install
)

$ErrorActionPreference = 'Stop'

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) { throw "vswhere.exe not found: $vswhere" }
$vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'MSVC x64 build tools not found' }
$vcvars = Join-Path $vs 'VC\Auxiliary\Build\vcvars64.bat'
if (-not (Test-Path -LiteralPath $vcvars)) { throw "vcvars64.bat not found: $vcvars" }

# This script lives in src\, so the sources are next to it -- do not join another 'src'
# (that produced "...\src\src\HideSheathedLeft.cpp" and every build failed with C1083).
$src = $PSScriptRoot
$repo = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $repo 'tools\patch-character-models.ps1'))) { $repo = $PSScriptRoot }
if (-not $OutDir) { $OutDir = Join-Path $repo 'dist' }
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }

$bat = Join-Path $env:TEMP 'hsl_build.bat'
$lines = @(
  '@echo off',
  "call `"$vcvars`" >nul",
  "cl /nologo /O2 /EHsc /std:c++17 /DNDEBUG /LD `"$src\HideSheathedLeft.cpp`" /Fe:`"$OutDir\HideSheathedLeft.dll`" /Fo:`"$OutDir\HideSheathedLeft.obj`" /link /INCREMENTAL:NO",
  'if errorlevel 1 exit /b 1',
  "cl /nologo /O2 /EHsc /std:c++17 /DNDEBUG /LD `"$src\xinput1_3_proxy.cpp`" /Fe:`"$OutDir\xinput1_3.dll`" /Fo:`"$OutDir\xinput1_3_proxy.obj`" /link /DEF:`"$src\xinput1_3_proxy.def`" /INCREMENTAL:NO",
  'exit /b %errorlevel%'
)
Set-Content -LiteralPath $bat -Value $lines -Encoding ascii
& cmd /c $bat
if ($LASTEXITCODE -ne 0) { throw "build failed (exit $LASTEXITCODE)" }

Copy-Item -LiteralPath (Join-Path $repo 'HideSheathedLeft.ini') -Destination $OutDir -Force

Get-ChildItem -LiteralPath $OutDir -Filter '*.dll' | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
Write-Host "built -> $OutDir"

if ($Install) {
  if (-not (Test-Path -LiteralPath $GameDir)) { throw "game dir not found: $GameDir" }
  Copy-Item -LiteralPath (Join-Path $OutDir 'HideSheathedLeft.dll') -Destination $GameDir -Force
  Copy-Item -LiteralPath (Join-Path $OutDir 'HideSheathedLeft.ini') -Destination $GameDir -Force
  $proxy = Join-Path $GameDir 'xinput1_3.dll'
  if (Test-Path -LiteralPath $proxy) {
    Write-Host 'NOTE: an existing xinput1_3.dll is present; renaming it to xinput1_3.dll.dkp-off'
    if (Test-Path -LiteralPath "$proxy.dkp-off") { Remove-Item -LiteralPath "$proxy.dkp-off" -Force }
    Rename-Item -LiteralPath $proxy -NewName 'xinput1_3.dll.dkp-off'
  }
  Copy-Item -LiteralPath (Join-Path $OutDir 'xinput1_3.dll') -Destination $GameDir -Force
  Write-Host "installed into $GameDir"
  Write-Host 'uninstall: delete xinput1_3.dll, HideSheathedLeft.dll and HideSheathedLeft.ini'
}
