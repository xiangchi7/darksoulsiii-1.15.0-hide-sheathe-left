param(
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$Owner = 'xiangchi7',
    [string]$Repo = 'HideSheathedLeft',
    [string]$Tag = 'v1.0.0',
    [string]$WorkDir = 'C:\Users\35866\Documents\deepseek-harness\default-workspace\publish-1.0.0'
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

# 1. materialise the v1.0.0 tree (the imported first-generation snapshot)
if (Test-Path -LiteralPath $WorkDir) { Remove-Item -LiteralPath $WorkDir -Recurse -Force }
New-Item -ItemType Directory -Path $WorkDir | Out-Null
$ref = (Req GET "https://api.github.com/repos/$Owner/$Repo/git/ref/tags/$Tag").text | ConvertFrom-Json
$commitSha = $ref.object.sha
if ($ref.object.type -eq 'tag') {
    $commitSha = ((Req GET "https://api.github.com/repos/$Owner/$Repo/git/tags/$($ref.object.sha)").text | ConvertFrom-Json).object.sha
}
$tree = (Req GET "https://api.github.com/repos/$Owner/$Repo/git/trees/$commitSha`?recursive=1").text | ConvertFrom-Json
$blobs = @($tree.tree | Where-Object { $_.type -eq 'blob' })
Write-Host "v1.0.0 snapshot $($commitSha.Substring(0,10)): $($blobs.Count) file(s)"
foreach ($e in $blobs) {
    $blob = (Req GET "https://api.github.com/repos/$Owner/$Repo/git/blobs/$($e.sha)").text | ConvertFrom-Json
    $bytes = [Convert]::FromBase64String(($blob.content -replace "`r?`n", ''))
    $target = Join-Path $WorkDir ($e.path -replace '/', '\')
    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
    [System.IO.File]::WriteAllBytes($target, $bytes)
}
$zip = "$WorkDir\HideSheathedLeft-1.0.0.zip"
Compress-Archive -Path "$WorkDir\*" -DestinationPath $zip -Force
Write-Host "built $zip  ($([math]::Round((Get-Item $zip).Length/1KB)) KB)"

# 2. release for the old version (create when missing)
$existing = Req GET "https://api.github.com/repos/$Owner/$Repo/releases/tags/$Tag"
if ($existing.code -eq 200) {
    $release = $existing.text | ConvertFrom-Json
    Write-Host "release $Tag already exists"
} else {
    $body = @{
        tag_name   = $Tag
        name       = "HideSheathedLeft $Tag (first generation)"
        body       = "First-generation approach, kept for reference.`n`nIt writes an invalid dummy poly (-1) into WepAbsorpPosParam's leftHang_*/right_1..3 fields. On the retail engine an invalid poly produces a degenerate (NaN) attach matrix, which shows up as black triangles and full-screen flicker.`n`nSuperseded by v1.0.1, which keeps the model invisible by attaching it to a real dummy parked 1000 m below the character (and appends that dummy to every character model)."
        draft      = $false
        prerelease = $false
    } | ConvertTo-Json
    $created = Req POST "https://api.github.com/repos/$Owner/$Repo/releases" $body
    if ($created.code -notin 200, 201) { Write-Host "CREATE FAILED ($($created.code)): $($created.text)"; exit 1 }
    $release = $created.text | ConvertFrom-Json
    Write-Host "release created: $($release.html_url)"
}

# 3. attach the 1.0.0 zip
$assetName = Split-Path -Leaf $zip
$assets = (Req GET "https://api.github.com/repos/$Owner/$Repo/releases/$($release.id)/assets").text | ConvertFrom-Json
if ($assets | Where-Object { $_.name -eq $assetName }) {
    Write-Host "asset $assetName already attached"
} else {
    $bytes = [System.IO.File]::ReadAllBytes($zip)
    $r = [System.Net.HttpWebRequest]::Create("https://uploads.github.com/repos/$Owner/$Repo/releases/$($release.id)/assets?name=$assetName")
    $r.Method = 'POST'
    $r.Headers.Add('Authorization', "Bearer $Token")
    $r.UserAgent = 'dsh'
    $r.ContentType = 'application/zip'
    $r.ContentLength = $bytes.Length
    $r.ServicePoint.Expect100Continue = $false
    $s = $r.GetRequestStream(); $s.Write($bytes, 0, $bytes.Length); $s.Close()
    try { $resp = $r.GetResponse() } catch [System.Net.WebException] { $resp = $_.Exception.Response }
    $code = if ($resp) { [int]$resp.StatusCode } else { -1 }
    if ($code -in 200, 201) { Write-Host "asset uploaded: $assetName ($([math]::Round($bytes.Length/1KB)) KB)" }
    else { $sr = New-Object IO.StreamReader($resp.GetResponseStream(), [System.Text.Encoding]::UTF8); Write-Host "ASSET FAILED ($code): $($sr.ReadToEnd())" }
}

# 4. summary
$all = (Req GET "https://api.github.com/repos/$Owner/$Repo/releases").text | ConvertFrom-Json
Write-Host ''
Write-Host 'releases now:'
foreach ($r in $all) {
    Write-Host ("  {0,-8} {1}" -f $r.tag_name, $r.name)
    foreach ($a in $r.assets) { Write-Host ("      - {0,-34} {1,8} KB" -f $a.name, [math]::Round($a.size/1KB)) }
}
