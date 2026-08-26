"""
Freshness/diversity store — SEMANTIC version.

Old version: exact-hash match only. Caught literal repeats but NOT the same fact
reworded ("Who holds the record for most wickets?" vs "Muralitharan holds the
record for most wickets, with 800.") — which is the actual bug we saw in
production: 4 items in a row, all about the same fact, just rephrased.

New version: embeds every generated summary with the same MiniLM model already
used for ChromaDB, and rejects a new item if it's too similar (cosine similarity)
to anything recently generated for that sport — regardless of exact wording or
content type (a quiz and a trivia card about the same fact are still a repeat).
Still backed by SQLite so it persists across sessions.
"""

import os
import sqlite3
import json
import numpy as np
from sentence_transformers import SentenceTransformer

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "history.db")
SIMILARITY_THRESHOLD = 0.92  # cosine similarity above this = "same fact, reworded"

_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS generated_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sport TEXT,
            content_type TEXT,
            summary_text TEXT,
            embedding TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return conn


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def is_duplicate(summary_text: str, sport: str, recent_limit: int = 30) -> bool:
    """
    Checks the new item against recent items for this SPORT (not just this
    content_type) since the same underlying fact can appear as a quiz, trivia,
    fill-blank, etc. — that mix was exactly the bug observed in production.
    """
    conn = _get_conn()
    rows = conn.execute(
        "SELECT embedding FROM generated_items WHERE sport = ? ORDER BY created_at DESC LIMIT ?",
        (sport, recent_limit),
    ).fetchall()
    conn.close()

    if not rows:
        return False

    embedder = get_embedder()
    new_emb = embedder.encode(summary_text)

    for (emb_json,) in rows:
        old_emb = np.array(json.loads(emb_json))
        if _cosine_sim(new_emb, old_emb) >= SIMILARITY_THRESHOLD:
            return True
    return False


def record_item(sport: str, content_type: str, summary_text: str):
    embedder = get_embedder()
    emb = embedder.encode(summary_text).tolist()
    conn = _get_conn()
    conn.execute(
        "INSERT INTO generated_items (sport, content_type, summary_text, embedding) VALUES (?, ?, ?, ?)",
        (sport, content_type, summary_text, json.dumps(emb)),
    )
    conn.commit()
    conn.close()


def get_recent_summaries(sport: str, content_type: str = None, limit: int = 8) -> list[str]:
    """
    Used to build the 'avoid_list' injected into prompts.
    Pulls across ALL content types for this sport (not just the current one),
    since the same fact showing up as a different content type is still a repeat.
    """
    conn = _get_conn()
    rows = conn.execute(
        "SELECT summary_text FROM generated_items WHERE sport = ? ORDER BY created_at DESC LIMIT ?",
        (sport, limit),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]
