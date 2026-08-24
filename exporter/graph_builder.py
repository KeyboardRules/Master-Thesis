"""
Build a combined program graph (MDG + CHG) from PHP file analyses.

Node ID conventions
───────────────────
MDG nodes  : POSIX-style path relative to project root  e.g. "index.php"
CHG nodes  : simple type name                           e.g. "DbConnection"

These two namespaces are disjoint in practice (file paths vs identifier names).
If a collision is needed in the future, add a "file::" / "class::" prefix.

Node attributes
───────────────
  kind        module | module_unresolved |
              class | abstract_class | interface | trait |
              class_external | interface_external | trait_external
  label       human-readable name (same as node ID for now)
  graph_type  MDG | CHG
  file        (CHG only) relative path of the declaring file
  line        (CHG only) line number of the declaration

Edge attributes
───────────────
  kind        INCLUDE | REQUIRE | INCLUDE_ONCE | REQUIRE_ONCE   (MDG)
              EXTENDS | IMPLEMENTS | USE_TRAIT                   (CHG)
  graph_type  MDG | CHG
  label       lower-case version of kind (for display tools)
"""

from pathlib import Path
from typing import Dict, List

import networkx as nx

from php_parser import FileAnalysis, ClassDecl


def _rel_posix(abs_path: str, root: str) -> str:
    """Return POSIX relative path from root; fall back to the absolute path."""
    try:
        return Path(abs_path).relative_to(root).as_posix()
    except ValueError:
        return Path(abs_path).as_posix()


def build_graph(analyses: List[FileAnalysis], project_root: str) -> nx.DiGraph:
    G = nx.DiGraph()

    # Map absolute path → relative node ID (used throughout MDG construction)
    path_to_id: Dict[str, str] = {
        a.path: _rel_posix(a.path, project_root) for a in analyses
    }

    # ── MDG: one node per discovered file ────────────────────────────────────
    for a in analyses:
        nid = path_to_id[a.path]
        G.add_node(nid, kind="module", label=nid, graph_type="MDG")

    # ── MDG: one directed edge per include/require statement ─────────────────
    for a in analyses:
        src_id = path_to_id[a.path]
        for inc in a.includes:
            if inc.resolved and inc.resolved in path_to_id:
                dst_id = path_to_id[inc.resolved]
            else:
                # Unresolved include: synthetic placeholder node
                dst_id = f"?:{inc.raw_expr}"
                if not G.has_node(dst_id):
                    G.add_node(dst_id,
                               kind="module_unresolved",
                               label=inc.raw_expr,
                               graph_type="MDG")

            edge_kind = inc.stmt_type.upper()
            G.add_edge(src_id, dst_id,
                       kind=edge_kind,
                       graph_type="MDG",
                       label=inc.stmt_type)

    # ── CHG: collect all class/interface/trait declarations ──────────────────
    all_types: Dict[str, ClassDecl] = {}
    for a in analyses:
        for cls in a.classes:
            all_types[cls.name] = cls

    for cls in all_types.values():
        G.add_node(cls.name,
                   kind=cls.kind,
                   label=cls.name,
                   graph_type="CHG",
                   file=_rel_posix(cls.file, project_root),
                   line=cls.line)

    # ── CHG: inheritance and trait-use edges ─────────────────────────────────
    def _ensure_external(name: str, default_kind: str) -> None:
        """Add a placeholder node for types declared outside the project."""
        if not G.has_node(name):
            G.add_node(name,
                       kind=default_kind,
                       label=name,
                       graph_type="CHG")

    # Collect edges separately so we can set attrs in a dedicated pass.
    # Some NetworkX versions do not reliably store kwargs on add_edge() when
    # source/target nodes already carry a richer attribute schema (e.g. CHG
    # nodes that have 'file' and 'line' while MDG nodes do not).
    pending_edges: List[tuple] = []   # (u, v, attrs_dict)

    for cls in all_types.values():
        for parent in cls.extends:
            _ensure_external(parent, "class_external")
            pending_edges.append((cls.name, parent,
                                  {"kind": "EXTENDS", "graph_type": "CHG",
                                   "label": "extends"}))

        for iface in cls.implements:
            _ensure_external(iface, "interface_external")
            pending_edges.append((cls.name, iface,
                                  {"kind": "IMPLEMENTS", "graph_type": "CHG",
                                   "label": "implements"}))

        for trait in cls.uses_traits:
            _ensure_external(trait, "trait_external")
            pending_edges.append((cls.name, trait,
                                  {"kind": "USE_TRAIT", "graph_type": "CHG",
                                   "label": "use trait"}))

    # Pass 1: create edges (guarantees they exist in the adjacency dict)
    for u, v, _ in pending_edges:
        G.add_edge(u, v)

    # Pass 2: set attributes explicitly via the edge-data dict reference
    for u, v, attrs in pending_edges:
        G[u][v].update(attrs)

    return G
