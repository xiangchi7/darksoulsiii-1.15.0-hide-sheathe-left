param([Parameter(Mandatory=$true)][string]$Token)
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

$r = Req GET 'https://api.github.com/repos/xiangchi7/HideSheathedLeft'
Write-Host "GET repo -> $($r.code)"
Write-Host ($r.text.Substring(0, [Math]::Min(400, $r.text.Length)))

$r2 = Req GET 'https://api.github.com/repos/xiangchi7/HideSheathedLeft/contents/'
Write-Host "`nGET contents -> $($r2.code)"
Write-Host ($r2.text.Substring(0, [Math]::Min(300, $r2.text.Length)))

$r3 = Req GET 'https://api.github.com/repos/xiangchi7/HideSheathedLeft/git/refs'
Write-Host "`nGET refs -> $($r3.code)"
Write-Host ($r3.text.Substring(0, [Math]::Min(300, $r3.text.Length)))

$b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes('hello'))
$r4 = Req POST 'https://api.github.com/repos/xiangchi7/HideSheathedLeft/git/blobs' ('{"content":"' + $b64 + '","encoding":"base64"}')
Write-Host "`nPOST blob -> $($r4.code)"
Write-Host ($r4.text.Substring(0, [Math]::Min(300, $r4.text.Length)))
