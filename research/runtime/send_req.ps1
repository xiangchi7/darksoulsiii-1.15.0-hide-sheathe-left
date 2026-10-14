# Send one request to the privileged ds3 agent and print its reply.
# Usage: pwsh -File send_req.ps1 -Json '{"cmd":"probe"}'
param(
  [Parameter(Mandatory = $true)][string]$Json,
  [int]$TimeoutSec = 300
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$ipc = Join-Path $root 'ipc'
$req = Join-Path $ipc 'req.json'
$res = Join-Path $ipc 'res.json'
$tmp = Join-Path $ipc 'req.tmp'

if (Test-Path -LiteralPath $res) { Remove-Item -LiteralPath $res -Force }
if (Test-Path -LiteralPath $req) { Remove-Item -LiteralPath $req -Force }

# UTF-8 WITHOUT BOM (Set-Content -Encoding utf8 adds a BOM on Windows PowerShell 5.1)
$enc = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($tmp, $Json, $enc)
Move-Item -LiteralPath $tmp -Destination $req -Force

$deadline = (Get-Date).AddSeconds($TimeoutSec)
while ((Get-Date) -lt $deadline) {
  if (Test-Path -LiteralPath $res) {
    Start-Sleep -Milliseconds 120
    Get-Content -LiteralPath $res -Raw
    exit 0
  }
  Start-Sleep -Milliseconds 400
}
Write-Output '{"ok":false,"error":"timeout waiting for agent"}'
exit 1
