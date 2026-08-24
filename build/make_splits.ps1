<#
Repo-level (grouped) + CWE-stratified train/val/test split for the cross-module dataset.

- GROUPED by repo: no repository appears in more than one split  -> no train/test leakage
  (a model can't memorise a project it also sees at test time).
- STRATIFIED by CWE: greedy assignment minimises L2 deviation of per-split per-CWE counts
  from their target proportions, so each split keeps a similar CWE mix.
- DETERMINISTIC: repos processed largest-first (ties by name); no randomness.

Ratios default 0.70 / 0.15 / 0.15. Output: dataset_xmodule/splits.json
#>
param(
  [double]$Train = 0.70, [double]$Val = 0.15, [double]$Test = 0.15,
  [string]$DS
)
if(-not $DS){ $DS = @("$PSScriptRoot\dataset_xmodule","$PSScriptRoot\..\dataset_xmodule",".\dataset_xmodule") |
  Where-Object { Test-Path $_ } | Select-Object -First 1 }
$idx = Get-Content "$DS\index.json" -Raw | ConvertFrom-Json
$splits = @('train','val','test'); $ratio = @{train=$Train; val=$Val; test=$Test}

# per-repo CWE histogram + total
$repoCwe = @{}; $repoTot = @{}
foreach($s in $idx){
  if(-not $repoCwe.ContainsKey($s.repo)){ $repoCwe[$s.repo]=@{}; $repoTot[$s.repo]=0 }
  $repoCwe[$s.repo][$s.cwe] = ([int]$repoCwe[$s.repo][$s.cwe]) + 1
  $repoTot[$s.repo] += 1
}
$cwes = ($idx.cwe | Sort-Object -Unique)
# per-CWE targets per split
$target = @{}; foreach($sp in $splits){ $target[$sp]=@{}; foreach($c in $cwes){ $target[$sp][$c] = ($idx|Where-Object{$_.cwe -eq $c}).Count * $ratio[$sp] } }

# running counts
$cur = @{}; foreach($sp in $splits){ $cur[$sp]=@{}; foreach($c in $cwes){ $cur[$sp][$c]=0.0 } }
$assign = @{}   # repo -> split

# process repos largest first (deterministic)
$order = $repoTot.GetEnumerator() | Sort-Object @{e={$_.Value};Descending=$true}, @{e={$_.Key}}
foreach($e in $order){
  $repo = $e.Key
  $best=$null; $bestCost=[double]::MaxValue
  foreach($sp in $splits){
    # tentative L2 deviation across ALL splits/cwes if this repo goes to $sp
    $cost=0.0
    foreach($sp2 in $splits){
      foreach($c in $cwes){
        $add = if($sp2 -eq $sp){ [double]([int]$repoCwe[$repo][$c]) } else { 0.0 }
        $dev = ($cur[$sp2][$c] + $add) - $target[$sp2][$c]
        $cost += $dev*$dev
      }
    }
    if($cost -lt $bestCost){ $bestCost=$cost; $best=$sp }
  }
  $assign[$repo]=$best
  foreach($c in $cwes){ $cur[$best][$c] += [double]([int]$repoCwe[$repo][$c]) }
}

# build id lists
$out = [ordered]@{}; foreach($sp in $splits){ $out[$sp] = [ordered]@{ repos=@(); ids=@() } }
foreach($s in $idx){ $sp=$assign[$s.repo]; $out[$sp].ids += $s.id }
foreach($repo in $assign.Keys){ $out[$assign[$repo]].repos += $repo }
foreach($sp in $splits){ $out[$sp].repos = @($out[$sp].repos | Sort-Object -Unique); $out[$sp].ids = @($out[$sp].ids | Sort-Object) }

$meta = [ordered]@{
  method='grouped-by-repo + CWE-stratified (greedy L2), deterministic'
  ratios=@{train=$Train;val=$Val;test=$Test}
  total_samples=$idx.Count; total_repos=$cwes.Count
  splits=$out
}
($meta | ConvertTo-Json -Depth 6) | Out-File "$DS\splits.json" -Encoding utf8

# ---- report ----
"Split summary (grouped by repo, no repo crosses splits):"
$rows=@()
foreach($sp in $splits){
  $rows += [pscustomobject]@{ split=$sp; repos=$out[$sp].repos.Count; samples=$out[$sp].ids.Count;
    pct=("{0:P1}" -f ($out[$sp].ids.Count/$idx.Count)) }
}
$rows | Format-Table -AutoSize
# leakage check
$allRepos = @(); foreach($sp in $splits){ $allRepos += $out[$sp].repos }
$overlap = ($allRepos | Group-Object | Where-Object Count -gt 1).Count
"Repo overlap across splits (must be 0): $overlap"
# per-CWE distribution
"`nPer-CWE counts per split:"
$tab=@()
foreach($c in ($cwes | Sort-Object)){
  $r=[ordered]@{CWE=$c}
  foreach($sp in $splits){ $r[$sp] = @($out[$sp].ids | Where-Object { $id=$_; ($idx|Where-Object{$_.id -eq $id}).cwe -eq $c }).Count }
  $tab += [pscustomobject]$r
}
$tab | Format-Table -AutoSize
"Written: $DS\splits.json"
