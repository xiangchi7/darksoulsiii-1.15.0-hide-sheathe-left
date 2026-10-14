param(
    [Parameter(Mandatory=$true)][string]$Token,
    [string]$Owner = 'xiangchi7',
    [string]$Repo = 'HideSheathedLeft',
    [string]$RepoDir = 'C:\Users\35866\Documents\deepseek-harness\default-workspace\HideSheathedLeft-1.0.1'
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

# remote tree of the default branch
$ref = (Req GET "https://api.github.com/repos/$Owner/$Repo/git/ref/heads/main").text | ConvertFrom-Json
$head = $ref.object.sha
$tree = (Req GET "https://api.github.com/repos/$Owner/$Repo/git/trees/$head`?recursive=1").text | ConvertFrom-Json
$remote = @{}
foreach ($e in $tree.tree) { if ($e.type -eq 'blob') { $remote[$e.path] = $e.sha } }
Write-Host "remote commit $head : $($remote.Count) blob(s)"

# local files -> git blob sha
$root = (Resolve-Path -LiteralPath $RepoDir).Path
Push-Location $root
$local = @{}
foreach ($f in (Get-ChildItem -LiteralPath $root -Recurse -File | Where-Object { $_.FullName -notmatch '\\\.git\\' })) {
    $rel = $f.FullName.Substring($root.Length + 1).Replace('\', '/')
    $sha = (& git hash-object -- $f.FullName).Trim()
    $local[$rel] = $sha
}
Pop-Location
Write-Host "local: $($local.Count) file(s)"

$missing = @($local.Keys | Where-Object { -not $remote.ContainsKey($_) })
$differ = @($local.Keys | Where-Object { $remote.ContainsKey($_) -and $remote[$_] -ne $local[$_] })
$extra = @($remote.Keys | Where-Object { -not $local.ContainsKey($_) })
Write-Host "missing on remote : $($missing.Count) $($missing -join ', ')"
Write-Host "different content : $($differ.Count) $($differ -join ', ')"
Write-Host "extra on remote   : $($extra.Count) $($extra -join ', ')"

$tags = (Req GET "https://api.github.com/repos/$Owner/$Repo/git/refs/tags").text
Write-Host "tag refs: $tags"
$rel = Req GET "https://api.github.com/repos/$Owner/$Repo/releases"
Write-Host "releases: $(($rel.text | ConvertFrom-Json | Select-Object -ExpandProperty tag_name) -join ', ')"
