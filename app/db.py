"""SQLite persistence for screening cases."""
import json
import re
import sqlite3
from contextlib import contextmanager


def normalise_phone(v: str | None) -> str | None:
    digits = re.sub(r"\D", "", v or "")
    return digits or None


def normalise_email(v: str | None) -> str | None:
    email = (v or "").strip().lower()
    return email or None

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id    TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    full_name  TEXT,
    passport_no TEXT,
    nationality TEXT,
    email      TEXT,
    phone      TEXT,
    doc_hash   TEXT,
    score      INTEGER,
    band       TEXT,
    payload    TEXT
);
CREATE INDEX IF NOT EXISTS idx_passport ON cases(passport_no);
CREATE INDEX IF NOT EXISTS idx_email    ON cases(email);
CREATE INDEX IF NOT EXISTS idx_doc_hash ON cases(doc_hash);
"""

@contextmanager
def _conn(path: str):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

def init_db(path: str) -> None:
    with _conn(path) as con:
        con.executescript(SCHEMA)

def save_case(path, case_id, claimed, score, band, signals, doc_hash=None) -> None:
    payload = json.dumps({
        "claimed": claimed,
        "signals": [{"code": s.code, "engine": s.engine, "severity": s.severity,
                     "message": s.message} for s in signals],
    })
    with _conn(path) as con:
        con.execute(
            "INSERT OR REPLACE INTO cases "
            "(case_id, full_name, passport_no, nationality, email, phone, doc_hash, score, band, payload) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (case_id, claimed.get("full_name"), claimed.get("passport_no"),
             claimed.get("nationality"), normalise_email(claimed.get("email")),
             normalise_phone(claimed.get("phone")),
             doc_hash, score, band, payload),
        )

def find_prior(path, *, passport_no=None, email=None, phone=None, doc_hash=None) -> list[dict]:
    clauses, params = [], []
    for col, val in (("passport_no", passport_no), ("email", normalise_email(email)),
                     ("phone", normalise_phone(phone)), ("doc_hash", doc_hash)):
        if val:
            clauses.append(f"{col} = ?")
            params.append(val)
    if not clauses:
        return []
    sql = f"SELECT * FROM cases WHERE {' OR '.join(clauses)} ORDER BY created_at DESC LIMIT 50"
    with _conn(path) as con:
        return [dict(r) for r in con.execute(sql, params)]

def recent_count(path: str, minutes: int = 10) -> int:
    with _conn(path) as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM cases "
            "WHERE created_at >= datetime('now', ?)", (f"-{minutes} minutes",)
        ).fetchone()
        return row["n"]

def all_cases(path: str, limit: int = 100) -> list[dict]:
    with _conn(path) as con:
        return [dict(r) for r in con.execute(
            "SELECT case_id, created_at, full_name, score, band FROM cases "
            "ORDER BY created_at DESC LIMIT ?", (limit,))]
