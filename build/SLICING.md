# Backward Taint-Slicing over the E-CPG — Algorithm Spec (Week 9–16, step B2)

Goal: from each CWE **sink**, walk the E-CPG **backwards** along data/def-use, call,
**INCLUDE (MDG)** and **EXTENDS/TRAIT (CHG)** edges, collecting exactly the statements that
influence the tainted argument. The union of those statements is the **program slice** fed
to the linearizer (step B3). A slice is a **positive** iff a backward path reaches a taint
**source** without passing a **sanitizer**; the same seed with the taint killed / no source
reached yields a **negative**.

This reuses PHPJoy's models and traversal framework — it is a new *backward* subclass, not a
rewrite.

## 1. E-CPG schema actually used (from `api-framework/apis/const.py`)

Node props: `id, type, code, lineno, funcid, fileid, classid, name, childnum, flags`,
plus recorder marks `is_sink_trace`, `trace_id`.

Edges to traverse (reverse direction unless noted):

| Layer | Edge (`:TYPE`) | Meaning | Use in backward slice |
|---|---|---|---|
| PDG | `REACHES` (carries `var`) | data dependence def→use | **core** backward def-use |
| CFG | `FLOWS_TO` (`flowLabel`) | control flow | pull in guarding predicates (context) |
| CG | `CALLS` | caller→callee | inter-procedural: arg↔param binding |
| **MDG** | `INCLUDE` | includer→included file toplevel | cross-file scope (include boundary) |
| **CHG** | `EXTENDS`,`IMPLEMENTS`,`TRAIT` | class hierarchy | resolve inherited method / property def site |
| AST | `PARENT_OF` | syntax | expand a statement to its subtree for slicing |
| scope | `IS_FILE_OF`,`IS_FUNCTION_OF_AST` | file/func containment | locate enclosing unit |

## 2. Reuse map (do NOT re-implement)

| Need | Reuse from PHPJoy |
|---|---|
| source set | `vuln_model.POTENTIAL_SOURCE_MODEL` (`_POST,_GET,_REQUESTS,_COOKIE,_FILE`) |
| sink set per CWE | `vuln_model.POTENTIAL_SINK_MODEL[vuln_type]` |
| sanitizer set | `vuln_model.BASIC_SANITIZE_FUNCTIONS` + `EXTERNAL_SANITIZE_FUNCTIONS[vuln_type]` |
| seed-finding, arg-var extraction, CG arg↔param | `graph_traversal_model.GlobalPDGForwardTraversalWithModel`: `find_terminal`, `find_origin`, `find_sanitizer`, `get_all_arg_var`, `match_cg_dataflow` |
| worklist scaffold | `graph_traversal.BaseGraphTraversal` (`run`, `traversal`, `init_traversal`, recorder) |
| slice marking | node props `is_sink_trace` / `trace_id` (already in schema) |

Implement `GlobalBackwardSliceTraversal(GlobalPDGForwardTraversalWithModel)` that overrides
`init_traversal` (seed = sinks) and `traversal` (step **backwards**).

## 3. Algorithm

```
INPUT : ecpg (Neo4j), vuln_type
OUTPUT: for each sink occurrence -> Slice{nodes, edges, crosses_include, crosses_inherit, verdict}

sinks      = find_terminal(POTENTIAL_SINK_MODEL[vuln_type])      # seed nodes
sources    = POTENTIAL_SOURCE_MODEL
sanitizers = BASIC_SANITIZE_FUNCTIONS ∪ EXTERNAL_SANITIZE_FUNCTIONS[vuln_type]

for each sink S:
    # tainted symbols entering the sink = vars of its argument list
    seeds = {(v, S) for v in get_all_arg_var(S)}
    worklist = seeds ; visited = {} ; slice = {S}
    crosses_include = crosses_inherit = false ; reached_source = false ; killed = false

    while worklist:
        (var, node) = worklist.pop()
        if (var,node) in visited: continue
        visited.add((var,node))

        # (a) intra-procedural def-use: who last wrote `var` before `node`
        for def in reverse_REACHES(node, var):          # REACHES edge with .var == var, reversed
            slice.add(def); slice.add_edge(def→node)
            if is_sanitizer(def, sanitizers, var):      # find_sanitizer: def wraps var in a cleanser
                killed = true; continue                 # this path is sanitized -> prune
            if is_source(def, sources):                 # $_GET/$_POST/... assigned into var
                reached_source = true; slice.add(def); continue
            for v2 in rhs_vars(def): worklist.push((v2, def))

        # (b) inter-procedural (CG): var is a formal parameter -> jump to call sites
        if is_param(node, var):
            for call in reverse_CALLS(func_of(node)):    # callers
                arg = match_cg_dataflow(call, param_index(var))   # bind param->actual arg
                slice.add(call)
                for v2 in vars(arg): worklist.push((v2, call))

        # (c) MDG include boundary: var used here but defined at an included file's toplevel
        if undefined_in_scope(var, node):
            for inc in INCLUDE_edges_into(file_of(node)):   # files that include, or are included by, this file
                crosses_include = true
                for def in toplevel_defs(inc, var): worklist.push((var, def))

        # (d) CHG inheritance boundary: sink in a method / uses $this->prop or inherited method
        if in_method(node):
            C = class_of(node)
            for P in walk(EXTENDS ∪ TRAIT from C):           # method-resolution order
                crosses_inherit = true
                # inherited method body, or parent-set property definition
                for def in member_defs(P, var):  worklist.push((var, def))

    verdict = "positive" if (reached_source and not killed) else "negative"
    slice.crosses_include = crosses_include ; slice.crosses_inherit = crosses_inherit
    emit Slice
```

Notes:
- **Sanitizer = path kill.** If every backward path from the sink hits a sanitizer before a
  source, the sink is safe → negative. Keep an *unsanitized* witness path for positives.
- **Control context.** For each stmt kept, also pull its guarding predicate via one
  `FLOWS_TO` hop (so `if (!isset($_GET…))` guards appear in the slice) — improves LLM signal.
- **Cross-module flags** are set exactly when an `INCLUDE` (c) or `EXTENDS/TRAIT` (d) edge is
  traversed **on a source→sink path**. This is the **E-CPG confirmation** of the heuristic
  `boundary_type` label in the dataset — it closes the `heuristic_pending_ecpg` gap.

## 4. Termination & budgets

Worklist + `visited` on `(var,node)` guarantees termination. Bound blow-up with:
`MAX_DEPTH` call-depth (k-CFA, default k=3), `MAX_SLICE_NODES` (default 400),
`MAX_PATHS` per sink. Cache resolved MRO and include graph per file.

## 5. Output for the linearizer (step B3)

Per sink: the slice sub-graph `(nodes with {id,type,code,lineno,file,func,class}, edges with
{type,var})`, plus `verdict`, `crosses_include`, `crosses_inherit`, and the ordered witness
path source→…→sink. Cross-check every emitted sink function name against the NAVEX / TChecker
lists (step B2 companion table `SOURCES_SINKS_XCHECK.md`).

## 6. Baselines (needed for the F1/PR-AUC acceptance)

Produce three renderings of **the same sink** so the comparison is apples-to-apples:
1. **no-slice** — the whole enclosing function/file text.
2. **intra-file slice** — run the algorithm but **forbid steps (b/c/d)** that leave the file
   (no CG-across-files, no INCLUDE, no CHG). Misses cross-module taint by construction.
3. **cross-module slice** — the full algorithm above.

The thesis claim = (3) beats (1) and (2) on F1 / PR-AUC, strongest on samples whose
`boundary_type ≠ intra`.
