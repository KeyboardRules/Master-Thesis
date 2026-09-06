"""
Hybrid linearization: Slice -> text record for Qwen2.5-Coder (thesis step B3).

Consumes `Slice` objects from `apis.backward_slice` and renders the hybrid format defined in
LINEARIZATION.md: a code-sequential [SLICE] block (with role tags, the tainted symbol ⟦t⟧,
and explicit [INCLUDE→]/[INHERIT→] boundary hops) plus a graph-structural [EDGES] block of
def-use / call / include / inherit triples over local ids n0,n1,…. Then wraps it in the
Qwen2.5 chat template whose assistant target ends in a single scored label token.

Produces, per sink seed, up to 3 ablation renderings so F1/PR-AUC compare on identical seeds:
  variant="cross-module"  full slice (INCLUDE/EXTENDS hops kept)      -> our method
  variant="intra-file"    slice built with intra_file_only=True        -> baseline 2
  variant="no-slice"      whole enclosing function text, no [EDGES]     -> baseline 1

NOTE: written against the real API + the Slice class in backward_slice.py, NOT executed here
(no Neo4j/Python in the authoring env). Live-graph assumptions are marked `# VERIFY`.
"""
import json
import re
from typing import Dict, List, Optional

from apis.const import NODE_INDEX, NODE_CODE, NODE_LINENO, NODE_TYPE, NODE_FUNCID, NODE_CLASSID
from apis.vuln_model import (
    POTENTIAL_SOURCE_MODEL, POTENTIAL_SINK_MODEL, BASIC_SANITIZE_FUNCTIONS,
    EXTERNAL_SANITIZE_FUNCTIONS, VULN_TYPE_ID_TO_STRING,
)

SYSTEM_PROMPT = (
    "You are a PHP taint-analysis judge. Given a program slice (code + data-flow edges), "
    "decide if untrusted input reaches the sink unsanitized."
)
_SUPERGLOBAL_RE = re.compile(r"\$_(?:GET|POST|REQUEST|COOKIE|FILES|SERVER|ENV)\b")


# ------------------------------------------------------------------ node helpers ---------
def _attr(node, key, default=None):
    try:
        v = node[key]
        return v if v is not None else default
    except Exception:
        try:
            return node.get(key, default)
        except Exception:
            return default


def _code(af, node) -> str:
    try:
        return (af.code_step.get_node_code(node) or "").strip()
    except Exception:
        return str(_attr(node, NODE_CODE, "")).strip()


def _unit(af, node) -> Dict[str, str]:
    """(file, func, class) labels for the UNIT header."""
    try:
        f = af.fig_step.get_belong_file(node) or "?"
    except Exception:
        f = "?"
    funcid = _attr(node, NODE_FUNCID)
    func, klass = "<toplevel>", None
    if funcid is not None:
        fn = None
        try:
            fn = af.get_node_itself(funcid)
        except Exception:
            fn = None
        if fn is not None:
            func = _attr(fn, "name", None) or _attr(fn, NODE_CODE, None) or "<func>"
            # the method's own `classid` prop is the node id of its enclosing AST_CLASS node
            # (set by Exporter.php when it descends into a class; confirmed via php2ast source)
            try:
                classid = _attr(fn, NODE_CLASSID)
                cnode = af.get_node_itself(classid) if classid else None
                if cnode is not None and str(_attr(cnode, NODE_TYPE, "")).endswith("CLASS"):
                    klass = _attr(cnode, "name", None) or _attr(cnode, NODE_CODE, None)
            except Exception:
                pass
    return {"file": str(f), "func": str(func), "class": klass}


def _role(af, node, sink_id: int, sink_funcs: set, san_funcs: set) -> Optional[str]:
    code = _code(af, node)
    if _attr(node, NODE_INDEX) == sink_id:
        return "SNK"
    if _SUPERGLOBAL_RE.search(code):
        return "SRC"
    if any(re.search(r"\b" + re.escape(fn) + r"\s*\(", code) for fn in san_funcs):
        return "SAN"
    if any(re.search(r"\b" + re.escape(fn) + r"\s*\(", code) for fn in sink_funcs):
        return "SNK"
    return None


def _tainted_symbol(edges_into: List[dict]) -> str:
    for e in edges_into:
        if e.get("var"):
            return "$" + e["var"].split(",")[0].lstrip("$")
    return ""


