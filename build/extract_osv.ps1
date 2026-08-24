# Extract PHP/Packagist advisories that have (a) a CWE and (b) a GitHub fix commit.
# Output: build/candidates_osv.json  (one record per advisory-with-fix-commit)
param(
  [string]$Dir = "D:\Thesis\Thesis\Artifact\phpjoy_release\build\packagist",
  [string]$Out = "D:\Thesis\Thesis\Artifact\phpjoy_release\build\candidates_osv.json"
)
$ErrorActionPreference = "Stop"
$files = Get-ChildItem $Dir -Filter *.json
$records = New-Object System.Collections.ArrayList
$rxCommit = [regex]'github\.com/([^/]+)/([^/]+)/commit/([0-9a-f]{7,40})'

foreach($f in $files){
  $j = Get-Content $f.FullName -Raw | ConvertFrom-Json

  # CWE ids (OSV stores them in database_specific.cwe_ids at top level)
  $cwes = @()
  if($j.database_specific -and $j.database_specific.cwe_ids){ $cwes = @($j.database_specific.cwe_ids) }

  # CVE aliases
  $cves = @()
  if($j.aliases){ $cves = @($j.aliases | Where-Object { $_ -like 'CVE-*' }) }

  # Fix commits from references (type FIX or any github commit url)
  $fixCommits = New-Object System.Collections.ArrayList
  if($j.references){
    foreach($r in $j.references){
      if(-not $r.url){ continue }
      $m = $rxCommit.Match($r.url)
      if($m.Success){
        [void]$fixCommits.Add([pscustomobject]@{
          owner=$m.Groups[1].Value; repo=($m.Groups[2].Value -replace '\.git$',''); sha=$m.Groups[3].Value;
          reftype=$r.type; url=$r.url })
      }
    }
  }

  # package name (first affected)
  $pkg = $null; $eco = $null
  if($j.affected -and $j.affected.Count -gt 0){ $pkg = $j.affected[0].package.name; $eco = $j.affected[0].package.ecosystem }

  # severity
  $sev = $null
  if($j.database_specific -and $j.database_specific.severity){ $sev = $j.database_specific.severity }

  if($fixCommits.Count -gt 0){
    [void]$records.Add([pscustomobject]@{
      id=$j.id; cves=$cves; cwes=$cwes; package=$pkg; ecosystem=$eco; severity=$sev;
      published=$j.published; fix_commits=$fixCommits; summary=$j.summary
    })
  }
}

$records | ConvertTo-Json -Depth 8 | Out-File -FilePath $Out -Encoding utf8

# Summary
"Total advisories scanned : $($files.Count)"
"With GitHub fix commit   : $($records.Count)"
"With fix commit AND CWE  : $(@($records | Where-Object { $_.cwes.Count -gt 0 }).Count)"
"`nTop CWE among fix-commit advisories:"
$records | Where-Object { $_.cwes.Count -gt 0 } | ForEach-Object { $_.cwes } | Group-Object | Sort-Object Count -Descending | Select-Object -First 15 Count,Name | Format-Table -AutoSize
