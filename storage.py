"""Almacenamiento de proyectos en SQLite (un documento JSON por proyecto y sus versiones)."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime

from .config import settings

_lock = threading.RLock()


def _conn():
    c = sqlite3.connect(settings.db_path, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, created TEXT, updated TEXT, title TEXT, data TEXT);
        CREATE TABLE IF NOT EXISTS versions (
            id TEXT PRIMARY KEY, project_id TEXT, created TEXT, label TEXT, data TEXT);
        CREATE TABLE IF NOT EXISTS geocache (
            query TEXT PRIMARY KEY, created TEXT, result TEXT);
        CREATE INDEX IF NOT EXISTS idx_versions_project ON versions(project_id);
        """)


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def save_project(p: dict) -> dict:
    p["updated"] = now()
    title = p.get("title") or ""
    with _lock, _conn() as c:
        c.execute("INSERT INTO projects(id, created, updated, title, data) VALUES (?,?,?,?,?) "
                  "ON CONFLICT(id) DO UPDATE SET updated=excluded.updated, title=excluded.title, data=excluded.data",
                  (p["id"], p.get("created") or now(), p["updated"], title, json.dumps(p, ensure_ascii=False)))
    return p


def get_project(pid: str) -> dict | None:
    with _lock, _conn() as c:
        row = c.execute("SELECT data FROM projects WHERE id=?", (pid,)).fetchone()
    return json.loads(row["data"]) if row else None


def list_projects() -> list[dict]:
    with _lock, _conn() as c:
        rows = c.execute("SELECT id, created, updated, title, data FROM projects ORDER BY updated DESC").fetchall()
    out = []
    for r in rows:
        d = json.loads(r["data"])
        arts = d.get("articles") or []
        out.append({
            "id": r["id"], "created": r["created"], "updated": r["updated"], "title": r["title"],
            "stage": d.get("stage"), "medios": [((a or {}).get("meta") or {}).get("medio") for a in arts],
            "relacion": ((d.get("correspondence") or {}).get("final") or {}).get("relacion"),
        })
    return out


def delete_project(pid: str):
    with _lock, _conn() as c:
        c.execute("DELETE FROM projects WHERE id=?", (pid,))
        c.execute("DELETE FROM versions WHERE project_id=?", (pid,))


def save_version(pid: str, label: str, data: dict) -> dict:
    v = {"id": new_id(), "project_id": pid, "created": now(), "label": label or "Versión sin título"}
    with _lock, _conn() as c:
        c.execute("INSERT INTO versions(id, project_id, created, label, data) VALUES (?,?,?,?,?)",
                  (v["id"], pid, v["created"], v["label"], json.dumps(data, ensure_ascii=False)))
    return v


def list_versions(pid: str) -> list[dict]:
    with _lock, _conn() as c:
        rows = c.execute("SELECT id, created, label FROM versions WHERE project_id=? ORDER BY created DESC", (pid,)).fetchall()
    return [dict(r) for r in rows]


def get_version(pid: str, vid: str) -> dict | None:
    with _lock, _conn() as c:
        row = c.execute("SELECT data FROM versions WHERE project_id=? AND id=?", (pid, vid)).fetchone()
    return json.loads(row["data"]) if row else None


def geocache_get(q: str):
    with _lock, _conn() as c:
        row = c.execute("SELECT result FROM geocache WHERE query=?", (q,)).fetchone()
    return json.loads(row["result"]) if row else None


def geocache_put(q: str, result):
    with _lock, _conn() as c:
        c.execute("INSERT OR REPLACE INTO geocache(query, created, result) VALUES (?,?,?)",
                  (q, now(), json.dumps(result, ensure_ascii=False)))


# Las tablas se crean al importar el módulo (idempotente), también fuera del servidor web.
init()