# ------------------------------------------------------------------ core render ----------
def linearize_slice(sl, af, cwe: str, vuln_type, max_chars: int = 8000,
                    include_edges: bool = True) -> str:
    """Render one Slice into the hybrid [SLICE]/[EDGES] record (LINEARIZATION.md §3).

    include_edges=False drops the [EDGES] block -> code-only rendering (ablation A3).
    """
    sink_id = sl.sink[NODE_INDEX]
    sink_funcs = set(POTENTIAL_SINK_MODEL.get(VULN_TYPE_ID_TO_STRING.get(vuln_type), set()))
    san_funcs = set(BASIC_SANITIZE_FUNCTIONS)
    vt = VULN_TYPE_ID_TO_STRING.get(vuln_type)
    if vt in EXTERNAL_SANITIZE_FUNCTIONS:
        san_funcs |= set(EXTERNAL_SANITIZE_FUNCTIONS[vt])

    # ordering: witness path source->sink; fall back to (file,lineno)
    order = sl.witness if sl.witness else sorted(
        sl.nodes.keys(),
        key=lambda i: (str(_unit(af, sl.nodes[i])["file"]), _attr(sl.nodes[i], NODE_LINENO, 0) or 0),
    )
    # never drop the sink
    if sink_id not in order:
        order = order + [sink_id]

    # incoming edges per node (for tainted-symbol + boundary lookup)
    in_edges: Dict[int, List[dict]] = {}
    for e in sl.edges:
        in_edges.setdefault(e["dst"], []).append(e)

    # local id map (assigned in emission order)
    local: Dict[int, str] = {}

    def lid(nid: int) -> str:
        if nid not in local:
            local[nid] = f"n{len(local)}"
        return local[nid]

    trace = _tainted_symbol([e for nid in order for e in in_edges.get(nid, [])])
    lines = [f"<META> cwe={cwe} boundary={sl.boundary_type} vartrace=⟦t⟧{trace or '$?'}", "[SLICE]"]

    prev_unit = None
    prev_id = None
    for nid in order:
        node = sl.nodes.get(nid)
        if node is None:
            continue
        u = _unit(af, node)
        # boundary hop marker between consecutive witness nodes
        if prev_id is not None:
            hop = next((e for e in in_edges.get(nid, []) if e["src"] == prev_id), None) \
                  or next((e for e in in_edges.get(prev_id, []) if e["src"] == nid), None)
            if hop and hop["rel"] == "INCLUDE":
                lines.append(f"[INCLUDE→ {u['file']}]")
            elif hop and hop["rel"] in ("EXTENDS", "TRAIT"):
                lines.append(f"[INHERIT→ {u.get('class') or '?'}::{u['func']}]")
        # unit header on change
        cur_unit = (u["file"], u["func"], u.get("class"))
        if cur_unit != prev_unit:
            cls = f" class={u['class']}" if u.get("class") else ""
            lines.append(f"[UNIT file={u['file']} func={u['func']}{cls}]")
            prev_unit = cur_unit
        # the code line
        role = _role(af, node, sink_id, sink_funcs, san_funcs)
        tag = f"[{role}] " if role else ""
        code = _code(af, node)
        if trace:                                   # mark the tainted symbol inline
            code = re.sub(r"(?<![\w$])" + re.escape(trace) + r"\b", "⟦t⟧" + trace, code)
        ln = _attr(node, NODE_LINENO, "?")
        lines.append(f" {lid(nid)} [Ln {ln}] {tag}{code}")
        prev_id = nid

    lines.append("[/SLICE]")
    # EDGES block (graph-structural half of the hybrid) -- omitted for ablation A3
    if include_edges:
        lines.append("[EDGES]")
        for e in sl.edges:
            if e["src"] in local and e["dst"] in local:
                rel = e["rel"] + (f"({e['var']})" if e.get("var") else "")
                lines.append(f" {local[e['src']]} -{rel}-> {local[e['dst']]}")
        lines.append("[/EDGES]")

    text = "\n".join(lines)
    if len(text) > max_chars:                       # crude budget guard; see §4 for node-drop policy
        text = text[:max_chars] + "\n[TRUNCATED]"
    return text


def linearize_function_text(sink_node, af, cwe: str) -> str:
    """Baseline-1 'no-slice': whole enclosing function/file text, no EDGES block."""
    funcid = _attr(sink_node, NODE_FUNCID)
    try:
        fn = af.get_node_itself(funcid) if funcid is not None else None
        body = af.code_step.get_node_code(fn) if fn is not None else _code(af, sink_node)
    except Exception:
        body = _code(af, sink_node)
    return f"<META> cwe={cwe} boundary=intra variant=no-slice\n[SLICE]\n{body}\n[/SLICE]"


# ------------------------------------------------------------------ chat wrapping --------
def to_chat_example(record_text: str, sl, cwe: str, split: str, sample_id: str,
                    variant: str) -> dict:
    """Wrap a rendered record into a QLoRA SFT row (prompt + scored target)."""
    label = getattr(sl, "verdict", "SAFE")
    boundary = getattr(sl, "boundary_type", "intra")
    prompt = (
        f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n{record_text}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    target = f"verdict={label} cwe={cwe} boundary={boundary}"
    return {
        "id": sample_id, "cwe": cwe, "boundary": boundary, "variant": variant,
        "label": label, "split": split, "prompt": prompt, "target": target,
    }


# ------------------------------------------------------------------ orchestration --------
def build_ft_dataset(af, vuln_type, cwe: str, sample_id: str, split: str,
                     out_fp, variants=("cross-module", "intra-file", "no-slice"),
                     include_edges: bool = True):
    """
    Run the slicer on the (already-loaded) E-CPG and append one JSONL row per variant per
    sink to `out_fp` (an open file handle). Positives come from a vuln/ E-CPG, negatives from
    the matching fixed/ E-CPG — the caller decides which graph is loaded. Join `split` from
    dataset_xmodule/splits.json (repo-grouped) so there is no train/test leakage.
    """
    from apis.backward_slice import run_slicing        # local import to avoid cycles
    rows = 0
    full = run_slicing(af, vuln_type) if ("cross-module" in variants or "no-slice" in variants) else []
    intra = run_slicing(af, vuln_type, intra_file_only=True) if "intra-file" in variants else []

    if "cross-module" in variants:
        for sl in full:
            txt = linearize_slice(sl, af, cwe, vuln_type, include_edges=include_edges)
            out_fp.write(json.dumps(to_chat_example(txt, sl, cwe, split, sample_id, "cross-module")) + "\n"); rows += 1
    if "intra-file" in variants:
        for sl in intra:
            txt = linearize_slice(sl, af, cwe, vuln_type, include_edges=include_edges)
            out_fp.write(json.dumps(to_chat_example(txt, sl, cwe, split, sample_id, "intra-file")) + "\n"); rows += 1
    if "no-slice" in variants:
        for sl in full:                                # reuse full slices' sink seeds
            txt = linearize_function_text(sl.sink, af, cwe)
            out_fp.write(json.dumps(to_chat_example(txt, sl, cwe, split, sample_id, "no-slice")) + "\n"); rows += 1
    return rows
