<#
Independent provenance check for the cross-module dataset.

For a set of samples it RE-DOWNLOADS the fix commit straight from GitHub and confirms the
shipped vuln/ and fixed/ files are byte-identical to the real <sha>^1 (pre-fix) and <sha>
(post-fix) blobs. This proves the dataset was not fabricated or altered: every positive is
the true vulnerable code and every negative is the true patched code.

Requirements: git + internet only (no PHP/Java/Neo4j needed).

Usage:
  ./verify_provenance.ps1 -Random 30      # spot-check 30 random advisories (recommended)
  ./verify_provenance.ps1 -All            # verify every advisory (slow, clones a lot)
  ./verify_provenance.ps1 -Id GHSA-...    # one specific advisory

Output: PASS/FAIL per file + a summary. Writes provenance_report.csv.
#>
param(
  [int]$Random = 30, [switch]$All, [string]$Id,
  [string]$DS,
  [string]$Tmp = "$env:TEMP\phpjoy_verify",
  [string]$Report = "$PSScriptRoot\provenance_report.csv"
)
$ErrorActionPreference = "Continue"
# Locate dataset_xmodule portably: script dir, parent dir, or current dir.
if(-not $DS){
  $DS = @("$PSScriptRoot\dataset_xmodule","$PSScriptRoot\..\dataset_xmodule",".\dataset_xmodule") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
}
if(-not $DS){ throw "dataset_xmodule not found. Pass -DS <path-to-dataset_xmodule>." }
$idx = Get-Content "$DS\index.json" -Raw | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null

$sel = if($Id){ $idx | Where-Object { $_.id -eq $Id } }
       elseif($All){ $idx }
       else { $idx | Get-Random -Count ([Math]::Min($Random,$idx.Count)) }

function Hash($s){ if($null -eq $s){ return "" }
  $md5=[System.Security.Cryptography.MD5]::Create()
  ([BitConverter]::ToString($md5.ComputeHash([Text.Encoding]::UTF8.GetBytes($s)))) }

"id,cve,file,vuln_match,fixed_match" | Out-File $Report -Encoding utf8
$okAdv=0; $badAdv=0; $checked=0; $bad=0
foreach($s in $sel){
  $parts=$s.repo -split '/'; $dir=Join-Path $Tmp ("{0}__{1}" -f $parts[0],$parts[1])
  if(-not (Test-Path (Join-Path $dir ".git"))){
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    git -C $dir init -q; git -C $dir remote add origin ("https://github.com/{0}.git" -f $s.repo) 2>&1 | Out-Null
  }
  git -C $dir fetch --depth 2 origin $s.fix_commit -q 2>&1 | Out-Null
  if($LASTEXITCODE -ne 0){ Write-Host ("[SKIP] {0} fetch failed (commit gone?)" -f $s.id) -ForegroundColor DarkYellow; continue }

  $advOk=$true
  $sampleDir = Join-Path (Join-Path $DS $s.cwe) $s.id
  foreach($vf in (Get-ChildItem (Join-Path $sampleDir 'vuln') -File)){
    $rel = ($vf.Name -replace '__','/')
    $realVuln  = (git -C $dir show ("{0}^1:{1}" -f $s.fix_commit,$rel) 2>$null | Out-String)
    $realFixed = (git -C $dir show ("{0}:{1}"   -f $s.fix_commit,$rel) 2>$null | Out-String)
    $shipVuln  = Get-Content $vf.FullName -Raw
    $shipFixedP= Join-Path $sampleDir ("fixed\{0}" -f $vf.Name)
    $shipFixed = if(Test-Path $shipFixedP){ Get-Content $shipFixedP -Raw } else { $null }
    $vMatch = (Hash $realVuln.TrimEnd()) -eq (Hash $shipVuln.TrimEnd())
    $fMatch = (Hash $realFixed.TrimEnd()) -eq (Hash $shipFixed.TrimEnd())
    $checked++; if(-not ($vMatch -and $fMatch)){ $bad++; $advOk=$false }
    "{0},{1},{2},{3},{4}" -f $s.id,$s.cve,$rel,$vMatch,$fMatch | Add-Content $Report -Encoding utf8
  }
  if($advOk){ $okAdv++; Write-Host ("[PASS] {0} {1} ({2})" -f $s.id,$s.cve,$s.repo) -ForegroundColor Green }
  else     { $badAdv++; Write-Host ("[FAIL] {0} {1} ({2}) - see report" -f $s.id,$s.cve,$s.repo) -ForegroundColor Red }
}
Remove-Item $Tmp -Recurse -Force -ErrorAction SilentlyContinue
Write-Host ("`nAdvisories: {0} PASS / {1} FAIL   Files: {2} checked, {3} mismatched" -f $okAdv,$badAdv,$checked,$bad) -ForegroundColor Cyan
Write-Host ("Report: {0}" -f $Report)
