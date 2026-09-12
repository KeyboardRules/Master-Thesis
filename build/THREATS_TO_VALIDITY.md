# Threats to Validity

Limitations observed while actually executing the Phase-2 pipeline (E-CPG build → backward
slicing → hybrid linearization) over the 144-sample `test` split. Every figure below comes from
the real run, not from estimation. The run is finished; regenerate the figures with the
commands in §8 if the corpus is rebuilt.

**Final result of the `test`-split run: 91 of 144 samples completed (63%), 53 permanently
retired (37%).** Of the 91 completed, 73 produced slices and 18 produced none.

---

## 1. Construct validity — the sink model bounds what can be detected

**XSS (CWE-79) sinks are limited to bare `echo $var` / `print $var`.**
`graph_traversal_model.find_terminal()` special-cases `XSS` by first *removing* the
function-name sink list (`terminal_functions -= POTENTIAL_SINK_MODEL[XSS]`) and then collecting
only `AST_ECHO` / `AST_PRINT` nodes that contain at least one non-constant variable. Two
consequences:

- Output through a template engine (Twig, Blade, Smarty), a framework `Response`/`View`
  object, or a helper such as `printf` / `vprintf` is **never recognised as a sink**, so no
  slice is produced no matter how the taint flows.
- **All 18 completed samples that produced zero rows are CWE-79** — 100% of the empty results
  fall in this one CWE. Direct inspection of one such graph confirmed the cause rather than
  assuming it: the whole codebase contained exactly **one** `AST_ECHO` node, and it was
  `echo "<constant string>"` with zero variable descendants, so it correctly did not qualify.

This is a property of the inherited PHPJoy `vuln_model.py`, not a defect introduced here. It
was deliberately **left unchanged**: widening the XSS sink set mid-run would have made the
already-processed samples inconsistent with later ones, and internal consistency of the corpus
matters more for the comparison than a marginally larger sample count. The effect is a
**systematic under-count of XSS recall** that applies *equally to all three variants*
(cross-module, intra-file, no-slice), so it biases absolute recall downward but does not favour
any variant in the head-to-head comparison that the thesis claim rests on.

## 2. Internal validity — a baseline bug that would have invalidated the comparison

The `no-slice` baseline originally rendered as the literal string `"None"` — no code at all.
`linearize_function_text()` built it from `code_step.get_node_code(fn)`, which for
`AST_METHOD` / `AST_FUNC_DECL` returns the declaration's `name` property; this php-ast +
`Exporter.php` combination leaves that property empty, so it stringified to `"None"`.

Had this gone unnoticed, the headline result would have been the cross-module variant beating a
baseline that contained **zero code**, which is not a meaningful comparison. It is fixed (the
baseline now carries the real source text of the enclosing function), but the implication for
reproduction is important:

> **Any `no-slice` rows generated before 2026-09-11 are invalid and must be regenerated or
> discarded.** Do not mix them with rows produced after the fix.

**A second, larger internal-validity defect was found in the same area: the variants did not
share a seed set.** `build_ft_dataset` wrote its rows variant-by-variant (all cross-module
first, then intra-file, then no-slice). Large samples produce thousands of slices and each one
costs several Neo4j round-trips to linearise, so the per-checkout wall-clock budget frequently
expired part-way through — after the cross-module rows had been flushed but before the two
baselines' rows for those same seeds were ever produced. Measured on the partial corpus:
**cross-module 10 828 rows vs 6 306 for each baseline — a 4 522-row surplus**, spread over 7
samples.

Left in place this would have been fatal to the central claim: the cross-module variant would
have been trained and scored on strictly more data than the baselines it is compared against,
so any margin it showed could be attributed to data volume rather than to the method. The
three-variant design exists precisely to exclude that explanation.

Fixed by buffering all variants and writing them in a single operation, so a sample contributes
either all of its renderings or none. For corpora produced before that change,
`dedupe_ft_dataset.py` drops any sample id that is missing a variant (`--keep-unbalanced`
overrides, but should not be used for the headline numbers). **Verify parity before reporting
results**: the per-variant counts on the cleaned file must be approximately equal.

