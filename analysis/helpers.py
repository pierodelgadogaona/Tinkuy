"""Utilidades para construir bloques a partir de resultados del modelo y del código."""
from __future__ import annotations

import re
from datetime import datetime


def L(x) -> list:
    return x if isinstance(x, list) else []


def D(x) -> dict:
    return x if isinstance(x, dict) else {}


def S(x, default: str = "") -> str:
    if x is None:
        return default
    if isinstance(x, (list, tuple)):
        return "; ".join(S(i) for i in x if i not in (None, ""))
    return str(x)


def ev_cell(evs) -> dict:
    return {"ev": [e for e in L(evs) if isinstance(e, dict) and e.get("cita")]}


def one_ev(n, p, cita) -> dict:
    return {"ev": [{"n": n, "p": p, "cita": cita}]} if cita else {"ev": []}


def origin_of(n_list) -> str:
    s = set(int(x) for x in L(n_list) if str(x) in ("1", "2"))
    if s == {1, 2}:
        return "shared"
    if s == {1}:
        return "n1"
    if s == {2}:
        return "n2"
    return "shared"


def origin_from_counts(c1: int, c2: int) -> str:
    if c1 and c2:
        return "shared"
    return "n1" if c1 else "n2" if c2 else "none"


def presence_label(origin: str) -> str:
    return {"shared": "Ambas", "n1": "Solo N1", "n2": "Solo N2", "none": "Ninguna"}.get(origin, origin)


def para_index(pid: str) -> int:
    m = re.match(r"P(\d+)", pid or "")
    return int(m.group(1)) if m else 0


def para_range(a: dict, start: str, end: str) -> list[str]:
    ids = [b["id"] for b in a["blocks"] if b["type"] == "paragraph"]
    s, e = para_index(start), para_index(end or start)
    if not s:
        return []
    if e < s:
        s, e = e, s
    return [i for i in ids if s <= para_index(i) <= e]


def words_in(a: dict, pids: list[str]) -> int:
    from ..nlp.text import count_words
    m = {b["id"]: b for b in a["blocks"] if b["type"] == "paragraph"}
    return sum(count_words(m[p]["text"]) for p in pids if p in m)


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)).replace(tzinfo=None)
    except ValueError:
        try:
            return datetime.fromisoformat(str(s)[:10])
        except ValueError:
            return None


def hours_between(a, b):
    da, db = parse_dt(a), parse_dt(b)
    if not da or not db:
        return None
    return round((db - da).total_seconds() / 3600, 1)


def fmt_dt(s) -> str:
    d = parse_dt(s)
    if not d:
        return "Información no disponible"
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    txt = f"{d.day} de {meses[d.month - 1]} de {d.year}"
    if len(str(s)) > 10:
        txt += f", {d.hour:02d}:{d.minute:02d}"
    return txt


def synth_from(out: dict | None) -> tuple[dict | None, str]:
    if out and "__error__" not in out and isinstance(out.get("sintesis"), dict):
        return out["sintesis"], "modelo"
    return None, ""


NA = "Información no disponible"
