param(
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$Owner = 'xiangchi7',
    [string]$Repo = 'HideSheathedLeft',
    [string]$Tag = 'v1.0.1',
    [string]$Asset = 'D:\Desktop\HideSheathedLeft-1.0.1-full.zip'
)
$ErrorActionPreference = 'Stop'

function Req {
    param([string]$Method, [string]$Uri)
    $r = [System.Net.HttpWebRequest]::Create($Uri)
    $r.Method = $Method
    $r.Headers.Add('Authorization', "Bearer $Token")
    $r.UserAgent = 'dsh'
    $r.Accept = 'application/vnd.github+json'
    try { $resp = $r.GetResponse() } catch [System.Net.WebException] { $resp = $_.Exception.Response }
    $code = if ($resp) { [int]$resp.StatusCode } else { -1 }
    $text = ''
    if ($resp) { $sr = New-Object IO.StreamReader($resp.GetResponseStream(), [System.Text.Encoding]::UTF8); $text = $sr.ReadToEnd(); $sr.Close() }
    return [pscustomobject]@{ code = $code; text = $text }
}

$rel = (Req GET "https://api.github.com/repos/$Owner/$Repo/releases/tags/$Tag").text | ConvertFrom-Json
$name = Split-Path -Leaf $Asset
foreach ($a in ((Req GET "https://api.github.com/repos/$Owner/$Repo/releases/$($rel.id)/assets").text | ConvertFrom-Json)) {
    if ($a.name -eq $name) {
        $d = Req DELETE "https://api.github.com/repos/$Owner/$Repo/releases/assets/$($a.id)"
        Write-Host "deleted old asset $($a.name) -> HTTP $($d.code)"
    }
}

$bytes = [System.IO.File]::ReadAllBytes($Asset)
$r = [System.Net.HttpWebRequest]::Create("https://uploads.github.com/repos/$Owner/$Repo/releases/$($rel.id)/assets?name=$name")
$r.Method = 'POST'
$r.Headers.Add('Authorization', "Bearer $Token")
$r.UserAgent = 'dsh'
$r.ContentType = 'application/zip'
$r.ContentLength = $bytes.Length
$r.ServicePoint.Expect100Continue = $false
$r.Timeout = 600000
$s = $r.GetRequestStream(); $s.Write($bytes, 0, $bytes.Length); $s.Close()
try { $resp = $r.GetResponse() } catch [System.Net.WebException] { $resp = $_.Exception.Response }
$code = if ($resp) { [int]$resp.StatusCode } else { -1 }
$text = ''
if ($resp) { $sr = New-Object IO.StreamReader($resp.GetResponseStream(), [System.Text.Encoding]::UTF8); $text = $sr.ReadToEnd(); $sr.Close() }
if ($code -in 200, 201) {
    $a = $text | ConvertFrom-Json
    Write-Host "uploaded $($a.name)  $([math]::Round($a.size/1MB,1)) MB  sha256-of-file=$((Get-FileHash $Asset -Algorithm SHA256).Hash.Substring(0,16))"
} else {
    Write-Host "UPLOAD FAILED ($code): $text"
    exit 1
}

$rel2 = (Req GET "https://api.github.com/repos/$Owner/$Repo/releases/tags/$Tag").text | ConvertFrom-Json
Write-Host "release assets now:"
foreach ($a in $rel2.assets) { Write-Host ("  {0,-34} {1,8} KB" -f $a.name, [math]::Round($a.size/1KB)) }
