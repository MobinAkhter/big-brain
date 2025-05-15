# brain/storage.py
import sqlite3, json, time, pathlib, faiss, numpy as np

# ─────────────────────────────────────────────
# On-disk location for the vault
# ─────────────────────────────────────────────
HOME = pathlib.Path.home()
APP = HOME / ".second-brain"
APP.mkdir(mode=0o700, exist_ok=True)
DB_PATH = APP / "second_brain.db"

# ─────────────────────────────────────────────
# SQLite setup
# ─────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.execute(
    "CREATE TABLE IF NOT EXISTS notes("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "body TEXT NOT NULL,"
    "ts   REAL NOT NULL,"
    "emb  BLOB NOT NULL)"
)

# ─────────────────────────────────────────────
# FAISS index — use IndexIDMap so add_with_ids works
# ─────────────────────────────────────────────
DIM = 1024  # size of embedding vector
_index_base = faiss.IndexFlatIP(DIM)                  # cosine similarity via inner-prod
index = faiss.IndexIDMap(_index_base)                 # enables add_with_ids

# Load any existing vectors from the DB
rows = conn.execute("SELECT id, emb FROM notes").fetchall()
if rows:
    ids = np.array([r[0] for r in rows], dtype="int64")
    vecs = np.array([json.loads(r[1]) for r in rows], dtype="float32")
    index.add_with_ids(vecs, ids)

# ─────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────
def add(body: str, vec: list[float]) -> int:
    """Persist note + vector, update FAISS, return its row-id."""
    cur = conn.execute(
        "INSERT INTO notes(body, ts, emb) VALUES(?,?,?)",
        (body, time.time(), json.dumps(vec)),
    )
    note_id = cur.lastrowid
    conn.commit()

    # FAISS update
    index.add_with_ids(
        np.array([vec], dtype="float32"),
        np.array([note_id], dtype="int64"),
    )
    return note_id


def topk(vec: list[float], k: int = 4):
    """Return (id, body) for the top-k cosine-similar matches."""
    if index.ntotal == 0:
        return []

    D, I = index.search(np.array([vec], dtype="float32"), k)
    ids = [int(i) for i in I[0] if i != -1]

    if not ids:
        return []

    rows = conn.executemany(
        "SELECT id, body FROM notes WHERE id = ?", [(i,) for i in ids]
    )
    return list(rows)