The same class of risk applies to `code_step.get_node_code` generally: it returns
`NOT_SUPPORT_FOR_<TYPE>` placeholders for node types it does not implement. Statement-level
types (`AST_ASSIGN`, `AST_BINARY_OP`, `AST_UNARY_OP`, the increment/decrement family) were added
during this work because without them a taint source such as `$x = $_GET['y']` rendered as a
placeholder and the `[SRC]` tagger — which matches on the rendered text — could never fire.
Container types (`AST_ARG_LIST`, `AST_PARAM`, `AST_STMT_LIST`, `AST_TOPLEVEL`, `AST_CLASS`)
still render as placeholders and appear as such in the slice text.

## 3. External validity — which projects are representable

**53 of 144 test samples (37%) could never be analysed on this hardware** and were retired
after repeated failures. This is the single largest limitation of the evaluation, and the loss
is not random — it is concentrated in exactly the kind of large, mature codebase the method
most needs to demonstrate itself on:

| Repository | Retired samples |
|---|---|
| yetiforcecompany/yetiforcecrm | 6 |
| opencart/opencart | 5 |
| YesWiki/yeswiki | 4 |
| shopware/core | 4 |
| magento/magento2 | 3 |
| AzuraCast/AzuraCast, torrentpier/torrentpier, roundcube/roundcubemail, composer/composer, modxcms/revolution | 2 each |
| joomla/joomla-cms, wikimedia/mediawiki-core, ezsystems/ezpublish-legacy, simplesamlphp/simplesamlphp, passbolt/passbolt_api, propelorm/Propel, daylightstudio/FUEL-CMS and others | 1 each |

By CWE: CWE-79 ×24, CWE-89 ×9, CWE-94 ×4, CWE-22 ×4, CWE-74 ×3, CWE-918 ×3, CWE-1336 ×3,
CWE-502 ×2, CWE-434 ×1.

Combined with §1, the attrition compounds for XSS specifically: of the CWE-79 samples in the
split, 24 were retired outright and a further 18 completed with no qualifying sink — so the
CWE-79 evidence is far thinner than the raw dataset counts suggest.

Three distinct causes, all in the toolchain rather than the method:

1. **Upstream `phpast2cpg.jar` crashes on modern PHP syntax.** Observed repeatedly:
   `java.lang.ClassCastException: ast.ASTNode cannot be cast to ast.expressions.ArgumentList`
   in `PHPCSVEdgeInterpreter.handleMethodCall`, and `… cannot be cast to
   ast.expressions.Identifier` in `handlePropertyGroup` — consistent with PHP 8 first-class
   callable syntax and typed/readonly properties. The jar ships as a prebuilt binary with no
   source in the artifact, so this is **not fixable** here.
2. **Memory ceiling.** The analysis box has 3.9 GB RAM. The JVM's default maximum heap is about
   a quarter of that (~950 MB), which was the single largest failure cause until it was raised
   to 2 GB (`JVM_HEAP_MB`); that change eliminated `OutOfMemoryError` entirely for mid-size
   repos, but the largest projects (Magento, MediaWiki, Roundcube) still exceed 2 GB during CPG
   construction.
3. **Analysis-time ceiling.** A per-checkout wall-clock budget (`PIPELINE_TIMEOUT_S`, 600 s)
   bounds the backward slicing. Very large graphs hit it and are abandoned.

**Conclusion to state in the thesis:** results generalise to small and medium PHP projects.
Behaviour on very large enterprise codebases is **not evidenced** by this evaluation.

## 4. Incomplete graphs even for samples that succeed

`Parser.php` skips any file it cannot parse, logging `[ERROR] … syntax error`, and continues.
A sample therefore can succeed with a CPG that is missing some of its files — for example
Magento checkouts consistently failed on `Match.php` (`unexpected token "match"`, a PHP 8
keyword). Taint paths through a skipped file are invisible, producing **false negatives that
are silent**. Any per-sample result should be read as a lower bound.

