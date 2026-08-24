# Filter harvested candidates to taint-flow CWEs and produce per-CWE / per-repo stats.
param(
  [string]$In  = "D:\Thesis\Thesis\Artifact\phpjoy_release\build\candidates_osv.json",
  [string]$Out = "D:\Thesis\Thesis\Artifact\phpjoy_release\build\candidates_taint.json"
)
$ErrorActionPreference = "Stop"
$all = Get-Content $In -Raw | ConvertFrom-Json

# Taint-flow (source -> sink) CWEs that PHPJoy's dataflow taint analysis targets.
$taintCwe = @('CWE-79','CWE-89','CWE-94','CWE-22','CWE-98','CWE-78','CWE-434',
              'CWE-502','CWE-918','CWE-91','CWE-611','CWE-74','CWE-90','CWE-95','CWE-73','CWE-1336')

$taint = @($all | Where-Object {
  $keep = $false
  foreach($c in $_.cwes){ if($taintCwe -contains $c){ $keep = $true; break } }
  $keep
})

# Attach a single primary CWE (first taint CWE) and flatten repo
foreach($r in $taint){
  $primary = $null
  foreach($c in $r.cwes){ if($taintCwe -contains $c){ $primary = $c; break } }
  $r | Add-Member -NotePropertyName primary_cwe -NotePropertyValue $primary -Force
  $fc = $r.fix_commits[0]
  $r | Add-Member -NotePropertyName repo_full -NotePropertyValue ("{0}/{1}" -f $fc.owner,$fc.repo) -Force
}

$taint | ConvertTo-Json -Depth 8 | Out-File $Out -Encoding utf8

"Taint-flow candidates (advisory-level): $($taint.Count)"
"Unique repos                          : $((@($taint.repo_full) | Sort-Object -Unique).Count)"
"`nPer primary CWE:"
$taint | Group-Object primary_cwe | Sort-Object Count -Descending | Select-Object Count,Name | Format-Table -AutoSize
"`nTop repos by candidate count:"
$taint | Group-Object repo_full | Sort-Object Count -Descending | Select-Object -First 20 Count,Name | Format-Table -AutoSize
