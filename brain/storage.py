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


get_conn().execute(
    "CREATE TABLE IF NOT EXISTS notes("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "parent_id INTEGER,"
    "body TEXT NOT NULL,"
    "ts REAL NOT NULL,"
    "emb BLOB)"
)

get_conn().execute("CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(body, content='notes', content_rowid='id')")

get_conn().execute("""
                   CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes
                   BEGIN
                   INSERT INTO notes_fts(rowid, body)
                   VALUES (new.id, new.body);
                   END;
                   """)

get_conn().execute("""
                   CREATE TRIGGER IF NOT EXISTS notes_ad AFTER
                   DELETE
                   ON notes
                   BEGIN
                   INSERT INTO notes_fts(notes_fts, rowid, body)
                   VALUES ('delete', old.id, old.body);
                   END;
                   """)

get_conn().execute("""
                   CREATE TRIGGER IF NOT EXISTS notes_au AFTER
                   UPDATE ON notes
                   BEGIN
                   INSERT INTO notes_fts(notes_fts, rowid, body)
                   VALUES ('delete', old.id, old.body);
                   INSERT INTO notes_fts(rowid, body)
                   VALUES (new.id, new.body);
                   END;
                   """)

if get_conn().execute("SELECT COUNT(*) FROM notes_fts").fetchone()[0] == 0:
    get_conn().execute("INSERT INTO notes_fts(rowid, body) SELECT id, body FROM notes")

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


def add(body: str):
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
            "INSERT INTO notes(parent_id, body, ts, emb) VALUES(?,?,?,?)",
            (parent, chunk, ts, blob))
        nid = cur.lastrowid
        if parent is None:
            parent = nid
        get_conn().commit()
        _index.add_items(vec.reshape(1, -1), [nid])


@lru_cache(maxsize=128)
def _embed(text: str) -> np.ndarray:
    from .llm import embed
    normalized_text = _normalize(text)
    return np.array(embed(normalized_text), dtype="float32")


@lru_cache(maxsize=64)
def topk(query: str, k: int = 4):
    if _index is None or _index.get_current_count() == 0:
        normalized_query = _normalize(query)
        if normalized_query:
            fts_query = normalized_query
            fts_ids = get_conn().execute("SELECT rowid FROM notes_fts WHERE notes_fts MATCH ? LIMIT ?",
                                         (fts_query, k)).fetchall()
            fts_ids = set(row[0] for row in fts_ids)
        else:
            fts_ids = set()
        if not fts_ids:
            return []
        placeholders = ','.join('?' * len(fts_ids))
        rows = get_conn().execute(f"SELECT id, body FROM notes WHERE id IN ({placeholders})", list(fts_ids)).fetchall()
        return rows[:k]

    normalized_query = _normalize(query)

    emb_ids = set()
    try:
        vec = _embed(query)
        if vec.size == _DIM:
            k_emb = min(k, _index.get_current_count())
            emb_ids, _ = _index.knn_query(vec, k=k_emb)
            emb_ids = set(emb_ids[0])
    except RuntimeError:
        pass

    fts_ids = set()
    if normalized_query:
        fts_query = normalized_query
        fts_ids = get_conn().execute("SELECT rowid FROM notes_fts WHERE notes_fts MATCH ? LIMIT ?",
                                     (fts_query, k)).fetchall()
        fts_ids = set(row[0] for row in fts_ids)

    all_ids = emb_ids.union(fts_ids)
    if not all_ids:
        return []

    placeholders = ','.join('?' * len(all_ids))
    rows = get_conn().execute(f"SELECT id, body FROM notes WHERE id IN ({placeholders})", list(all_ids)).fetchall()
    return rows[:k]


def all_notes():
    return get_conn().execute("SELECT id, parent_id, ts, body FROM notes ORDER BY ts DESC").fetchall()


def delete(nid: int):
    if _index:
        _index.mark_deleted(nid)
    get_conn().execute("DELETE FROM notes WHERE id=?", (nid,))
    get_conn().commit()