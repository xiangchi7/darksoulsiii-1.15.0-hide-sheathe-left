# Publish the repo through the GitHub REST API instead of `git push`.
#
# `git push` over HTTPS to github.com is reset at TLS level on this network, while
# api.github.com works, so the same content is uploaded with the Git Data API:
#   blobs -> tree -> commit -> refs/heads/main -> tag object -> release + asset zip
#
#   powershell -ExecutionPolicy Bypass -File publish-via-api.ps1 -Token <PAT>
#
# The token is used in-process only; it is never written to disk.

param(
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$RepoDir = 'C:\Users\35866\Documents\deepseek-harness\default-workspace\HideSheathedLeft-1.0.1',
    [string]$Asset = 'D:\Desktop\HideSheathedLeft-1.0.1.zip',
    [string]$RepoName = 'HideSheathedLeft',
    [string]$Tag = 'v1.0.1',
    [string]$Branch = 'main'
)

$ErrorActionPreference = 'Stop'
$headers = @{ Authorization = "Bearer $Token"; 'User-Agent' = 'HideSheathedLeft-publisher'; Accept = 'application/vnd.github+json' }
$api = 'https://api.github.com'

function Api([string]$method, [string]$uri, $body = $null) {
    $params = @{ Method = $method; Uri = $uri; Headers = $headers }
    if ($null -ne $body) {
        $params.ContentType = 'application/json'
        $params.Body = ([System.Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -Depth 6 -Compress $body)))
    }
    return Invoke-RestMethod @params
}

# who owns the token / which repo do we write to
$me = Api GET "$api/user"
$owner = $me.login
Write-Host "authenticated as $owner"

$repo = $null
try { $repo = Api GET "$api/repos/$owner/$RepoName" } catch { }
if (-not $repo) {
    Write-Host "creating repo $owner/$RepoName ..."
    $repo = Api POST "$api/user/repos" @{
        name        = $RepoName
        private     = $false
        auto_init   = $false
        has_issues  = $true
        description = 'Dark Souls III 1.15.0: hide the left-hand item''s sheathed model while two-handing the right-hand weapon'
    }
}
$owner = $repo.owner.login
$name = $repo.name
Write-Host "target repo: $owner/$name"

# An entirely empty repo rejects blob creation ("Git Repository is empty", 409), so seed
# one placeholder commit first.  The tree built below replaces it completely and the
# branch is force-pointed at a parentless commit, so the placeholder never survives.
if (-not $repo.size -or [int]$repo.size -eq 0) {
    Write-Host 'seeding an initial commit (empty repos cannot create blobs) ...'
    $seedB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes("init`n"))
    $seed = Api PUT "$api/repos/$owner/$name/contents/.init" @{ message = 'init'; content = $seedB64 }
    Write-Host "  seeded: $($seed.commit.sha)"
}

# 1. upload every file as a blob
$root = (Resolve-Path -LiteralPath $RepoDir).Path
$files = Get-ChildItem -LiteralPath $root -Recurse -File |
         Where-Object { $_.FullName -notmatch '\\\.git\\' } |
         Sort-Object FullName
Write-Host "uploading $($files.Count) file(s) as blobs ..."
$tree = @()
foreach ($f in $files) {
    $rel = $f.FullName.Substring($root.Length + 1).Replace('\', '/')
    $b64 = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($f.FullName))
    $blob = Api POST "$api/repos/$owner/$name/git/blobs" @{ content = $b64; encoding = 'base64' }
    $tree += @{ path = $rel; mode = '100644'; type = 'blob'; sha = $blob.sha }
}
Write-Host "  blobs done ($($tree.Count) entries)"

# 2. tree + commit
$treeObj = Api POST "$api/repos/$owner/$name/git/trees" @{ tree = $tree }
$msg = (Get-Content -LiteralPath (Join-Path $root 'CHANGELOG.md') -Raw)
$commit = Api POST "$api/repos/$owner/$name/git/commits" @{
    message = "HideSheathedLeft 1.0.1`n`n$msg"
    tree    = $treeObj.sha
    parents = @()
}
Write-Host "commit: $($commit.sha)"

# 3. branch + annotated tag
try {
    Api POST "$api/repos/$owner/$name/git/refs" @{ ref = "refs/heads/$Branch"; sha = $commit.sha } | Out-Null
    Write-Host "branch $Branch created"
} catch {
    Api PATCH "$api/repos/$owner/$name/git/refs/heads/$Branch" @{ sha = $commit.sha; force = $true } | Out-Null
    Write-Host "branch $Branch updated"
}
try {
    $tagObj = Api POST "$api/repos/$owner/$name/git/tags" @{ tag = $Tag; message = "HideSheathedLeft $Tag"; object = $commit.sha; type = 'commit' }
    Api POST "$api/repos/$owner/$name/git/refs" @{ ref = "refs/tags/$Tag"; sha = $tagObj.sha } | Out-Null
    Write-Host "tag $Tag created"
} catch {
    Write-Host "tag $Tag already exists (or could not be created): $($_.Exception.Message)"
}

# 4. release + asset
$release = $null
try { $release = Api GET "$api/repos/$owner/$name/releases/tags/$Tag" } catch { }
if (-not $release) {
    $release = Api POST "$api/repos/$owner/$name/releases" @{
        tag_name         = $Tag
        target_commitish = $Branch
        name             = "HideSheathedLeft $Tag"
        body             = $msg
        draft            = $false
        prerelease       = $false
    }
    Write-Host "release created: $($release.html_url)"
} else {
    Write-Host "release exists: $($release.html_url)"
}

if (Test-Path -LiteralPath $Asset) {
    $assetName = Split-Path -Leaf $Asset
    $bytes = [System.IO.File]::ReadAllBytes($Asset)
    try {
        Invoke-RestMethod -Method Post -Headers $headers -ContentType 'application/zip' `
            -Uri "https://uploads.github.com/repos/$owner/$name/releases/$($release.id)/assets?name=$assetName" `
            -Body $bytes | Out-Null
        Write-Host "asset uploaded: $assetName ($([math]::Round($bytes.Length/1KB)) KB)"
    } catch {
        Write-Host "ASSET UPLOAD FAILED: $($_.Exception.Message)"
        Write-Host "upload it manually at $($release.html_url)"
    }
}

Write-Host ''
Write-Host "repo    -> https://github.com/$owner/$name"
Write-Host "release -> https://github.com/$owner/$name/releases/tag/$Tag"
Write-Host "commit  -> https://github.com/$owner/$name/commit/$($commit.sha)"
