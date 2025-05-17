# brain/storage.py
import sqlite3
import time
import pathlib
import numpy as np
import hnswlib
import re
import threading
from functools import lru_cache

HOME = pathlib.Path.home()
APP = HOME / ".second-brain"
APP.mkdir(mode=0o700, exist_ok=True)
DB = APP / "second_brain.db"

local_storage = threading.local()

def get_conn():
    if not hasattr(local_storage, 'conn'):
        local_storage.conn = sqlite3.connect(DB)
    return local_storage.conn

# Create tables if they don't exist
get_conn().execute(
    "CREATE TABLE IF NOT EXISTS notes("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "parent_id INTEGER,"
    "body TEXT NOT NULL,"
    "ts REAL NOT NULL,"
    "emb BLOB,"
    "tags TEXT DEFAULT '')"
)

get_conn().execute("CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(body, content='notes', content_rowid='id')")

# Triggers for FTS5
get_conn().execute("""
CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes
BEGIN
  INSERT INTO notes_fts(rowid, body) VALUES (new.id, new.body);
END;
""")

get_conn().execute("""
CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes
BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, body) VALUES ('delete', old.id, old.body);
END;
""")

get_conn().execute("""
CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes
BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, body) VALUES ('delete', old.id, old.body);
  INSERT INTO notes_fts(rowid, body) VALUES (new.id, new.body);
END;
""")

# Populate FTS table if empty
if get_conn().execute("SELECT COUNT(*) FROM notes_fts").fetchone()[0] == 0:
    get_conn().execute("INSERT INTO notes_fts(rowid, body) SELECT id, body FROM notes")

# Ensure 'tags' column exists (for backward compatibility)
cursor = get_conn().execute("PRAGMA table_info(notes)")
columns = [row[1] for row in cursor.fetchall()]
if 'tags' not in columns:
    get_conn().execute("ALTER TABLE notes ADD COLUMN tags TEXT DEFAULT ''")
    get_conn().commit()

_index = None
_DIM = 0

def _ensure_index(dim: int):
    global _index, _DIM
    if _index is None:
        _DIM = dim
        idx = hnswlib.Index(space="ip", dim=_DIM)
        idx.init_index(max_elements=100_000, ef_construction=200, M=32)
        idx.set_ef(100)
        rows = get_conn().execute("SELECT id, emb FROM notes WHERE emb IS NOT NULL").fetchall()
        for nid, blob in rows:
            if isinstance(blob, (bytes, bytearray)) and len(blob) == _DIM * 4:
                vec = np.frombuffer(blob, dtype="float32")
                idx.add_items(vec.reshape(1, -1), [nid])
        _index = idx

def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    return text

def _chunk(text, max_words=100):
    words = text.split()
    if len(words) <= max_words:
        yield text
    else:
        for i in range(0, len(words), max_words):
            yield " ".join(words[i:i + max_words])

def add(body: str, tags: str = ""):
    from .llm import embed
    ts = time.time()
    parent = None
    for chunk in _chunk(body):
        normalized_chunk = _normalize(chunk)
        vec = np.array(embed(normalized_chunk), dtype="float32")
        if vec.size == 0:
            continue
        _ensure_index(vec.size)
        blob = vec.tobytes()
        cur = get_conn().execute(
            "INSERT INTO notes(parent_id, body, ts, emb, tags) VALUES(?,?,?,?,?)",
            (parent, chunk, ts, blob, tags))
        nid = cur.lastrowid
        if parent is None:
            parent = nid
        get_conn().commit()
        _index.add_items(vec.reshape(1, -1), [nid])

def update_note(nid: int, body: str, tags: str = ""):
    from .llm import embed
    ts = time.time()
    normalized_body = _normalize(body)
    vec = np.array(embed(normalized_body), dtype="float32")
    _ensure_index(vec.size)
    blob = vec.tobytes()
    get_conn().execute(
        "UPDATE notes SET body=?, ts=?, emb=?, tags=? WHERE id=?",
        (body, ts, blob, tags, nid)
    )
    get_conn().commit()
    if _index:
        _index.mark_deleted(nid)
        _index.add_items(vec.reshape(1, -1), [nid])

def get_note(nid):
    row = get_conn().execute("SELECT body, tags FROM notes WHERE id=?", (nid,)).fetchone()
    return {"body": row[0], "tags": row[1]} if row else None

@lru_cache(maxsize=128)
def _embed(text: str) -> np.ndarray:
    from .llm import embed
    normalized_text = _normalize(text)
    return np.array(embed(normalized_text), dtype="float32")

