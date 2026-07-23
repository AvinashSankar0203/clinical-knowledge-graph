CREATE TABLE IF NOT EXISTS nodes (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
    predicate TEXT NOT NULL,
    target_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
    paper_id TEXT,
    paper_title TEXT,
    paper_url TEXT
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