Relatedly, `AST_CLASS` nodes carry empty `name` / `classname` properties in this parser
combination. Class-hierarchy resolution was therefore reworked to follow the `EXTENDS` / `TRAIT`
relationship to its end node directly rather than looking the parent up by name (the name-based
lookup could never succeed). The functional path is correct, but `[UNIT … class=…]` headers in
the linearised output cannot show class names.

## 5. Data hygiene of `ft_dataset.jsonl`

- **Duplicate rows.** A sample whose second checkout fails is not recorded as done, so it is
  retried — but the rows its first checkout already flushed remain in the file and are written
  again. Byte-identical `vuln`/`fixed` renderings (when a fix touches code outside the slice)
  add more. At one measurement this was **6 695 of 22 849 rows (29%)**.
- **Partial samples.** Some ids have `vuln`-side rows with no matching `fixed`-side rows,
  breaking the intended 1:1 positive/negative pairing for those seeds.

Both must be handled before training: `python build/dedupe_ft_dataset.py --report-only` reports
them, `--in-place` removes the duplicates and reports which samples are still incomplete. **The
head-to-head F1 / PR-AUC numbers must be computed on the de-duplicated file**, otherwise
repeated rows silently weight some seeds far more than others.

## 6. Label provenance

Dataset labels originate from patch-based pre-fix / post-fix pairing and were published as
`label_status: heuristic_pending_ecpg` (see `METHODOLOGY.md` §6). The E-CPG confirmation —
comparing the slicer's `crosses_include` / `crosses_inherit` against each sample's heuristic
`boundary_type` — is only available for samples that actually produced a slice. The 53 retired
and 18 zero-row samples therefore **remain heuristically labelled and unconfirmed**, and should
not be counted as E-CPG-verified cross-module positives.

## 7. Do not subset on the `boundary` field of a row

It is tempting to report the cross-module advantage on "the `boundary != intra` rows", since
that is where the method is claimed to help. **That filter silently deletes the baseline.**
The `boundary` field records what the *slice* crossed, and the intra-file variant is defined by
forbidding cross-file steps, so every one of its rows is `boundary=intra` by construction:

| variant | intra | inherit | include | include+inherit |
|---|---|---|---|---|
| cross-module | 4 224 | 1 178 | 596 | 359 |
| **intra-file** | **6 306** | 0 | 0 | 0 |
| no-slice | 4 207 | 1 178 | 589 | 332 |

Filtering on it therefore yields a "comparison" in which intra-file contributes zero rows — an
artefact that would look like a total win for the proposed method.

Subset on the **sample's** ground-truth `boundary_type` from `dataset_xmodule/index.json`
instead. In this corpus every productive sample is already a cross-module positive by dataset
construction (73 of 73), so that subset is the whole corpus and the variants stay balanced:
cross-module 6 357, intra-file 6 306, no-slice 6 306.

## 8. Reproducing these figures


```bash
python build/dedupe_ft_dataset.py --report-only        # rows, duplicates, incomplete samples
python - <<'PY'
import json, collections, os
idx={s['id']:s for s in json.load(open('build/dataset_xmodule/index.json',encoding='utf-8-sig'))}
done=set(json.load(open('build/phase2_state.json')))
att=json.load(open('build/phase2_attempts.json')) if os.path.exists('build/phase2_attempts.json') else {}
rows=[json.loads(l) for l in open('build/ft_dataset.jsonl')]
wr={r['id'] for r in rows}; retired={k for k,v in att.items() if v>=3}
print('done',len(done),'productive',len(done&wr),'zero-row',len(done-wr),'retired',len(retired))
print('retired by repo',collections.Counter(idx[i]['repo'] for i in retired if i in idx))
print('zero-row by CWE',collections.Counter(idx[i]['cwe'] for i in (done-wr) if i in idx))
PY
grep -oE "java\.lang\.[A-Za-z]+(Error|Exception)" build/run_phase2_batch.log | sort | uniq -c
```