@lru_cache(maxsize=64)
def topk(query: str, k: int = 4, tags: str = None, date_start: float = None, date_end: float = None):
    normalized_query = _normalize(query)
    fts_query = ' '.join([f"{word}*" for word in normalized_query.split()]) if query else ''

    # Build SQL query for filtering
    conditions = []
    params = []
    if tags:
        tag_list = [tag.strip().lower() for tag in tags.split(',') if tag.strip()]
        if tag_list:
            conditions.append(" AND ".join("LOWER(tags) LIKE ?" for _ in tag_list))
            params.extend([f"%{tag}%" for tag in tag_list])
    if date_start is not None:
        conditions.append("ts >= ?")
        params.append(date_start)
    if date_end is not None:
        conditions.append("ts <= ?")
        params.append(date_end)

    emb_results = {}
    if _index is not None and _index.get_current_count() > 0 and query:
        try:
            vec = _embed(query)
            if vec.size == _DIM:
                k_emb = min(k, _index.get_current_count())
                labels, distances = _index.knn_query(vec, k=k_emb)
                similarities = -distances[0]  # Higher is better for inner product
                if len(similarities) > 0:
                    min_sim = np.min(similarities)
                    max_sim = np.max(similarities)
                    if max_sim > min_sim:
                        sim_emb_norm = (similarities - min_sim) / (max_sim - min_sim)
                    else:
                        sim_emb_norm = np.ones_like(similarities)
                    emb_results = {int(label): score for label, score in zip(labels[0], sim_emb_norm)}
        except RuntimeError:
            pass

    fts_results = {}
    if fts_query:
        fts_conditions = conditions[:]
        fts_params = params[:]
        fts_conditions.insert(0, "notes_fts MATCH ?")
        fts_params.insert(0, fts_query)
        where_clause = " WHERE " + " AND ".join(fts_conditions) if fts_conditions else ""
        query = f"""
            SELECT rowid, rank FROM notes_fts
            JOIN notes ON notes_fts.rowid = notes.id
            {where_clause}
            ORDER BY rank LIMIT ?
        """
        fts_rows = get_conn().execute(query, fts_params + [k]).fetchall()
        if fts_rows:
            rowids, ranks = zip(*fts_rows)
            similarities = -np.array(ranks)
            min_sim = np.min(similarities)
            max_sim = np.max(similarities)
            if max_sim > min_sim:
                sim_fts_norm = (similarities - min_sim) / (max_sim - min_sim)
            else:
                sim_fts_norm = np.ones_like(similarities)
            fts_results = {int(rowid): score for rowid, score in zip(rowids, sim_fts_norm)}

    all_ids = set(emb_results.keys()).union(set(fts_results.keys()))
    if not query and not all_ids:
        # If no query, return filtered notes without ranking
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = get_conn().execute(
            f"SELECT id, body FROM notes{where_clause}",
            params
        ).fetchall()
        return rows[:k]

    if not all_ids:
        return []

    scores = {}
    for nid in all_ids:
        emb_score = emb_results.get(nid, 0)
        fts_score = fts_results.get(nid, 0)
        scores[nid] = emb_score + fts_score

    sorted_ids = sorted(all_ids, key=lambda x: scores[x], reverse=True)
    placeholders = ','.join('?' * len(sorted_ids))
    rows = get_conn().execute(
        f"SELECT id, body FROM notes WHERE id IN ({placeholders})",
        list(sorted_ids)
    ).fetchall()

    id_to_row = {row[0]: row for row in rows}
    sorted_rows = [id_to_row[nid] for nid in sorted_ids if nid in id_to_row]
    return sorted_rows[:k]

def filter_notes(text: str = None, tags: str = None, date_start: float = None, date_end: float = None):
    conditions = []
    params = []
    if text:
        conditions.append("LOWER(body) LIKE ?")
        params.append(f"%{text.lower()}%")
    if tags:
        tag_list = [tag.strip().lower() for tag in tags.split(',') if tag.strip()]
        if tag_list:
            conditions.append(" AND ".join("LOWER(tags) LIKE ?" for _ in tag_list))
            params.extend([f"%{tag}%" for tag in tag_list])
    if date_start is not None:
        conditions.append("ts >= ?")
        params.append(date_start)
    if date_end is not None:
        conditions.append("ts <= ?")
        params.append(date_end)
    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    return get_conn().execute(
        f"SELECT id, parent_id, ts, body, tags FROM notes{where_clause} ORDER BY ts DESC",
        params
    ).fetchall()

def all_notes():
    return get_conn().execute("SELECT id, parent_id, ts, body, tags FROM notes ORDER BY ts DESC").fetchall()

def delete(nid: int):
    if _index:
        _index.mark_deleted(nid)
    get_conn().execute("DELETE FROM notes WHERE id=?", (nid,))
    get_conn().commit()

def export_notes():
    rows = get_conn().execute("SELECT id, parent_id, ts, body, tags FROM notes").fetchall()
    return [
        {"id": nid, "parent_id": pid, "timestamp": ts, "body": body, "tags": tags}
        for nid, pid, ts, body, tags in rows
    ]