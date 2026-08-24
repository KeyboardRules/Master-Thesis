"""Export a NetworkX DiGraph to GraphML, GEXF, or DOT format."""

from pathlib import Path

import networkx as nx

SUPPORTED_FORMATS = ("graphml", "gexf", "dot")


def export_graph(G: nx.DiGraph, output_path: str, fmt: str = "graphml") -> None:
    """
    Write graph G to output_path in the requested format.

    GraphML  — best compatibility; opens in Gephi, yEd, NetworkX.
    GEXF     — richer metadata; Gephi-native format.
    DOT      — requires 'pydot' (pip install pydot); opens in Graphviz/dot.
    """
    fmt = fmt.lower()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "graphml":
        nx.write_graphml(G, str(out))
    elif fmt == "gexf":
        nx.write_gexf(G, str(out))
    elif fmt == "dot":
        try:
            from networkx.drawing.nx_pydot import write_dot
        except ImportError as exc:
            raise ImportError(
                "DOT export requires 'pydot'.  "
                "Install with:  pip install pydot"
            ) from exc
        write_dot(G, str(out))
    else:
        raise ValueError(
            f"Unknown format '{fmt}'.  Choose from: {SUPPORTED_FORMATS}"
        )

    print(f"[+] Graph written to: {out.resolve()}")
