<#
Manual-review helper for the cross-module dataset.

Prints, for each selected sample, everything a human needs to judge whether it is a
TRUE cross-module taint vulnerability: metadata, the security patch, the boundary
evidence (include/extends/trait in the vulnerable file), the tainted-source lines, and
the GitHub advisory + commit URLs for online cross-checking.

Usage:
  ./review.ps1 -Id GHSA-277f-37gw-9gmq         # one specific sample
  ./review.ps1 -Random 3                        # 3 random samples
  ./review.ps1 -Random 2 -Cwe CWE-89            # 2 random SQLi samples
  ./review.ps1 -Random 2 -Boundary include      # 2 random include-boundary samples
  ./review.ps1 -Stratified 2                     # 2 per CWE (a balanced review set)

Records a row per reviewed sample in review_sheet.csv (fill in verdict TP/FP + notes).
#>
param(
  [string]$Id, [int]$Random = 0, [int]$Stratified = 0,
  [string]$Cwe, [string]$Boundary,
  [string]$DS,
  [string]$Sheet = "$PSScriptRoot\review_sheet.csv"
)
# Locate dataset_xmodule portably: script dir, parent dir, or current dir.
if(-not $DS){
  $DS = @("$PSScriptRoot\dataset_xmodule","$PSScriptRoot\..\dataset_xmodule",".\dataset_xmodule") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
}
if(-not $DS){ throw "dataset_xmodule not found. Pass -DS <path-to-dataset_xmodule>." }
$idx = Get-Content "$DS\index.json" -Raw | ConvertFrom-Json
$pool = $idx
if($Cwe){ $pool = $pool | Where-Object { $_.cwe -eq $Cwe } }
if($Boundary){ $pool = $pool | Where-Object { $_.boundary_type -eq $Boundary } }

$sel = @()
if($Id){ $sel = $idx | Where-Object { $_.id -eq $Id } }
elseif($Stratified -gt 0){ $sel = $idx | Group-Object cwe | ForEach-Object { $_.Group | Get-Random -Count ([Math]::Min($Stratified,$_.Count)) } }
elseif($Random -gt 0){ $sel = $pool | Get-Random -Count ([Math]::Min($Random,@($pool).Count)) }
else { $sel = $pool | Get-Random -Count 1 }

if(-not (Test-Path $Sheet)){ "id,cve,cwe,repo,boundary,sink_hit,verdict,notes" | Out-File $Sheet -Encoding utf8 }

foreach($s in $sel){
  $dir = Join-Path (Join-Path $DS $s.cwe) $s.id
  Write-Host ("`n" + ("="*90)) -ForegroundColor Cyan
  Write-Host ("{0}  |  {1}  |  {2}  |  {3}  |  boundary={4}  sink={5}" -f $s.id,$s.cve,$s.cwe,$s.repo,$s.boundary_type,$s.sink_hit) -ForegroundColor Yellow
  Write-Host ("Advisory : https://github.com/advisories/{0}" -f $s.id)
  Write-Host ("Commit   : https://github.com/{0}/commit/{1}" -f $s.repo,$s.fix_commit)
  Write-Host "`n-- evidence (why flagged cross-module) --"
  $s.evidence | ForEach-Object { Write-Host "   $_" }
  Write-Host "`n-- fix.diff (the patch) --" -ForegroundColor Green
  Get-Content (Join-Path $dir 'fix.diff') | Select-Object -First 60
  Write-Host "`n-- boundary in VULNERABLE file: include / extends / trait use --" -ForegroundColor Green
  Get-ChildItem (Join-Path $dir 'vuln') -File | ForEach-Object {
    Select-String -Path $_.FullName -Pattern '(include|require)(_once)?\b|class\s+\w+\s+extends|^\s+use\s+\w+\s*;' | Select-Object -First 12 | ForEach-Object { Write-Host ("   {0}:{1}: {2}" -f $_.Filename,$_.LineNumber,$_.Line.Trim()) }
  }
  Write-Host "`n-- tainted source usage ($ _GET/_POST/...) in VULNERABLE file --" -ForegroundColor Green
  Get-ChildItem (Join-Path $dir 'vuln') -File | ForEach-Object {
    Select-String -Path $_.FullName -Pattern '\$_(GET|POST|REQUEST|COOKIE|SERVER|FILES)' | Select-Object -First 8 | ForEach-Object { Write-Host ("   {0}:{1}: {2}" -f $_.Filename,$_.LineNumber,$_.Line.Trim()) }
  }
  # append review row (verdict left blank for you to fill)
  ("{0},{1},{2},{3},{4},{5},," -f $s.id,$s.cve,$s.cwe,$s.repo,$s.boundary_type,$s.sink_hit) | Add-Content $Sheet -Encoding utf8
}
Write-Host ("`nReview rows appended to {0} - fill the 'verdict' column (TP/FP) and 'notes'." -f $Sheet) -ForegroundColor Cyan
