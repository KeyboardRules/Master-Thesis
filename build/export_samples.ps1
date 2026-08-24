<#
Export labeled positive/negative samples for cross-module candidates (v2, filtered).

positive = vulnerable code (changed .php file at fix-commit's parent)  -> vuln/
negative = fixed code      (same file at fix commit)                   -> fixed/

Filters (data hygiene):
  * drop generated/vendored/test paths (vendor, node_modules, dist, tests, *.min.*)
  * drop advisories whose *filtered* PHP change set is > $MaxFiles  -> merge/refactor
    noise (e.g. PR-merge commits diffed against first parent); logged to dropped.json
#>
param(
  [string]$Jsonl   = "D:\Thesis\Thesis\Artifact\phpjoy_release\build\xmodule_results.jsonl",
  [string]$Work    = "D:\Thesis\Thesis\Artifact\phpjoy_release\build\repos",
  [string]$OutRoot = "D:\Thesis\Thesis\Artifact\phpjoy_release\build\dataset_xmodule",
  [int]$MaxFiles   = 12
)
$ErrorActionPreference = "Continue"
if(Test-Path $OutRoot){ Remove-Item $OutRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $OutRoot | Out-Null

$rxNoise = [regex]'(?i)(^|/)(vendor|node_modules|dist|build|tests?|spec|fixtures?|examples?|assets|third[_-]?party)/|\.min\.'
$rows = Get-Content $Jsonl | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json }
$pos  = @($rows | Where-Object { $_.status -eq 'ok' -and $_.xmodule -and $_.xmodule -ne 'intra' })
"Cross-module positive advisories in results: $($pos.Count)"

$index   = New-Object System.Collections.ArrayList
$dropped = New-Object System.Collections.ArrayList
foreach($r in $pos){
  $parts = $r.repo -split '/'; $owner=$parts[0]; $repo=$parts[1]
  $dir = Join-Path $Work "$owner`__$repo"
  if(-not (Test-Path (Join-Path $dir ".git"))){ continue }
  $sha = $r.sha

  # hygiene filter on changed php files
  $files = @($r.changed_php | Where-Object { -not $rxNoise.IsMatch($_) })
  if($files.Count -eq 0){ [void]$dropped.Add([pscustomobject]@{id=$r.id;reason='all_files_noise';n=$r.changed_php.Count}); continue }
  if($files.Count -gt $MaxFiles){ [void]$dropped.Add([pscustomobject]@{id=$r.id;reason='too_many_files_merge_noise';n=$files.Count}); continue }

  $boundary = switch -Wildcard ($r.xmodule){ 'xmodule_include' {'include'} 'xmodule_inherit' {'inherit'} 'xmodule_include+inherit' {'include+inherit'} default {'unknown'} }
  $sampleDir = Join-Path (Join-Path $OutRoot $r.cwe) $r.id
  $vulnDir = Join-Path $sampleDir 'vuln'; $fixDir = Join-Path $sampleDir 'fixed'
  New-Item -ItemType Directory -Force -Path $vulnDir,$fixDir | Out-Null

  $wrote=0; $written=@()
  foreach($p in $files){
    $vuln = git -C $dir show "$sha^1:$p" 2>$null | Out-String
    $fix  = git -C $dir show "${sha}:$p"  2>$null | Out-String
    if([string]::IsNullOrEmpty($vuln)){ continue }
    $flat = ($p -replace '[\\/]','__')
    $vuln | Out-File (Join-Path $vulnDir $flat) -Encoding utf8 -NoNewline
    if(-not [string]::IsNullOrEmpty($fix)){ $fix | Out-File (Join-Path $fixDir $flat) -Encoding utf8 -NoNewline }
    $wrote++; $written += $p
  }
  if($wrote -eq 0){ Remove-Item $sampleDir -Recurse -Force -ErrorAction SilentlyContinue; continue }

  git -C $dir diff "$sha^1" $sha -- $written 2>$null | Out-File (Join-Path $sampleDir 'fix.diff') -Encoding utf8

  $meta = [ordered]@{
    id=$r.id; cve=$r.cve; cwe=$r.cwe; repo=$r.repo; fix_commit=$sha
    boundary_type=$boundary; xmodule_tier=$r.xmodule; label_status='heuristic_pending_ecpg'
    sink_hit=$r.sink_hit; changed_php=$written; evidence=$r.evidence
    positive='vuln/ (pre-fix, parent commit)'; negative='fixed/ (post-fix)'
  }
  ($meta | ConvertTo-Json -Depth 6) | Out-File (Join-Path $sampleDir 'meta.json') -Encoding utf8
  [void]$index.Add([pscustomobject]$meta)
}

($index   | ConvertTo-Json -Depth 6) | Out-File (Join-Path $OutRoot 'index.json') -Encoding utf8
($dropped | ConvertTo-Json -Depth 4) | Out-File (Join-Path $OutRoot 'dropped.json') -Encoding utf8
"`nExported cross-module positive samples: $($index.Count)   (dropped for hygiene: $($dropped.Count))"
"By CWE:";      $index | Group-Object cwe | Sort-Object Count -Descending | Select-Object Count,Name | Format-Table -AutoSize
"By boundary:"; $index | Group-Object boundary_type | Select-Object Count,Name | Format-Table -AutoSize
