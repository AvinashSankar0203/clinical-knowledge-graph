"""
Graph analysis layer: loads the knowledge graph from Postgres into NetworkX
for algorithmic queries (centrality, paths), and pandas for summary tables.

This complements the Postgres storage layer -- Postgres is the system of
record; NetworkX/pandas are read-only tools for analysis and visualization.
"""
import os

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import psycopg2
import psycopg2.extras


def get_conn():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "medgraph"),
        user=os.environ.get("PGUSER", os.environ.get("USER", "postgres")),
        password=os.environ.get("PGPASSWORD", ""),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def load_graph_from_postgres() -> nx.DiGraph:
    """Builds a directed NetworkX graph from the nodes/edges tables."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id, name, type FROM nodes")
    nodes = cur.fetchall()

    cur.execute(
        """SELECT sn.name AS source, e.predicate, tn.name AS target, e.paper_title
           FROM edges e
           JOIN nodes sn ON sn.id = e.source_id
           JOIN nodes tn ON tn.id = e.target_id"""
    )
    edges = cur.fetchall()
    cur.close()
    conn.close()

    G = nx.DiGraph()
    for n in nodes:
        G.add_node(n["name"], type=n["type"])
    for e in edges:
        G.add_edge(e["source"], e["target"], predicate=e["predicate"], paper=e["paper_title"])

    return G


def most_connected_entities(G: nx.DiGraph, top_n: int = 10) -> pd.DataFrame:
    """Degree centrality: how many direct connections each entity has,
    normalized by graph size. Higher = more 'central' to the graph."""
    centrality = nx.degree_centrality(G)
    df = pd.DataFrame(
        [(name, G.nodes[name].get("type", "Unknown"), score) for name, score in centrality.items()],
        columns=["entity", "type", "centrality"],
    )
    return df.sort_values("centrality", ascending=False).head(top_n).reset_index(drop=True)


def entity_type_counts(G: nx.DiGraph) -> pd.DataFrame:
    """Simple pandas summary: how many entities of each type exist."""
    types = [G.nodes[n].get("type", "Unknown") for n in G.nodes]
    df = pd.DataFrame({"type": types})
    return df.value_counts("type").reset_index(name="count")


def shortest_path_between(G: nx.DiGraph, source: str, target: str):
    """Finds the shortest chain of relationships connecting two entities,
    treating the graph as undirected for this search (we care about ANY
    connection path, not just following relation direction)."""
    undirected = G.to_undirected()
    try:
        return nx.shortest_path(undirected, source=source, target=target)
    except nx.NetworkXNoPath:
        return None
    except nx.NodeNotFound as e:
        return f"Entity not found: {e}"


def draw_graph(G: nx.DiGraph, output_path: str = "analysis/graph.png"):
    """Renders the graph as an image -- useful for a README or showing
    a non-technical audience what the graph actually looks like."""
    plt.figure(figsize=(16, 12))
    pos = nx.spring_layout(G, k=0.6, seed=42)

    type_colors = {
        "Disease": "#e74c3c", "Modality": "#3498db", "Technique": "#2ecc71",
        "Anatomy": "#f39c12", "Model": "#9b59b6", "Unknown": "#95a5a6",
    }
    node_colors = [type_colors.get(G.nodes[n].get("type", "Unknown"), "#95a5a6") for n in G.nodes]

    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=500, alpha=0.9)
    nx.draw_networkx_edges(G, pos, alpha=0.3, arrows=True, arrowsize=8)
    nx.draw_networkx_labels(G, pos, font_size=7)

    plt.title("MedGraph: Clinical Literature Knowledge Graph", fontsize=14)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Saved graph visualization -> {output_path}")


def main():
    G = load_graph_from_postgres()
    print(f"Loaded graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges\n")

    print("=== Entity type breakdown ===")
    print(entity_type_counts(G).to_string(index=False))

    print("\n=== Most connected entities (degree centrality) ===")
    print(most_connected_entities(G).to_string(index=False))

    print("\n=== Example shortest path: glioma -> CNN ===")
    path = shortest_path_between(G, "glioma", "CNN")
    print(path)

    draw_graph(G)


if __name__ == "__main__":
    main()
