<#
Cross-module analyzer (git-based, no API rate limit).

For each candidate advisory it:
  1. Shallow-fetches only the fix commit + parent  (git fetch --depth 2 <sha>)
  2. Lists changed .php files and the fix diff
  3. Reads each changed file at the VULNERABLE (parent) version
  4. Applies MDG (include/require) + CHG (extends/implements/use trait) detection
     -- reusing the exporter's regex approach -- plus per-CWE sink detection
  5. Classifies a cross-module tier with transparent evidence.

All labels are HEURISTIC (pre-E-CPG). Final taint-path verification requires the
PHPJoy E-CPG toolchain; this stage produces the candidate corpus + evidence.

Output: build/samples/<GHSA>.json  and appends a row to build/xmodule_results.jsonl
#>
param(
  [int]$Start = 0,
  [int]$Count = 20,
  [string]$Cand   = "D:\Thesis\Thesis\Artifact\phpjoy_release\build\candidates_taint.json",
  [string]$Work   = "D:\Thesis\Thesis\Artifact\phpjoy_release\build\repos",
  [string]$OutDir = "D:\Thesis\Thesis\Artifact\phpjoy_release\build\samples",
  [string]$Jsonl  = "D:\Thesis\Thesis\Artifact\phpjoy_release\build\xmodule_results.jsonl"
)
$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Force -Path $Work,$OutDir | Out-Null
$all = Get-Content $Cand -Raw | ConvertFrom-Json
$slice = $all[$Start..([Math]::Min($Start+$Count-1,$all.Count-1))]

# ---- detection regexes (aligned with exporter/php_parser.py) ----
$rxInclude = [regex]'(?m)\b(include_once|require_once|include|require)\b\s*[^;]*?[''"]([^''"]+\.(?:php|inc))[''"]'
$rxClass   = [regex]'(?m)(?:(abstract|final)\s+)?(class|interface|trait)\s+(\w+)(?:\s+extends\s+([\w\\, ]+?))?(?:\s+implements\s+([\w\\, ]+?))?\s*\{'
# trait-use ONLY inside a class body (simple name, no backslash) -- matches exporter/php_parser.py.
# We scope by requiring the use-statement to appear AFTER the first class declaration.
$rxTraitUse = [regex]'(?m)^\s+use\s+(\w+(?:\s*,\s*\w+)*)\s*;'
$rxSuper   = [regex]'\$_(GET|POST|REQUEST|COOKIE|SERVER|FILES|SESSION)\b'
# per-CWE sink signatures
$sinks = @{
  'CWE-79'  = [regex]'(?i)\b(echo|print|printf|print_r|->assign|->render|<\?=)\b'
  'CWE-89'  = [regex]'(?i)(->query|mysqli?_query|->exec|->prepare|pg_query|->rawQuery|DB::(select|raw|statement)|->whereRaw)'
  'CWE-22'  = [regex]'(?i)\b(fopen|file_get_contents|file_put_contents|readfile|unlink|include|require|fpassthru|copy)\b'
  'CWE-94'  = [regex]'(?i)\b(eval|create_function|assert|preg_replace)\b'
  'CWE-78'  = [regex]'(?i)\b(system|exec|shell_exec|passthru|popen|proc_open)\b'
  'CWE-434' = [regex]'(?i)\b(move_uploaded_file)\b'
  'CWE-502' = [regex]'(?i)\b(unserialize)\b'
  'CWE-98'  = [regex]'(?i)\b(include|include_once|require|require_once)\b'
  'CWE-918' = [regex]'(?i)\b(curl_exec|file_get_contents|fsockopen|fopen|get_headers)\b'
  'CWE-611' = [regex]'(?i)(simplexml_load|DOMDocument|xml_parse|loadXML|LIBXML)'
}

function Ensure-Repo($owner,$repo){
  $dir = Join-Path $Work "$owner`__$repo"
  if(-not (Test-Path (Join-Path $dir ".git"))){
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    git -C $dir init -q 2>&1 | Out-Null
    git -C $dir remote add origin "https://github.com/$owner/$repo.git" 2>&1 | Out-Null
  }
  return $dir
}

