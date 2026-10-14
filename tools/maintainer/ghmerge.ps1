param(
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$Owner = 'xiangchi7',
    [string]$NewRepo = 'HideSheathedLeft',
    [string]$OldRepo = 'HideSheathedLeft-for-DS3',
    [string]$FullZip = 'D:\Desktop\HideSheathedLeft-1.0.1-full.zip',
    [string]$Tag = 'v1.0.1',
    [string]$OldTag = 'v1.0.0'
)
$ErrorActionPreference = 'Stop'

function Req {
    param([string]$Method, [string]$Uri, [string]$Body = $null, [switch]$Raw)
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
    if ($Raw) {
        $ms = New-Object IO.MemoryStream
        if ($resp) { $resp.GetResponseStream().CopyTo($ms) }
        return [pscustomobject]@{ code = $code; bytes = $ms.ToArray() }
    }
    $text = ''
    if ($resp) { $sr = New-Object IO.StreamReader($resp.GetResponseStream(), [System.Text.Encoding]::UTF8); $text = $sr.ReadToEnd(); $sr.Close() }
    return [pscustomobject]@{ code = $code; text = $text }
}

# 0. auth
$me = Req GET 'https://api.github.com/user'
if ($me.code -ne 200) { Write-Host "TOKEN INVALID (HTTP $($me.code)) - paste a fresh PAT"; exit 2 }
$login = ($me.text | ConvertFrom-Json).login
Write-Host "authenticated as $login"

# 1. full package as the second asset of the existing v1.0.1 release
$rel = (Req GET "https://api.github.com/repos/$Owner/$NewRepo/releases/tags/$Tag").text | ConvertFrom-Json
$assetName = Split-Path -Leaf $FullZip
$assets = (Req GET "https://api.github.com/repos/$Owner/$NewRepo/releases/$($rel.id)/assets").text | ConvertFrom-Json
if ($assets | Where-Object { $_.name -eq $assetName }) {
    Write-Host "asset $assetName already attached"
} elseif (-not (Test-Path -LiteralPath $FullZip)) {
    Write-Host "WARNING: $FullZip not found - skipping asset upload"
} else {
    $bytes = [System.IO.File]::ReadAllBytes($FullZip)
    $r = [System.Net.HttpWebRequest]::Create("https://uploads.github.com/repos/$Owner/$NewRepo/releases/$($rel.id)/assets?name=$assetName")
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
        Write-Host "asset uploaded: $($a.name)  $([math]::Round($a.size/1MB,1)) MB"
    } else { Write-Host "ASSET UPLOAD FAILED ($code): $text" }
}

# 2. seed the old project into the new repo as an orphan $OldTag snapshot
$existing = Req GET "https://api.github.com/repos/$Owner/$NewRepo/git/ref/tags/$OldTag"
if ($existing.code -eq 200) {
    Write-Host "tag $OldTag already exists - nothing to import"
} else {
    $old = (Req GET "https://api.github.com/repos/$Owner/$OldRepo").text | ConvertFrom-Json
    $branch = $old.default_branch
    $oldHead = ((Req GET "https://api.github.com/repos/$Owner/$OldRepo/git/ref/heads/$branch").text | ConvertFrom-Json).object.sha
    $oldTree = (Req GET "https://api.github.com/repos/$Owner/$OldRepo/git/trees/$oldHead`?recursive=1").text | ConvertFrom-Json
    $entries = @($oldTree.tree | Where-Object { $_.type -eq 'blob' })
    Write-Host "importing $($entries.Count) file(s) from $Owner/$OldRepo@$($branch) ($($oldHead.Substring(0,8))) ..."

    $tree = @()
    foreach ($e in $entries) {
        $blob = (Req GET "https://api.github.com/repos/$Owner/$OldRepo/git/blobs/$($e.sha)").text | ConvertFrom-Json
        $b64 = ($blob.content -replace "`r?`n", '')
        $new = (Req POST "https://api.github.com/repos/$Owner/$NewRepo/git/blobs" (@{ content = $b64; encoding = 'base64' } | ConvertTo-Json -Compress)).text | ConvertFrom-Json
        $tree += @{ path = $e.path; mode = $e.mode; type = 'blob'; sha = $new.sha }
    }
    $treeObj = (Req POST "https://api.github.com/repos/$Owner/$NewRepo/git/trees" (@{ tree = $tree } | ConvertTo-Json -Depth 6 -Compress)).text | ConvertFrom-Json
    $msg = "Import $OldRepo as $OldTag (first-generation approach: invalid-poly hide + shared import-slot loader shell). Superseded by $Tag."
    $commit = (Req POST "https://api.github.com/repos/$Owner/$NewRepo/git/commits" (@{ message = $msg; tree = $treeObj.sha; parents = @() } | ConvertTo-Json -Depth 6 -Compress)).text | ConvertFrom-Json
    $tagObj = (Req POST "https://api.github.com/repos/$Owner/$NewRepo/git/tags" (@{ tag = $OldTag; message = "HideSheathedLeft $OldTag (imported from $OldRepo)"; object = $commit.sha; type = 'commit' } | ConvertTo-Json -Compress)).text | ConvertFrom-Json
    $ref = Req POST "https://api.github.com/repos/$Owner/$NewRepo/git/refs" (@{ ref = "refs/tags/$OldTag"; sha = $tagObj.sha } | ConvertTo-Json -Compress)
    Write-Host "import done: commit $($commit.sha.Substring(0,10)), tag ref -> HTTP $($ref.code)"
}

# 3. archive the old repo and point it at the new one
$patch = @{
    archived    = $true
    description = "ARCHIVED - moved to https://github.com/$Owner/$NewRepo (this repo is the first-generation approach, kept as $OldTag history there)"
    homepage    = "https://github.com/$Owner/$NewRepo"
} | ConvertTo-Json
$pr = Req PATCH "https://api.github.com/repos/$Owner/$OldRepo" $patch
Write-Host "archive old repo -> HTTP $($pr.code)"

# 4. summary
$rel2 = (Req GET "https://api.github.com/repos/$Owner/$NewRepo/releases/tags/$Tag").text | ConvertFrom-Json
Write-Host ''
Write-Host "release assets:"
foreach ($a in $rel2.assets) { Write-Host ("  {0,-34} {1,8} KB" -f $a.name, [math]::Round($a.size/1KB)) }
$tags = (Req GET "https://api.github.com/repos/$Owner/$NewRepo/git/refs/tags").text | ConvertFrom-Json
Write-Host ("tags: " + (($tags | ForEach-Object { $_.ref -replace 'refs/tags/','' }) -join ', '))
Write-Host "repo -> https://github.com/$Owner/$NewRepo"
