"""
MedGraph API

Endpoints:
    GET  /health
    GET  /entities                  -> list all nodes, optional ?type= filter
    GET  /query?entity=X            -> neighbors of an entity (1-hop subgraph)
    POST /ask   {"question": "..."}  -> RAG-style Q&A grounded in the graph
"""
import os
from typing import Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

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


class AskRequest(BaseModel):
    question: str


def retrieve_subgraph_text(question: str, limit: int = 25) -> str:
    """Keyword-based retrieval: find edges whose source/target text overlaps
    with words in the question."""
    words = [w.strip("?.,").lower() for w in question.split() if len(w) > 3]
    if not words:
        return ""

    conn = get_conn()
    cur = conn.cursor()
    like_clauses = " OR ".join(["LOWER(sn.name) LIKE %s OR LOWER(tn.name) LIKE %s"] * len(words))
    params = []
    for w in words:
        params.extend([f"%{w}%", f"%{w}%"])
    cur.execute(
        f"""SELECT sn.name AS source, e.predicate, tn.name AS target, e.paper_title
            FROM edges e
            JOIN nodes sn ON sn.id = e.source_id
            JOIN nodes tn ON tn.id = e.target_id
            WHERE {like_clauses}
            LIMIT %s""",
        (*params, limit),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    lines = [f"- {r['source']} {r['predicate']} {r['target']} (source: {r['paper_title']})" for r in rows]
    return "\n".join(lines)


@app.post("/ask")
def ask(req: AskRequest):
    context = retrieve_subgraph_text(req.question)
    if not context:
        return {"answer": "No relevant graph facts found. Try asking about a specific disease, technique, or modality.", "context_used": []}

    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": (
                "Answer the question using ONLY the graph facts below. "
                "Cite which paper(s) support your answer. If the facts don't "
                "fully answer the question, say so.\n\n"
                f"Graph facts:\n{context}\n\nQuestion: {req.question}"
            ),
        }],
    )
    answer_text = "".join(b.text for b in msg.content if b.type == "text")
    return {"answer": answer_text, "context_used": context.split("\n")}