$results = @()
foreach($c in $slice){
  $fc = $c.fix_commits[0]
  $owner=$fc.owner; $repo=$fc.repo; $sha=$fc.sha; $cwe=$c.primary_cwe
  $rec = [ordered]@{ id=$c.id; cve=($c.cves -join ','); cwe=$cwe; repo="$owner/$repo"; sha=$sha
                     status=$null; changed_php=@(); xmodule=$null; evidence=@() }
  try{
    $dir = Ensure-Repo $owner $repo
    $f = git -C $dir fetch --depth 2 origin $sha -q 2>&1
    if($LASTEXITCODE -ne 0){ $rec.status="fetch_fail"; $results+=,$rec;
      "$($c.id) [$cwe] $owner/$repo -> FETCH FAIL" ; continue }

    # diff against first parent -> also handles merge/PR commits correctly
    $changed = @(git -C $dir diff --name-only "$sha^1" $sha 2>$null)
    if($changed.Count -eq 0){ $changed = @(git -C $dir diff-tree --no-commit-id --name-only -r $sha 2>$null) }
    $php = @($changed | Where-Object { $_ -match '\.(php|inc|phtml|module|ctp)$' })
    $rec.changed_php = $php
    $rec | Add-Member changed_all $changed -Force
    if($php.Count -eq 0){ $rec.status="no_php_changed"; $results+=,$rec;
      "$($c.id) [$cwe] $owner/$repo -> no php changed (files: $($changed -join ', '))"; continue }

    $incBoundary=$false; $inheritBoundary=$false; $sinkHit=$false; $ev=@()
    # multi-file include-linked fix?
    if($php.Count -ge 2){ $ev += "fix touches $($php.Count) php files" }

    foreach($p in $php){
      # vulnerable (parent) version of the file
      $content = git -C $dir show "$sha^1:$p" 2>$null | Out-String
      if([string]::IsNullOrEmpty($content)){ continue }
      $incs = $rxInclude.Matches($content)
      $cls  = $rxClass.Matches($content)
      # Only a CLASS (or abstract class) that EXTENDS another class carries method
      # bodies across the boundary. `implements <interface>` alone does NOT (interfaces
      # have no code -> no taint flow). Trait `use` inside a class body also carries code.
      $hasExtends = $false; $parentName=$null
      foreach($m in $cls){
        $kind=$m.Groups[2].Value.ToLower(); $ext=$m.Groups[4].Value.Trim()
        if($kind -in @('class') -and $ext){ $hasExtends=$true; if(-not $parentName){ $parentName=$ext } }
      }
      $hasTraitUse=$false
      if($cls.Count -gt 0){
        $afterClass = $content.Substring($cls[0].Index)
        if($rxTraitUse.IsMatch($afterClass)){ $hasTraitUse=$true }
      }
      if($incs.Count -gt 0){ $incBoundary=$true; $ev += "$p includes $($incs.Count) project file(s)" }
      if($hasExtends){ $inheritBoundary=$true; $ev += "$p class extends $parentName" }
      if($hasTraitUse){ $inheritBoundary=$true; $ev += "$p class uses trait" }
      # sink presence in vulnerable file
      if($sinks.ContainsKey($cwe) -and $sinks[$cwe].IsMatch($content)){ $sinkHit=$true }
    }
    # diff hunk: does the fix add a sanitizer / touch superglobal?
    $diff = git -C $dir diff "$sha^1" $sha 2>$null | Out-String
    $touchesSuper = $rxSuper.IsMatch($diff)
    if($touchesSuper){ $ev += "fix diff references a superglobal source" }

    $tier = "intra"
    if($incBoundary -and ($php.Count -ge 2 -or $touchesSuper)){ $tier="xmodule_include" }
    if($inheritBoundary){ if($tier -eq "intra"){ $tier="xmodule_inherit" } else { $tier="xmodule_include+inherit" } }

    $rec.status="ok"; $rec.xmodule=$tier; $rec.evidence=$ev
    $rec | Add-Member sink_hit $sinkHit -Force
    $results += ,$rec
    ($rec | ConvertTo-Json -Depth 6) | Out-File (Join-Path $OutDir "$($c.id).json") -Encoding utf8
    "$($c.id) [$cwe] $owner/$repo -> $tier  (php=$($php.Count), sink=$sinkHit)"
  } catch {
    $rec.status="error:$($_.Exception.Message)"; $results+=,$rec
    "$($c.id) [$cwe] $owner/$repo -> ERROR $($_.Exception.Message)"
  }
}
# append jsonl
$results | ForEach-Object { ($_ | ConvertTo-Json -Depth 6 -Compress) } | Add-Content -Path $Jsonl -Encoding utf8
"`n=== batch done: $($results.Count) processed ($Start..$($Start+$Count-1)) ==="
$results | Group-Object { $_.xmodule } | Select-Object Count,Name | Format-Table -AutoSize
