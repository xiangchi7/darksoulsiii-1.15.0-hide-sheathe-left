# Publish HideSheathedLeft 1.0.1 to GitHub: create the repo if needed, push, then
# create the v1.0.1 release and attach the zip asset.
#
#   powershell -ExecutionPolicy Bypass -File publish-1.0.1.ps1 -Token <PAT>
#
# The token is only used in-process (API header) and inline in the one push URL -- it is
# never written to .git/config or anywhere else.  Revoke it on GitHub when done.

param(
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$Owner = 'xiangchi7',
    [string]$Repo = 'HideSheathedLeft',
    [string]$RepoDir = 'C:\Users\35866\Documents\deepseek-harness\default-workspace\HideSheathedLeft-1.0.1',
    [string]$Asset = 'D:\Desktop\HideSheathedLeft-1.0.1.zip',
    [string]$Tag = 'v1.0.1'
)

$ErrorActionPreference = 'Stop'
$headers = @{ Authorization = "Bearer $Token"; 'User-Agent' = 'HideSheathedLeft-publisher' }

# 1. repository (create when missing)
$created = $false
try {
    $r = Invoke-RestMethod -Uri "https://api.github.com/repos/$Owner/$Repo" -Headers $headers
    Write-Host "repo already exists: $($r.full_name) (default branch: $($r.default_branch))"
} catch {
    Write-Host "creating repo $Owner/$Repo ..."
    $body = @{
        name        = $Repo
        private     = $false
        auto_init   = $false
        has_issues  = $true
        description = 'Dark Souls III 1.15.0: hide the left-hand item''s sheathed model while two-handing the right-hand weapon'
    } | ConvertTo-Json
    $r = Invoke-RestMethod -Method Post -Uri 'https://api.github.com/user/repos' -Headers $headers -ContentType 'application/json' -Body $body
    $created = $true
    Write-Host "created: $($r.full_name)"
}
# trust the API response over the parameters (the token's account may differ)
$Owner = $r.owner.login
$Repo = $r.name

# 2. push (branch main + the tag); token goes inline, never into .git/config
Push-Location $RepoDir
try {
    $url = "https://x-access-token:$Token@github.com/$Owner/$Repo.git"
    & git push $url "HEAD:refs/heads/main" --tags --force
    if ($LASTEXITCODE -ne 0) { throw "git push failed with exit code $LASTEXITCODE" }
    Write-Host 'pushed branch main + tag(s).'
} finally {
    Pop-Location
}

# 3. release + asset
$release = $null
try {
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Owner/$Repo/releases/tags/$Tag" -Headers $headers
    Write-Host "release $Tag already exists (id $($release.id))"
} catch {
    $body = @{
        tag_name         = $Tag
        target_commitish = 'main'
        name             = "HideSheathedLeft $Tag"
        body             = (Get-Content -LiteralPath (Join-Path $RepoDir 'CHANGELOG.md') -Raw)
        draft            = $false
        prerelease       = $false
    } | ConvertTo-Json
    $release = Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$Owner/$Repo/releases" -Headers $headers -ContentType 'application/json' -Body $body
    Write-Host "release created: $($release.html_url)"
}

if (Test-Path -LiteralPath $Asset) {
    $name = Split-Path -Leaf $Asset
    $existing = $null
    try { $existing = (Invoke-RestMethod -Uri "https://api.github.com/repos/$Owner/$Repo/releases/$($release.id)/assets" -Headers $headers) | Where-Object { $_.name -eq $name } } catch { }
    if ($existing) {
        Write-Host "asset $name already attached"
    } else {
        $bytes = [System.IO.File]::ReadAllBytes($Asset)
        Invoke-RestMethod -Method Post -Uri "https://uploads.github.com/repos/$Owner/$Repo/releases/$($release.id)/assets?name=$name" -Headers $headers -ContentType 'application/zip' -Body $bytes | Out-Null
        Write-Host "asset uploaded: $name ($([math]::Round($bytes.Length / 1KB)) KB)"
    }
} else {
    Write-Host "WARNING: asset not found: $Asset"
}

Write-Host ''
Write-Host "done -> https://github.com/$Owner/$Repo"
Write-Host "release -> https://github.com/$Owner/$Repo/releases/tag/$Tag"
if ($created) { Write-Host 'Remember: the new repo has no README on GitHub side; content comes from the push.' }
