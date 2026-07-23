"""
MedGraph API

Endpoints:
    GET  /health
    GET  /entities                  -> list all nodes, optional ?type= filter
    GET  /query?entity=X            -> neighbors of an entity (1-hop subgraph)
"""
import os
from typing import Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException

app = FastAPI(title="MedGraph API", version="0.1.0")


def get_conn():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "medgraph"),
        user=os.environ.get("PGUSER", os.environ.get("USER", "postgres")),
        password=os.environ.get("PGPASSWORD", ""),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/entities")
def list_entities(type: Optional[str] = None):
    conn = get_conn()
    cur = conn.cursor()
    if type:
        cur.execute("SELECT name, type FROM nodes WHERE type = %s ORDER BY name", (type,))
    else:
        cur.execute("SELECT name, type FROM nodes ORDER BY type, name")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"count": len(rows), "entities": rows}


@app.get("/query")
def query_entity(entity: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, type FROM nodes WHERE LOWER(name) = LOWER(%s)", (entity,))
    node = cur.fetchone()
    if not node:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail=f"Entity '{entity}' not found")

    cur.execute(
        """SELECT n.name AS target, e.predicate, e.paper_title, e.paper_url
           FROM edges e JOIN nodes n ON n.id = e.target_id
           WHERE e.source_id = %s""",
        (node["id"],),
    )
    outgoing = cur.fetchall()

    cur.execute(
        """SELECT n.name AS source, e.predicate, e.paper_title, e.paper_url
           FROM edges e JOIN nodes n ON n.id = e.source_id
           WHERE e.target_id = %s""",
        (node["id"],),
    )
    incoming = cur.fetchall()

    cur.close()
    conn.close()
    return {"entity": node, "outgoing": outgoing, "incoming": incoming}
