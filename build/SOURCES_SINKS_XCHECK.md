# Sources / Sinks / Sanitizers — PHPJoy ↔ NAVEX ↔ TChecker (Week 9–16, step B1)

Reuse PHPJoy's taint model, cross-checked against two mature PHP taint analyzers, and patch
the gaps this comparison exposes.

- **PHPJoy** columns are the *exact* sets in `api-framework/apis/vuln_model.py`
  (`POTENTIAL_SOURCE_MODEL`, `POTENTIAL_SINK_MODEL`, `BASIC_/EXTERNAL_SANITIZE_FUNCTIONS`).
- **NAVEX** = Alhuzali et al., USENIX Sec 2018 (open source: `github.com/aalhuz/navex`).
- **TChecker** = Luo et al., CCS 2022 (open source: `github.com/cuc-sclab/TChecker`).
- NAVEX/TChecker columns reflect the vuln classes and representative functions from their
  papers/artifacts — **verify against their released config files** before citing exact lists.
  ✔ = covered, ➕ = has entries PHPJoy lacks, — = out of scope.

## 1. Sources (user-controlled input)

| Source | PHPJoy | NAVEX | TChecker | Note |
|---|---|---|---|---|
| `$_GET` | ✔ | ✔ | ✔ | |
| `$_POST` | ✔ | ✔ | ✔ | |
| `$_REQUEST` | ⚠ **`_REQUESTS`** | ✔ | ✔ | **PHPJoy typo** → never matches `$_REQUEST` |
| `$_COOKIE` | ✔ | ✔ | ✔ | |
| `$_FILES` | ⚠ **`_FILE`** | ✔ | ✔ | **PHPJoy typo** → misses `$_FILES` (upload CWE-434!) |
| `$_SERVER` (Referer/UA/Host/X-Forwarded) | ✖ | ✔ | ✔ | **missing** — header-based XSS/SSRF/SQLi |
| `$_ENV`, `$argv`, `getenv()` | ✖ | partial | ✔ | missing |
| `$_GET`-like framework input (`Request::input`, `$wpdb` reads) | ✖ | partial | ➕ | TChecker models WordPress/framework APIs |
| Stored/2nd-order (DB read → sink) | ✖ | ✔ | partial | NAVEX tracks stored XSS/SQLi |

**Action:** fix the two typos (`_REQUESTS`→`_REQUEST`, `_FILE`→`_FILES`), add `$_SERVER`
(at least Referer/User-Agent/Host/X-Forwarded-For), consider framework input adapters.

## 2. Sinks (by CWE / vuln class)

| Vuln class (CWE) | PHPJoy sink funcs (excerpt) | NAVEX | TChecker | Gaps to add to PHPJoy |
|---|---|---|---|---|
| SQLi (89) | `mysql_query,mysqli_query,pg_query,…,"query"` | ✔ | ✔ | PDO `->query/->exec/->prepare`, `$wpdb->query/get_results`, Doctrine `->executeQuery` |
| XSS (79) | `echo,print,printf,print_r,exit,die,vprintf` | ✔ | ✔ | `<?=` short-echo, `header('Location')`, Twig raw, `->assign` |
| Command inj (78) | `exec,system,shell_exec,passthru,proc_open,popen,pcntl_exec` | ✔ | ✔ | backtick operator `` `…` ``, `mb_send_mail`, `mail()` 5th arg |
| Code inj (94) | `eval,create_function,assert,array_map` | ✔ | ✔ | **`preg_replace` /e**, `call_user_func`, `ReflectionFunction`, `include`(dyn) |
| File include (98) | `include,require,include_once,require_once` | ✔ | ✔ | `eval` overlaps; virtual paths |
| Path traversal (22/73) | `fopen,dir,dirname,opendir,scandir` | ✔ | ✔ | `file_get_contents,readfile,file_put_contents,unlink,copy` (PHPJoy files them under separate classes) |
| File read/write/delete | `file,file_get_contents,readfile / file_put_contents,fwrite / unlink,rmdir` | ✔ | ✔ | consistent, keep |
| Upload (434) | `copy,fopen,move_uploaded_file` | partial | ✔ | tie to `$_FILES` source (see §1) |
| Deserialize / POI (502) | `unserialize` | — | ✔ | `yaml_parse`, `Serializable`, phar:// |
| SSRF (918) | `curl_exec,file_get_contents,fsockopen` | — | partial | `get_headers,fopen(url),curl_setopt(URL)` |
| Open redirect (601) | `header` | ✔ | partial | keep |
| XXE (611) | ✖ (no class) | — | partial | add: `simplexml_load_*,DOMDocument::load,xml_parse` |
| Template inj (1336) | ✖ | — | — | add Twig/Blade `->render` with unescaped |

**Action:** add PDO/`$wpdb`/ORM query sinks (big XSS/SQLi recall win), move `preg_replace`
from sanitizers to a code-injection sink when the `/e` modifier is present, add XXE + template
sink classes (the dataset already contains CWE-611 and CWE-1336 positives).

## 3. Sanitizers

| Aspect | PHPJoy | NAVEX | TChecker | Note |
|---|---|---|---|---|
| Escaping (context-correct) | `htmlspecialchars,htmlentities,strip_tags` (XSS); `*_real_escape_string,pg_escape_string` (SQLi); `escapeshellarg,escapeshellcmd` (cmd) — in `EXTERNAL_SANITIZE_FUNCTIONS` | ✔ | ✔ | **good, keep** — these are context-typed |
| Type/validation | `intval,floatval,is_numeric,ctype_*,filter_input` | ✔ | ✔ | valid for SQLi/path, **not** for XSS |
| Encoders lumped as sanitizers | `base64_encode,urlencode,gzencode,http_build_query,…` in `BASIC_SANITIZE_FUNCTIONS` | ✖ | ✖ | ⚠ **over-approx** — `urlencode` ≠ XSS-safe in HTML body; encoders aren't sanitizers |
| **Decoders in same set** | `base64_decode,html_entity_decode,urldecode,htmlspecialchars_decode` also present | ✖ | ✖ | ⚠ **bug** — decoders *re-taint*; treating them as sanitizers kills real flows (false negatives) |

**Action:** make sanitization **context-sensitive** (like `EXTERNAL_SANITIZE_FUNCTIONS`): a
function sanitizes only for a specific sink class. Remove decoders from the sanitizer set (or
model them as taint-*restorers*). Drop generic encoders from XSS sanitization.

## 4. Net effect on the pipeline

These fixes go into the **source/sink/sanitizer sets consumed by the backward slicer**
(`SLICING.md` §2). The typo fixes (§1) and decoder bug (§3) most directly affect recall:
without them the slicer silently misses `$_REQUEST`/`$_FILES` flows and kills paths through
decoders. Re-run the slicer after patching, then compare confirmed cross-module counts
against the dataset's heuristic `boundary_type` labels as a sanity check.
