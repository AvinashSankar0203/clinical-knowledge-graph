"""
Loads ../data/graph.json into Postgres.

Reads connection info from env vars (all have local-dev defaults):
    PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
"""
import json
import os
from pathlib import Path

import psycopg2

GRAPH_PATH = Path(__file__).resolve().parent.parent / "data" / "graph.json"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_conn():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "medgraph"),
        user=os.environ.get("PGUSER", os.environ.get("USER", "postgres")),
        password=os.environ.get("PGPASSWORD", ""),
    )


def main():
    graph = json.loads(GRAPH_PATH.read_text())
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(SCHEMA_PATH.read_text())
    conn.commit()

    name_to_id = {}
    for node in graph["nodes"]:
        cur.execute(
            """INSERT INTO nodes (name, type) VALUES (%s, %s)
               ON CONFLICT (name) DO UPDATE SET type = EXCLUDED.type
               RETURNING id""",
            (node["name"], node["type"]),
        )
        name_to_id[node["name"]] = cur.fetchone()[0]
    conn.commit()

    inserted = 0
    for edge in graph["edges"]:
        src_id = name_to_id.get(edge["source"])
        tgt_id = name_to_id.get(edge["target"])
        if src_id is None or tgt_id is None:
            continue
        cur.execute(
            """INSERT INTO edges (source_id, predicate, target_id, paper_id, paper_title, paper_url)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (src_id, edge["predicate"], tgt_id, edge["paper_id"], edge["paper_title"], edge["paper_url"]),
        )
        inserted += 1
    conn.commit()

    print(f"Loaded {len(name_to_id)} nodes, {inserted} edges into Postgres.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
