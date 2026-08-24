# Cross-Module PHP Vulnerability Dataset

Labeled corpus of real PHP CVEs (public fix commits) whose taint path crosses a
**file-`include` boundary** or a **class-inheritance boundary** — the cross-module cases
PHPJoy's E-CPG targets. Built from the OSV Packagist advisory database via a git-only
pipeline (no GitHub API rate limits). **Entire taint-flow pool (1830 advisories) processed.**

## Headline numbers  (see `STATS.md`)

| Metric | Value |
|---|---|
| Cross-module **positive** advisories | **977** |
| File-level positive/negative pairs | 2320 |
| Distinct CWE types | **13** |
| Distinct repositories | 290 |
| Boundary: inherit / include / both | 704 / 153 / 120 |
| Acceptance (≥150 positives, ≥3 CWE) | **PASS** |

Top CWEs: XSS (485), SQLi (111), Path Traversal (65), Code Injection (64), File Upload (52),
Deserialization (44), SSRF (44), Injection (41), XXE (23), OS Command (20), Template-Inj (16),
File-Include (6), Ext-File-Control (6).

## Layout

```
dataset_xmodule/
├── index.json            # one record per positive advisory (metadata + evidence)
├── samples.jsonl         # lean file-level index: {id,cve,cwe,boundary,file,positive_path,negative_path}
├── dropped.json          # advisories excluded for hygiene (merge-noise / vendor / tests)
├── STATS.md              # full counts + acceptance check
└── <CWE-xx>/<GHSA-id>/
    ├── vuln/  <flattened path>   # POSITIVE  = vulnerable code (fix commit's parent)
    ├── fixed/ <flattened path>   # NEGATIVE  = patched code (fix commit)
    ├── fix.diff                  # the security patch
    └── meta.json                 # id, cve, cwe, repo, fix_commit, boundary_type, evidence
```

`vuln/` and `fixed/` file names are the repo-relative path with `/` → `__`.

## Labels

Each positive is paired with the post-fix version of the same file as its negative
(patch-based labeling, as in CVEfixes / RealVul). `boundary_type` records which boundary
the cross-module taint crosses:

- **include** — sink file pulls tainted data in through `include`/`require` of project files.
- **inherit** — sink lives in a class that `extends` a parent class or `use`s a trait
  (inherited method bodies carry the taint across files). Interface `implements` is *not*
  counted (no code, no flow).
- **include+inherit** — both boundaries present.

`label_status: heuristic_pending_ecpg` — boundary detection is static (MDG/CHG regex,
mirroring `exporter/php_parser.py`). **Confirming the taint path itself traverses the
boundary requires running the PHPJoy E-CPG toolchain** (PHP 8 → `phpast2cpg.jar` → Neo4j →
`api-framework` taint traversal). Every sample ships its exact repo + commit so that
verification is deterministic. See `../METHODOLOGY.md`.

## Reproduce

Pipeline scripts live in `build/`: `extract_osv.ps1` → `filter_taint.ps1` →
`xmodule_analyze.ps1` (all 1830 taint-flow candidates processed) → `export_samples.ps1` →
`consolidate.ps1`. Fallback to PHPVD/RealVul (METHODOLOGY §7) was **not required**.
