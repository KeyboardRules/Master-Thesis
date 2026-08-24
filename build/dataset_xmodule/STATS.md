# STATS - Cross-Module PHP Vulnerability Dataset (heuristic stage)

Pipeline: OSV Packagist harvest -> taint-CWE filter -> git-based cross-module classifier -> pre/post-fix export.

- **Cross-module positive advisories: 977** (each with a matched negative = post-fix code)
- **File-level positive/negative pairs: 2320** (see samples.jsonl)
- **Distinct CWE types: 13** (requirement: >= 3)
- Distinct repositories: 290
- Vulnerable file contains the CWE-specific sink: 499 / 977
- Dropped for hygiene (merge-noise / vendor / test paths): 82
- Advisories classified: **1830 of 1830** taint-flow advisories (entire pool processed)

## Positives per CWE

| CWE | Name | Positives |
|---|---|---|
| CWE-79 | XSS | 485 |
| CWE-89 | SQLi | 111 |
| CWE-22 | Path Traversal | 65 |
| CWE-94 | Code Injection | 64 |
| CWE-434 | File Upload | 52 |
| CWE-502 | Deserialization | 44 |
| CWE-918 | SSRF | 44 |
| CWE-74 | Injection | 41 |
| CWE-611 | XXE | 23 |
| CWE-78 | OS Command | 20 |
| CWE-1336 | Template Inj | 16 |
| CWE-98 | File Include | 6 |
| CWE-73 | External File Ctrl | 6 |

## Positives per boundary (taint path crossing)

| Boundary | Count |
|---|---|
| include | 153 |
| inherit | 704 |
| include+inherit | 120 |

## Acceptance check

- >= 150 cross-module positives: **977 -> PASS**
- >= 3 CWE types: **13 -> PASS**
- Top-3 CWEs (CWE-79, CWE-89, CWE-22) alone = 661 positives.
- PHPVD/RealVul fallback + scope reduction: **not triggered** (threshold greatly exceeded).

_Labels are `heuristic_pending_ecpg`; final taint-path confirmation is the PHPJoy E-CPG stage (METHODOLOGY.md sec.6)._
