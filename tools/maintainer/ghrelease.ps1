param(
    [Parameter(Mandatory=$true)][string]$Token,
    [string]$Owner = 'xiangchi7',
    [string]$Repo = 'HideSheathedLeft',
    [string]$Tag = 'v1.0.1',
    [string]$Asset = 'D:\Desktop\HideSheathedLeft-1.0.1.zip'
)
$ErrorActionPreference = 'Stop'

function Req {
    param([string]$Method, [string]$Uri, [string]$Body = $null)
    $r = [System.Net.HttpWebRequest]::Create($Uri)
    $r.Method = $Method
    $r.Headers.Add('Authorization', "Bearer $Token")
    $r.UserAgent = 'dsh'
    $r.Accept = 'application/vnd.github+json'
    if ($Body) {
        $b = [System.Text.Encoding]::UTF8.GetBytes($Body)
        $r.ContentType = 'application/json; charset=utf-8'
        $r.ContentLength = $b.Length
        $s = $r.GetRequestStream(); $s.Write($b, 0, $b.Length); $s.Close()
    }
    try { $resp = $r.GetResponse() } catch [System.Net.WebException] { $resp = $_.Exception.Response }
    $code = if ($resp) { [int]$resp.StatusCode } else { -1 }
    $text = ''
    if ($resp) { $sr = New-Object IO.StreamReader($resp.GetResponseStream(), [System.Text.Encoding]::UTF8); $text = $sr.ReadToEnd(); $sr.Close() }
    return [pscustomobject]@{ code = $code; text = $text }
}

# 1. release (create only when missing)
$existing = Req GET "https://api.github.com/repos/$Owner/$Repo/releases/tags/$Tag"
$release = $null
if ($existing.code -eq 200) {
    $release = $existing.text | ConvertFrom-Json
    Write-Host "release $Tag already exists: $($release.html_url)"
} else {
    $body = @{
        tag_name   = $Tag
        name       = "HideSheathedLeft $Tag"
        body       = "Dark Souls III 1.15.0 - hide the left-hand item's sheathed model while two-handing the right-hand weapon.`n`nSee CHANGELOG.md in the repository for details. This zip contains no game assets: the parking dummies are appended to your own chr/*.chrbnd.dcx by the bundled tools/ds3tae.exe (install.ps1 does it automatically)."
        draft      = $false
        prerelease = $false
    } | ConvertTo-Json
    $created = Req POST "https://api.github.com/repos/$Owner/$Repo/releases" $body
    Write-Host "POST release -> $($created.code)"
    if ($created.code -notin 200, 201) { Write-Host $created.text; exit 1 }
    $release = $created.text | ConvertFrom-Json
    Write-Host "release created: $($release.html_url)"
}

# 2. asset (skip when already attached)
$assetName = Split-Path -Leaf $Asset
$assets = (Req GET "https://api.github.com/repos/$Owner/$Repo/releases/$($release.id)/assets").text | ConvertFrom-Json
if ($assets | Where-Object { $_.name -eq $assetName }) {
    Write-Host "asset $assetName already attached ($((($assets | Where-Object { $_.name -eq $assetName }).size)/1KB) KB)"
} else {
    $bytes = [System.IO.File]::ReadAllBytes($Asset)
    $url = "https://uploads.github.com/repos/$Owner/$Repo/releases/$($release.id)/assets?name=$assetName"
    $r = [System.Net.HttpWebRequest]::Create($url)
    $r.Method = 'POST'
    $r.Headers.Add('Authorization', "Bearer $Token")
    $r.UserAgent = 'dsh'
    $r.ContentType = 'application/zip'
    $r.ContentLength = $bytes.Length
    $r.ServicePoint.Expect100Continue = $false
    $s = $r.GetRequestStream(); $s.Write($bytes, 0, $bytes.Length); $s.Close()
    try { $resp = $r.GetResponse() } catch [System.Net.WebException] { $resp = $_.Exception.Response }
    $code = if ($resp) { [int]$resp.StatusCode } else { -1 }
    $text = ''
    if ($resp) { $sr = New-Object IO.StreamReader($resp.GetResponseStream(), [System.Text.Encoding]::UTF8); $text = $sr.ReadToEnd(); $sr.Close() }
    Write-Host "POST asset -> $code"
    if ($code -in 200, 201) {
        $a = $text | ConvertFrom-Json
        Write-Host "asset uploaded: $($a.name)  $([math]::Round($a.size/1KB)) KB  $($a.browser_download_url)"
    } else {
        Write-Host $text
        Write-Host "upload the zip manually at $($release.html_url)"
    }
}

Write-Host ''
Write-Host "repo    -> https://github.com/$Owner/$Repo"
Write-Host "release -> https://github.com/$Owner/$Repo/releases/tag/$Tag"
