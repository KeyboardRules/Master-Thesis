"""
php-exporter — Minimum Viable PHP Program Graph Exporter
=========================================================

Extracts Module Dependency Graph (MDG) and Class Hierarchy Graph (CHG)
from a PHP file or directory, then writes them as a combined graph file.

Usage
-----
  python main.py <target> [options]

  target               PHP file or project directory to analyse
  -o / --output        Output file path (default: program_graph.graphml)
  -f / --format        graphml | gexf | dot  (default: graphml)
  -v / --verbose       Print per-file details

Example
-------
  python main.py ../tutorial/example -o output/example.graphml -v
"""

import argparse
import sys
from pathlib import Path

# Allow running from any working directory
sys.path.insert(0, str(Path(__file__).parent))

from scanner import scan
from php_parser import analyze_file
from graph_builder import build_graph
from graph_exporter import export_graph, SUPPORTED_FORMATS


def _print_analysis(analysis, project_root: str) -> None:
    """Verbose per-file summary."""
    rel = Path(analysis.path).relative_to(project_root)
    print(f"\n  [{rel}]")
    if analysis.constants:
        print(f"    constants : {dict(list(analysis.constants.items())[:4])}"
              + (" ..." if len(analysis.constants) > 4 else ""))
    for inc in analysis.includes:
        if inc.resolved:
            try:
                dst = Path(inc.resolved).relative_to(project_root)
            except ValueError:
                dst = inc.resolved
            print(f"    {inc.stmt_type:14s} → {dst}  (line {inc.line})")
        else:
            print(f"    {inc.stmt_type:14s} → [unresolved] {inc.raw_expr!r}"
                  f"  (line {inc.line})")
    for cls in analysis.classes:
        parts = [f"{cls.kind} {cls.name}"]
        if cls.extends:
            parts.append(f"extends {', '.join(cls.extends)}")
        if cls.implements:
            parts.append(f"implements {', '.join(cls.implements)}")
        if cls.uses_traits:
            parts.append(f"use {', '.join(cls.uses_traits)}")
        print(f"    {' | '.join(parts)}  (line {cls.line})")


def _print_graph_summary(G) -> None:
    import networkx as nx
    mdg_nodes = [n for n, d in G.nodes(data=True) if d.get("graph_type") == "MDG"]
    chg_nodes = [n for n, d in G.nodes(data=True) if d.get("graph_type") == "CHG"]
    mdg_edges = [(u, v, d) for u, v, d in G.edges(data=True) if d.get("graph_type") == "MDG"]
    chg_edges = [(u, v, d) for u, v, d in G.edges(data=True) if d.get("graph_type") == "CHG"]

    print(f"\n  ── MDG ({len(mdg_nodes)} nodes, {len(mdg_edges)} edges) ──")
    for u, v, d in mdg_edges:
        u_label = G.nodes[u].get("label", u)
        v_label = G.nodes[v].get("label", v)
        print(f"    {u_label}  --[{d['kind']}]-->  {v_label}")

    print(f"\n  ── CHG ({len(chg_nodes)} nodes, {len(chg_edges)} edges) ──")
    for u, v, d in chg_edges:
        print(f"    {u}  --[{d['kind']}]-->  {v}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="php-exporter",
        description="Extract MDG + CHG from PHP source code and export as a graph.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("target", help="PHP file or directory to analyse")
    parser.add_argument(
        "-o", "--output", default="program_graph.graphml",
        help="Output file path (default: program_graph.graphml)",
    )
    parser.add_argument(
        "-f", "--format", choices=SUPPORTED_FORMATS, default="graphml",
        help="Output format (default: graphml)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Print per-file analysis details",
    )
    args = parser.parse_args()

    target = Path(args.target).resolve()
    if not target.exists():
        print(f"[!] Target not found: {target}", file=sys.stderr)
        sys.exit(1)

    # ── Discover files ───────────────────────────────────────────────────────
    files, project_root = scan(str(target))
    print(f"[*] Analysing {len(files)} PHP file(s) under '{target}'")

    # ── Analyse each file ────────────────────────────────────────────────────
    analyses = []
    for fp in files:
        result = analyze_file(fp)
        analyses.append(result)
        if args.verbose:
            _print_analysis(result, project_root)

    # ── Build graph ──────────────────────────────────────────────────────────
    G = build_graph(analyses, project_root)

    total_nodes = G.number_of_nodes()
    total_edges = G.number_of_edges()
    mdg_edge_count = sum(1 for *_, d in G.edges(data=True) if d.get("graph_type") == "MDG")
    chg_edge_count = sum(1 for *_, d in G.edges(data=True) if d.get("graph_type") == "CHG")

    print(f"\n[*] Graph built: {total_nodes} nodes, {total_edges} edges "
          f"(MDG: {mdg_edge_count}, CHG: {chg_edge_count})")
    _print_graph_summary(G)

    # ── Export ───────────────────────────────────────────────────────────────
    print()
    export_graph(G, args.output, args.format)


if __name__ == "__main__":
    main()
