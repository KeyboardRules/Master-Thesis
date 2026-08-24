# How to Verify This Dataset

**Cross-Module PHP Vulnerability Dataset** — 977 real PHP CVEs (with public fix commits)
whose taint path crosses a file-`include` boundary or a class-inheritance boundary, each
paired with a matched negative (the post-fix code). Built from the OSV Packagist advisory
database. See `METHODOLOGY.md` for how it was constructed and `dataset_xmodule/STATS.md`
for full counts.

> **Label status.** Every sample is labeled `heuristic_pending_ecpg`. The cross-module
> boundary is detected *statically* (include / `extends` / trait-use). Whether the taint
> path *itself* traverses that boundary is confirmed at Level 3 below. Levels 1–2 need only
> `git` + PowerShell; Level 3 needs the PHPJoy toolchain.

## What you received

```
dataset_xmodule/            the dataset
  index.json                one record per positive advisory (metadata + evidence)
  samples.jsonl             file-level index (id, cwe, boundary, positive_path, negative_path)
  STATS.md                  counts + acceptance check
  dropped.json              advisories excluded for hygiene (merge-noise / vendor / tests)
  <CWE-xx>/<GHSA-id>/
    vuln/  <file>           POSITIVE = vulnerable code (fix commit's parent)
    fixed/ <file>           NEGATIVE = patched code (fix commit)
    fix.diff                the security patch
    meta.json               id, cve, cwe, repo, fix_commit, boundary_type, evidence
METHODOLOGY.md              construction method + acceptance mapping
VERIFY.md                   this file
scripts/                    all pipeline + verification scripts
  verify_provenance.ps1     Level 1
  review.ps1                Level 2
  extract_osv.ps1 filter_taint.ps1 xmodule_analyze.ps1 export_samples.ps1 consolidate.ps1
candidates_taint.json       the 1830 harvested candidates (for full reproduction)
```

## Level 1 — Provenance (authenticity): are these real CVEs, unaltered?

Re-downloads each fix commit straight from GitHub and confirms every `vuln/` and `fixed/`
file is **byte-identical** to the real `<sha>^1` (pre-fix) and `<sha>` (post-fix) blobs.
This proves nothing was fabricated. Needs only **git + internet**.

```powershell
cd scripts
.\verify_provenance.ps1 -Random 30      # spot-check 30 advisories (a few minutes)
.\verify_provenance.ps1 -All            # verify all 977 (slow)
```
Expect `PASS` for every advisory and `0 mismatched`. Results in `provenance_report.csv`.

## Level 2 — Manual security review (label precision: TP vs FP)

For a stratified sample, read the patch + code and judge whether each is a *true*
cross-module taint vulnerability. Needs only **PowerShell**.

```powershell
cd scripts
.\review.ps1 -Stratified 2              # ~26 samples, 2 per CWE, into review_sheet.csv
```
For each sample confirm, in the vulnerable file:
1. a **tainted source** (`$_GET/$_POST/...`) is present;
2. a **sink matching the CWE** exists and the `fix.diff` patches exactly that sink;
3. the **boundary** is real (file is composed via `include`/`require`, or the sink's class
   `extends` a parent / `use`s a trait);
4. plausibly the source→sink flow **crosses** that boundary (the part Level 3 confirms);
5. the **CVE is genuine** — open `https://github.com/advisories/<GHSA-id>` and the commit URL.

Mark `verdict` = TP/FP in `review_sheet.csv`; report **precision = TP/(TP+FP)**, ideally
split by `boundary_type` (`include` vs `inherit`).

## Level 3 — E-CPG taint verification (the definitive check)

Confirms the taint path actually traverses the boundary, using the PHPJoy Enhanced Code
Property Graph. Needs **PHP 8 + Java 11 + Neo4j 4.4.4** (see the main PHPJoy `README.md`).
For a given sample: check out `<repo>@<fix_commit>^1`, build its E-CPG, and run the taint
traversal from the source to the CWE sink; a positive is confirmed when the path includes an
`INCLUDE`/`REQUIRE` edge or an `EXTENDS`/`USE_TRAIT` edge. `meta.json` gives the exact
`repo` + `fix_commit` so this is deterministic.

## Reproduce from scratch (optional)

```powershell
curl -L -o packagist_all.zip https://osv-vulnerabilities.storage.googleapis.com/Packagist/all.zip
Expand-Archive packagist_all.zip packagist
scripts\extract_osv.ps1 ; scripts\filter_taint.ps1        # -> candidates_taint.json (1830)
scripts\xmodule_analyze.ps1 -Start 0 -Count 1830          # classify (git-clone heavy)
scripts\export_samples.ps1 ; scripts\consolidate.ps1      # -> dataset_xmodule/
```
