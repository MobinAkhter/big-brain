# brain/storage.py
import sqlite3, json, time, pathlib
import numpy as np
import hnswlib
from functools import lru_cache

# ───────────────────────────────────────────
# On-disk vault
# ───────────────────────────────────────────
HOME = pathlib.Path.home()
APP  = HOME/" .second-brain"
APP.mkdir(mode=0o700, exist_ok=True)
DB_PATH = APP/"second_brain.db"

# ───────────────────────────────────────────
# SQLite setup
# ───────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.execute(
    "CREATE TABLE IF NOT EXISTS notes("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "parent_id INTEGER,"
    "body TEXT NOT NULL,"
    "ts REAL NOT NULL)"
)

# ───────────────────────────────────────────
# HNSW ANN index via hnswlib
# ───────────────────────────────────────────
DIM = 1024
_index = hnswlib.Index(space="ip", dim=DIM)
_index.init_index(max_elements=100000, ef_construction=200, M=32)
_index.set_ef(50)

# Load existing embeddings from disk
rows = conn.execute("SELECT id, emb_blob FROM notes").fetchall()
if rows:
    ids = [r[0] for r in rows]
    vecs = [np.frombuffer(r[1], dtype="float32") for r in rows]
    _index.add_items(np.stack(vecs), ids)

# ───────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────
def _chunk_text(text: str, max_words: int = 500):
    words = text.split()
    for i in range(0, len(words), max_words):
        yield " ".join(words[i : i + max_words])

def add(body: str) -> list[int]:
    """
    Break long notes into 500-word chunks, embed each once via the
    @embed_cache, store in DB + HNSW, return list of new IDs.
    """
    from brain.llm import embed  # avoid circular import

    ts = time.time()
    parent_id = None
    saved_ids = []

    for chunk in _chunk_text(body):
        # insert row
        cur = conn.execute(
            "INSERT INTO notes(parent_id, body, ts) VALUES(?,?,?)",
            (parent_id, chunk, ts),
        )
        nid = cur.lastrowid
        if parent_id is None:
            parent_id = nid  # first chunk defines parent
        conn.commit()
        saved_ids.append(nid)

        # index embedding
        vec = np.array(embed(chunk), dtype="float32")
        _index.add_items(vec.reshape(1, -1), [nid])

    return saved_ids

@lru_cache(maxsize=128)
def get_embedding(text: str) -> np.ndarray:
    from brain.llm import embed
    return np.array(embed(text), dtype="float32")

@lru_cache(maxsize=64)
def topk(query: str, k: int = 4) -> list[tuple[int,str]]:
    """
    Given a raw query, embed once (cached), run ANN search (fast),
    then fetch bodies in rank order.
    """
    vec = get_embedding(query)
    ids, distances = _index.knn_query(vec, k=k)
    out = []
    for nid in ids[0]:
        row = conn.execute(
            "SELECT id, body FROM notes WHERE id = ?", (int(nid),)
        ).fetchone()
        if row:
            out.append((row[0], row[1]))
    return out

def all_notes():
    return conn.execute(
        "SELECT id, parent_id, ts, body FROM notes ORDER BY ts DESC"
    ).fetchall()

def delete(nid: int):
    conn.execute("DELETE FROM notes WHERE id = ?", (nid,))
    conn.commit()
    _index.mark_deleted(nid)
