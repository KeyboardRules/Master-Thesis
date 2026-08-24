# Cross-Module PHP Vulnerability Dataset — Methodology

Companion dataset for **PHPJoy** (Enhanced Code Property Graph, E-CPG). The goal is a
labeled corpus of PHP CVEs whose taint path **crosses a file-`include` boundary or a
class-inheritance boundary**, i.e. exactly the cross-module cases PHPJoy targets and that
single-file analyzers miss.

## 1. Acceptance criteria (from the task)

| Requirement | Target | Where satisfied |
|---|---|---|
| PHP CVEs with **public fix commits** | — | OSV Packagist harvest (§2) |
| Taint path crosses **include OR inheritance** boundary | mandatory filter | Cross-module classifier (§4) |
| Verified **positive + matching negative** samples | few hundred | pre-fix / post-fix pairing (§5) |
| **≥150 cross-module positives** over **≥3 CWE types** | threshold | see `STATS.md` |
| Fallback to **PHPVD / RealVul** + scope reduction if short | contingency | §7 |

## 2. Data provenance — OSV.dev Packagist

Source: `https://osv-vulnerabilities.storage.googleapis.com/Packagist/all.zip`
(Packagist = the PHP/Composer ecosystem). No auth, structured, includes CWE ids, severity,
CVE aliases, and typed references (incl. `FIX` commits).

Funnel (`extract_osv.ps1` → `filter_taint.ps1`):

- 6767 Packagist advisories
- 3264 with a GitHub **fix commit** reference
- 3115 with fix commit **AND** a CWE id
- **1830** whose CWE is a **taint-flow** class, across **430 unique repos**

Access-control / info-leak CWEs (352 CSRF, 862/863/284/287 authz, 200 disclosure) are
excluded: they have no source→sink data flow, so a taint analyzer does not model them.

Taint-flow CWEs kept: 79 (XSS), 89 (SQLi), 94/95 (code inj), 22/73 (path traversal),
98 (file include), 78/90 (command/LDAP), 434 (upload), 502 (deserialize), 918 (SSRF),
611 (XXE), 74/1336 (injection/template).

## 3. Why git, not the GitHub API

Unauthenticated GitHub REST is 60 req/h — useless at this scale. Instead each fix commit
is obtained with a **shallow fetch of only that commit + its first parent**
(`git fetch --depth 2 origin <sha>`), which has **no rate limit**. `<sha>^1` is the
vulnerable (pre-fix) tree; `<sha>` is the patched tree.

## 4. Cross-module classification (`xmodule_analyze.ps1`)

Reuses the boundary detectors from `exporter/php_parser.py`:

- **MDG / include boundary** — the changed (sink) file issues `include`/`require[_once]`
  of project-local `.php`/`.inc` files. Strengthened when the fix spans ≥2 include-linked
  files, or the fix diff references a superglobal source (`$_GET/$_POST/...`).
- **CHG / inheritance boundary** — the sink lives in a `class` that **`extends` another
  class** (inherited method bodies carry data across files) or **`use`s a trait** inside
  its body. `implements <interface>` alone is **not** counted — interfaces have no code,
  so no taint can flow through them. Top-of-file `use Ns\Class;` namespace imports are
  **not** counted as inheritance (a bug we explicitly guard against).

Tiers emitted: `xmodule_include`, `xmodule_inherit`, `xmodule_include+inherit`, `intra`.
Only non-`intra` rows are positives.

## 5. Positive / negative labeling (`export_samples.ps1`)

For every cross-module positive:

- **positive** = vulnerable code = changed `.php` file(s) at `<sha>^1` → `vuln/`
- **negative** = fixed code = same file(s) at `<sha>` → `fixed/`
- plus `fix.diff` and `meta.json` (id, CVE, CWE, repo, sha, boundary_type, evidence).

This pre-fix/post-fix pairing is the standard patch-based labeling used by CVEfixes /
Devign / RealVul, giving a matched negative for each positive.

## 6. Label confidence — honest limitation

All labels are `label_status: heuristic_pending_ecpg`. The boundary detection is static
(regex MDG/CHG). **Confirming that the taint path itself traverses the boundary** requires
running the full PHPJoy E-CPG (PHP parser → `phpast2cpg.jar` → Neo4j → taint traversal in
`api-framework`). That toolchain (PHP 8 + Java 11 + Neo4j 4.4.4) is the verification stage;
the corpus here is its verified-candidate input. Each sample ships the exact repo + commit
so E-CPG verification is deterministic.

## 7. Fallback: PHPVD / RealVul + scope reduction

If confirmed cross-module positives fall below 150 over ≥3 CWEs after E-CPG verification:

1. **Supplement** from RealVul (synthesised PHP slices from NVD/SARD, XSS+SQLi) and PHPVD,
   re-running the §4 classifier to keep only their cross-module entries.
2. **Reduce scope** to the 3 best-supported CWEs (79, 89, 22) and report per-CWE counts,
   documenting the reduction rather than padding with intra-file samples.

## 8. Reproduce

```powershell
# 1. harvest
curl -L -o build/packagist_all.zip https://osv-vulnerabilities.storage.googleapis.com/Packagist/all.zip
Expand-Archive build/packagist_all.zip build/packagist
./build/extract_osv.ps1        # -> candidates_osv.json
./build/filter_taint.ps1       # -> candidates_taint.json  (1830 rows)
# 2. classify (batches; git-clone heavy, resumable by -Start/-Count)
./build/xmodule_analyze.ps1 -Start 0 -Count 400   # -> xmodule_results.jsonl + samples/
# 3. export labeled pos/neg pairs
./build/export_samples.ps1     # -> dataset_xmodule/<CWE>/<id>/{vuln,fixed,fix.diff,meta.json}
```
