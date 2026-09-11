"""
Backward taint-slicing over the E-CPG (thesis step B2).

Seeds at each CWE **sink**, walks the E-CPG **backwards** along
  - PDG def-use   (REACHES, reversed)  -> intra-procedural data dependence
  - CG            (CALLS, reversed)     -> inter-procedural (sink param -> caller arg)
  - MDG           (INCLUDE)             -> cross-FILE scope (include boundary)
  - CHG           (EXTENDS / TRAIT)     -> cross-CLASS resolution (inheritance boundary)
and collects the statements that influence the tainted sink argument = the program **slice**
fed to the hybrid linearizer (step B3, see LINEARIZATION.md).

Design: this reuses `BaseGraphTraversal.run()` unchanged. That engine already
    seed(origin) -> expand(traversal) -> kill on sanitizer -> record on terminal.
We simply (a) seed the worklist with SINK nodes, (b) make `traversal()` step BACKWARD, and
(c) set the *terminal* rule to "node is a taint source". A recorded terminal therefore means a
source->...->sink witness path exists; if every path is cut by a sanitizer first, none is
recorded => the sink is safe (negative).

Model reuse (unchanged sets from vuln_model.py, already patched):
    sources  = POTENTIAL_SOURCE_MODEL
    sinks    = POTENTIAL_SINK_MODEL[vuln_type]
    sanitize = BASIC_SANITIZE_FUNCTIONS (+ EXTERNAL_SANITIZE_FUNCTIONS[vuln_type])

Confirmed AnalysisFramework API used (see analysis_framework.py / steps/*):
    find_pdg_def_nodes, find_pdg_use_nodes, pdg_step.get_related_vars,
    find_cg_call_nodes, find_cg_decl_nodes,
    find_fig_include_src, find_fig_include_dst, fig_step.get_belong_file,
    fig_step.get_toplevel_file_first_statement,
    chg_step.get_class_defined_node_by_name,
    filter_ast_child_nodes, get_ast_root_node, get_ast_parent_node, get_node_itself,
    code_step.get_node_code, match_relationship.

NOTE: this file is written against the real API but has NOT been executed here (no Neo4j in
the authoring environment). Points that need a live E-CPG to confirm are marked `# VERIFY`.
"""
import logging
from collections import defaultdict, deque
from typing import Dict, List, Set

from apis.graph_traversal_model import GlobalPDGForwardTraversalWithModel
from apis.const import (
    NODE_INDEX, NODE_TYPE, NODE_FUNCID, NODE_CODE, NODE_CHILDNUM, NODE_LINENO, NODE_CLASSID,
    TYPE_PARAM, TYPE_ARG_LIST, TYPE_VAR, TYPE_ASSIGN, TYPE_METHOD,
    EXTENDS_EDGE, TRAIT_EDGE,
)

logger = logging.getLogger(__name__)


class Slice:
    """One backward slice rooted at a single sink occurrence."""
    def __init__(self, sink_node):
        self.sink = sink_node
        self.nodes: Dict[int, object] = {sink_node[NODE_INDEX]: sink_node}
        self.edges: List[dict] = []                 # {src, dst, rel, var}
        self.crosses_include = False
        self.crosses_inherit = False
        self.reached_source = False
        self.sanitized = False
        self.witness: List[int] = []                # source -> ... -> sink node ids

    @property
    def verdict(self) -> str:
        return "VULNERABLE" if (self.reached_source and not self.sanitized) else "SAFE"

    @property
    def boundary_type(self) -> str:
        if self.crosses_include and self.crosses_inherit:
            return "include+inherit"
        if self.crosses_include:
            return "include"
        if self.crosses_inherit:
            return "inherit"
        return "intra"

    def add(self, node):
        self.nodes.setdefault(node[NODE_INDEX], node)

    def add_edge(self, src, dst, rel, var=""):
        self.add(src); self.add(dst)
        self.edges.append({"src": src[NODE_INDEX], "dst": dst[NODE_INDEX], "rel": rel, "var": var})


