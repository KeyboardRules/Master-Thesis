# Consolidate per-sample dirs into a lean metadata JSONL (one row per changed PHP file).
# Code is NOT inlined; each row points to the on-disk vuln/fixed file (loader reads them).
param(
  [string]$DS  = "D:\Thesis\Thesis\Artifact\phpjoy_release\build\dataset_xmodule",
  [string]$Out = "D:\Thesis\Thesis\Artifact\phpjoy_release\build\dataset_xmodule\samples.jsonl"
)
$ErrorActionPreference = "Continue"
if(Test-Path $Out){ Remove-Item $Out }
$sb = New-Object System.Text.StringBuilder
$rows = 0
foreach($m in (Get-ChildItem $DS -Recurse -Filter meta.json)){
  $meta = Get-Content $m.FullName -Raw | ConvertFrom-Json
  $d = $m.Directory.FullName
  $rel = $d.Substring($DS.Length).TrimStart('\','/') -replace '\\','/'
  foreach($vf in (Get-ChildItem (Join-Path $d 'vuln') -File -ErrorAction SilentlyContinue)){
    $fixedRel = "$rel/fixed/$($vf.Name)"
    $hasFixed = Test-Path (Join-Path $d "fixed\$($vf.Name)")
    $rec = [ordered]@{
      id=$meta.id; cve=$meta.cve; cwe=$meta.cwe; repo=$meta.repo; fix_commit=$meta.fix_commit
      boundary_type=$meta.boundary_type; label_status=$meta.label_status; sink_hit=$meta.sink_hit
      file=($vf.Name -replace '__','/')
      positive_path="$rel/vuln/$($vf.Name)"
      negative_path=$(if($hasFixed){$fixedRel}else{$null})
      vuln_bytes=$vf.Length
    }
    [void]$sb.AppendLine(($rec | ConvertTo-Json -Depth 4 -Compress))
    $rows++
  }
}
[System.IO.File]::WriteAllText($Out, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
"Metadata rows (file-level pairs): $rows"
"Distinct advisories: $((Get-ChildItem $DS -Recurse -Filter meta.json).Count)"
"samples.jsonl size: {0:N0} KB" -f ((Get-Item $Out).Length/1KB)
