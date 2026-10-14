# Publish a HideSheathedLeft release through the GitHub REST API.
#
#   powershell -ExecutionPolicy Bypass -File publish-1.0.2.ps1 -Token <PAT>
#   powershell -ExecutionPolicy Bypass -File publish-1.0.2.ps1 -Token <PAT> -SkipRepoPush
#
# The script is idempotent: existing tags are reused, existing assets with the same name are
# deleted and re-uploaded, and an existing release body is replaced with the CHANGELOG section for
# that version.  The token is used in-process only; it is never written to disk.
#
# What it does, in order:
#   1. reads the CHANGELOG section that starts with "## <Version>" and uses it as the release body
#   2. creates the annotated tag object at the current main head (if the tag does not exist yet)
#   3. creates the release (or refreshes its body/target if it already exists)
#   4. uploads/replaces the release assets (lean zip + optional -full zip) and prints SHA-256 sums
#
# The repository content itself is pushed with plain git (`git push origin main --follow-tags`);
# pass -SkipRepoPush if that has already been done.
param(
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$Owner = 'xiangchi7',
    [string]$Repo = 'HideSheathedLeft',
    [string]$RepoDir = 'C:\Users\35866\Documents\deepseek-harness\default-workspace\HideSheathedLeft-release',
    [string]$Branch = 'main',
    [string]$Version = '1.0.2',
    [string]$Asset = '',
    [string]$FullAsset = '',
    [switch]$SkipRepoPush
)

$ErrorActionPreference = 'Stop'
$Tag = "v$Version"
$headers = @{ Authorization = "Bearer $Token"; 'User-Agent' = 'HideSheathedLeft-publisher'; Accept = 'application/vnd.github+json' }

function Req {
    param([string]$Method, [string]$Uri, [string]$Body = $null)
    $r = [System.Net.HttpWebRequest]::Create($Uri)
    $r.Method = $Method
    $r.Headers.Add('Authorization', "Bearer $Token")
    $r.UserAgent = 'HideSheathedLeft-publisher'
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
    if ($resp) {
        $sr = New-Object IO.StreamReader($resp.GetResponseStream(), [System.Text.Encoding]::UTF8)
        $text = $sr.ReadToEnd(); $sr.Close()
    }
    return [pscustomobject]@{ code = $code; text = $text }
}

function Api([string]$Method, [string]$Uri, $body = $null) {
    $params = @{ Method = $Method; Uri = "https://api.github.com$Uri"; Headers = $headers }
    if ($null -ne $body) {
        $params.ContentType = 'application/json'
        $params.Body = [System.Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -Depth 6 -Compress $body))
    }
    return Invoke-RestMethod @params
}

# ---------------------------------------------------------------- 1. release body
$changelog = Join-Path $RepoDir 'CHANGELOG.md'
$body = ''
if (Test-Path -LiteralPath $changelog) {
    # read as UTF-8 explicitly: Get-Content would decode it with the ANSI codepage and mangle
    # every non-ASCII character (em dashes, Chinese) on its way into the release body
    $text = [System.IO.File]::ReadAllText($changelog, [System.Text.Encoding]::UTF8)
    $m = [regex]::Match($text, "(?ms)^##\s+$([regex]::Escape($Version))\s*\r?\n(.*?)(?=^##\s|\z)")
    if ($m.Success) { $body = "# HideSheathedLeft $Version`n`n" + $m.Groups[1].Value.Trim() }
}
if (-not $body) { $body = "HideSheathedLeft $Version" }
Write-Host "release body: $($body.Split("`n").Count) line(s) from CHANGELOG.md"

# ---------------------------------------------------------------- 2. tag
$head = Api GET "/repos/$Owner/$Repo/git/ref/heads/$Branch"
$headSha = $head.object.sha
Write-Host "main head: $($headSha.Substring(0,10))"

$tagSha = $null
try { $tagSha = (Api GET "/repos/$Owner/$Repo/git/ref/tags/$Tag").object.sha } catch { }
if ($tagSha) {
    Write-Host "tag $Tag already exists"
} else {
    $tagObj = Api POST "/repos/$Owner/$Repo/git/tags" @{
        tag     = $Tag
        message = "HideSheathedLeft $Version"
        object  = $headSha
        type    = 'commit'
    }
    Api POST "/repos/$Owner/$Repo/git/refs" @{ ref = "refs/tags/$Tag"; sha = $tagObj.sha } | Out-Null
    Write-Host "tag $Tag created at $($headSha.Substring(0,10))"
}

# ---------------------------------------------------------------- 3. release
$release = $null
try { $release = Api GET "/repos/$Owner/$Repo/releases/tags/$Tag" } catch { }
if ($release) {
    Write-Host "release $Tag exists (id $($release.id)) - refreshing name/body"
    $release = Api PATCH "/repos/$Owner/$Repo/releases/$($release.id)" @{
        name = "HideSheathedLeft $Tag"
        body = $body
    }
} else {
    $release = Api POST "/repos/$Owner/$Repo/releases" @{
        tag_name         = $Tag
        target_commitish = $Branch
        name             = "HideSheathedLeft $Tag"
        body             = $body
        draft            = $false
        prerelease       = $false
    }
    Write-Host "release created: $($release.html_url)"
}

# ---------------------------------------------------------------- 4. assets
$toUpload = @()
if ($Asset)     { $toUpload += $Asset }
if ($FullAsset) { $toUpload += $FullAsset }

foreach ($file in $toUpload) {
    if (-not (Test-Path -LiteralPath $file)) { Write-Warning "asset not found, skipped: $file"; continue }
    $name  = Split-Path -Leaf $file
    $bytes = [System.IO.File]::ReadAllBytes($file)
    $sha   = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower()

    foreach ($a in ((Api GET "/repos/$Owner/$Repo/releases/$($release.id)/assets"))) {
        if ($a.name -eq $name) {
            Api DELETE "/repos/$Owner/$Repo/releases/assets/$($a.id)" | Out-Null
            Write-Host "  removed previous asset $name"
        }
    }

    $r = [System.Net.HttpWebRequest]::Create("https://uploads.github.com/repos/$Owner/$Repo/releases/$($release.id)/assets?name=$name")
    $r.Method = 'POST'
    $r.Headers.Add('Authorization', "Bearer $Token")
    $r.UserAgent = 'HideSheathedLeft-publisher'
    $r.ContentType = 'application/zip'
    $r.ContentLength = $bytes.Length
    $r.ServicePoint.Expect100Continue = $false
    $s = $r.GetRequestStream(); $s.Write($bytes, 0, $bytes.Length); $s.Close()
    try { $resp = $r.GetResponse() } catch [System.Net.WebException] { $resp = $_.Exception.Response }
    $code = if ($resp) { [int]$resp.StatusCode } else { -1 }
    Write-Host ("  asset {0} -> HTTP {1}  ({2} KB, sha256 {3})" -f $name, $code, [math]::Round($bytes.Length / 1KB), $sha)
}

Write-Host ''
Write-Host "repo    -> https://github.com/$Owner/$Repo"
Write-Host "release -> https://github.com/$Owner/$Repo/releases/tag/$Tag"