class GlobalBackwardSliceTraversal(GlobalPDGForwardTraversalWithModel):
    """
    Backward taint slicer. Reuses the model setup of GlobalPDGForwardTraversalWithModel
    (origin=sources, terminal=sinks, sanitizer) but drives the engine backwards from sinks.
    """

    def __init__(self, *args, **kwargs):
        self.intra_file_only = kwargs.pop("intra_file_only", False)   # ablation: baseline 2
        self.disable_include = kwargs.pop("disable_include", False)   # ablation A2: drop MDG step
        self.disable_inherit = kwargs.pop("disable_inherit", False)   # ablation A2: drop CHG step
        self.with_control_context = kwargs.pop("with_control_context", True)  # ablation A5
        self.max_slice_nodes = kwargs.pop("max_slice_nodes", 400)
        super().__init__(*args, **kwargs)

        # --- flip the engine to backward: seed from SINKS, terminate on SOURCES -----------
        self._source_ids: Set[int] = set(self.origin_node_id)         # source assign-node ids
        self.origin = list(self.terminal_node)                        # seed = sink nodes
        for s in self.origin:
            s['origin'] = s[NODE_INDEX]
        # terminal rule fires when a candidate is a taint source (backward goal reached)
        self.terminal = [lambda n, **kw: n[NODE_INDEX] in self._source_ids]
        # self.sanitizer is already the sanitizer predicate from the parent (path kill)

        # per-seed (per-sink) bookkeeping
        self._slices: Dict[int, Slice] = {s[NODE_INDEX]: Slice(s) for s in self.origin}
        self._include_cache: Dict[int, list] = {}

    # ------------------------------------------------------------------ helpers ----------
    def _slice_of(self, node) -> Slice:
        return self._slices.setdefault(
            node['origin'], Slice(self.analysis_framework.get_node_itself(node['origin']))
        )

    def _rel_var(self, def_node, use_node) -> str:
        try:
            vs = self.analysis_framework.pdg_step.get_related_vars(def_node, use_node)
            return ",".join(vs) if vs else ""
        except Exception:            # VERIFY: signature/behaviour on live graph
            return ""

    # --- MDG: variable used here but defined in an adjacent (included/including) file -----
    def _backward_include(self, node) -> list:
        if self.intra_file_only or self.disable_include:   # ablation A2
            return []
        results = []
        try:
            # INCLUDE relationships connect Filesystem (`type="File"`) nodes, not the AST
            # nodes themselves -- resolve `node`'s own Filesystem node first, then walk
            # INCLUDE to neighboring Filesystem nodes, then FILE_OF to their AST_TOPLEVEL.
            fs_node = self.analysis_framework.get_fig_filesystem_node(node)
            if fs_node is None:
                return []
            includers = self.analysis_framework.find_fig_include_src(fs_node)   # files that include this one
            included = self.analysis_framework.find_fig_include_dst(fs_node)    # files this one includes
            for f in list(includers) + list(included):
                top_ast = self.analysis_framework.fig_step.get_node_from_file_system(f)
                top = self.analysis_framework.fig_step.get_toplevel_file_first_statement(top_ast)
                if top is not None:
                    results.append(top)
        except Exception:
            return []
        if results:
            sl = self._slice_of(node)
            sl.crosses_include = True
            for r in results:
                sl.add_edge(r, node, "INCLUDE")
        return results

    # --- CHG: sink in a method -> pull defs from parent class / used traits --------------
    def _backward_inherit(self, node) -> list:
        if self.intra_file_only or self.disable_inherit:   # ablation A2
            return []
        # is the enclosing function a method?
        func = self.analysis_framework.get_node_itself(node[NODE_FUNCID]) if node[NODE_FUNCID] is not None else None
        if func is None or func[NODE_TYPE] != TYPE_METHOD:
            return []
        results = []
        try:
            # the method's own `classid` prop is the node id of its enclosing AST_CLASS node
            # (set by Exporter.php when it descends into a class; confirmed via php2ast source)
            class_node = self.analysis_framework.get_node_itself(func[NODE_CLASSID])
            for rel_type in (EXTENDS_EDGE, TRAIT_EDGE):
                for rel in self.analysis_framework.match_relationship(
                        nodes=(class_node, None), r_type=rel_type):
                    # rel.end_node IS the resolved parent class/trait node already (confirmed
                    # on the live graph); going through get_class_defined_node_by_name(name)
                    # is both unnecessary and broken here since this php-ast/Exporter.php
                    # combo leaves AST_CLASS `name`/`code` empty.
                    if rel.end_node is not None:
                        results.append(rel.end_node)
        except Exception:            # VERIFY on live graph
            return []
        if results:
            sl = self._slice_of(node)
            sl.crosses_inherit = True
            for r in results:
                sl.add_edge(r, node, "EXTENDS")
        return results

    # --- CG backward: node is a formal parameter -> jump to every call site's argument ---
    def _backward_cg(self, node) -> list:
        if self.intra_file_only or node[NODE_TYPE] != TYPE_PARAM:
            return []
        results = []
        decl = self.analysis_framework.get_node_itself(node[NODE_FUNCID])    # enclosing function decl
        if decl is None:
            return []
        try:
            call_nodes = self.analysis_framework.find_cg_call_nodes(decl)    # callers of this function
        except Exception:
            call_nodes = []
        idx = node[NODE_CHILDNUM]
        for call in call_nodes:
            for arg_list in self.analysis_framework.filter_ast_child_nodes(call, node_type_filter=[TYPE_ARG_LIST]):
                arg = self.analysis_framework.get_ast_ith_child_node(arg_list, idx, ignore_error_flag=True)
                if arg is not None:
                    results.append(arg)
                    self._slice_of(node).add_edge(arg, node, "CALLS")
        return results

    # --- control context (ablation A5): pull the guarding predicate via one control hop --
    def _backward_control(self, node) -> list:
        cur = node
        for _ in range(6):                       # bounded upward search for an enclosing control
            try:
                cur = self.analysis_framework.get_ast_parent_node(cur, ignore_error_flag=True)
            except Exception:
                cur = None
            if cur is None:
                return []
            try:
                cond = self.analysis_framework.get_control_node_condition(cur, ignore_error=True)  # VERIFY
            except Exception:
                cond = None
            if cond is not None:
                self._slice_of(node).add_edge(cond, node, "FLOWS_TO")
                return [cond]
        return []

    # ------------------------------------------------------------------ traversal --------
    def traversal(self, node, *args, **kwargs):
        """Return backward predecessors of `node` across PDG / CG / MDG / CHG (+ control)."""
        sl = self._slice_of(node)
        if len(sl.nodes) >= self.max_slice_nodes:
            return []
        sl.add(node)
        if node[NODE_INDEX] in self._source_ids:
            sl.reached_source = True                      # witness reaches a source

        result = []
        # (a) intra-procedural def-use: definitions that REACH this node (backward)
        for d in self.analysis_framework.find_pdg_def_nodes(node):
            sl.add_edge(d, node, "REACHES", self._rel_var(d, node))
            result.append(d)
        # (b) inter-procedural: parameter -> caller arguments
        result.extend(self._backward_cg(node))
        # (c) MDG include boundary: only cross into an included/including file once (a) and
        # (b) found no local/CG predecessor -- a proxy for "undefined_in_scope(var, node)"
        # (SLICING.md sec 3(c)); avoids pulling in an include-hop on every single node.
        if not result:
            result.extend(self._backward_include(node))
        # (d) CHG inheritance boundary
        result.extend(self._backward_inherit(node))
        # (e) control context (ablation A5)
        if self.with_control_context:
            result.extend(self._backward_control(node))
        return result

    # ------------------------------------------------------------------ output -----------
    def extract_slices(self) -> List[Slice]:
        """
        Materialise one Slice per sink after run(). `run()` appends every source node it
        reaches to self._result; the recorder graph holds the traversed edges. We already
        accumulated nodes/edges/flags in self._slices during traversal, so we only mark which
        sinks actually reached a source and build the witness path.
        """
        for src_node in self.get_result():               # sources that were reached
            sl = self._slices.get(src_node['origin'])
            if sl is not None:
                sl.reached_source = True
                sl.witness = self._witness_path(sl, src_node[NODE_INDEX])
        return list(self._slices.values())

    def _witness_path(self, sl: Slice, source_id: int) -> List[int]:
        """BFS over recorded edges from source to sink to produce an ordered witness."""
        adj = defaultdict(list)
        for e in sl.edges:
            adj[e["src"]].append(e["dst"])               # edges point predecessor->node (toward sink)
        q, prev, seen = deque([source_id]), {source_id: None}, {source_id}
        sink_id = sl.sink[NODE_INDEX]
        while q:
            cur = q.popleft()
            if cur == sink_id:
                break
            for nxt in adj[cur]:
                if nxt not in seen:
                    seen.add(nxt); prev[nxt] = cur; q.append(nxt)
        path, cur = [], sink_id
        while cur is not None and cur in prev:
            path.append(cur); cur = prev[cur]
        return list(reversed(path))


def run_slicing(analysis_framework, vuln_type, intra_file_only=False, **kwargs) -> List[Slice]:
    """
    Convenience entry point.

    vuln_type: an int/str key of vuln_model.VULN_TYPE_ID_TO_STRING (e.g. XSS, SQL_INJECTION).
    intra_file_only=True yields ablation baseline #2 (no INCLUDE/EXTENDS/CALLS-across-file).
    Returns one Slice per sink; feed Slice objects to the linearizer (LINEARIZATION.md).
    """
    tr = GlobalBackwardSliceTraversal(
        analysis_framework,
        vuln_type=vuln_type,
        intra_file_only=intra_file_only,
        **kwargs,
    )
    # A codebase with no sink of this CWE anywhere is a legitimate "nothing to slice", not an
    # error -- but BaseGraphTraversal.init_traversal() raises IndexError on an empty seed set,
    # which previously aborted the whole sample. Return an empty slice list instead.
    if not tr.origin:
        logger.info("no %s sink found in this graph; nothing to slice", vuln_type)
        return []
    tr.run()
    return tr.extract_slices()
