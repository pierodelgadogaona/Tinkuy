"""Curaduría de un análisis: lo que se muestra y se exporta.

Se omite lo que no aporta a la comparación:
  · lo vacío (sin datos en ninguna de las dos noticias);
  · lo idéntico en ambas (mismo valor, mismo texto, 100 % compartido).
Las secciones y las fases que se quedan sin contenido desaparecen y la numeración visible continúa sin saltos
(`posicion` en cada fase, `etiqueta` en cada sección). Los identificadores originales no cambian: las rutas, las figuras
y las evidencias siguen apuntando a lo mismo. El proyecto guardado no se modifica; esta vista se calcula al servirlo.
"""
from __future__ import annotations

import copy
import re

_VACIOS = {"", "—", "-", "–", "n/d", "n/a", "no consta", "no disponible", "sin datos", "ninguno", "ninguna", "none", "null"}
_META = {"ev", "n", "ref", "p", "id", "evlist", "refs", "exp"}


def _txt(v) -> str:
    """Forma comparable de un valor de celda (cadena vacía si no hay nada)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return f"{v:g}"
    if isinstance(v, str):
        s = re.sub(r"\s+", " ", v).strip().casefold()
        return "" if s in _VACIOS else s
    if isinstance(v, dict):
        if "text" in v:
            return _txt(v["text"])
        return " ".join(t for k, x in v.items() if k not in ("ev", "evlist", "ref", "estado", "link") for t in [_txt(x)] if t)
    if isinstance(v, (list, tuple)):
        return " ".join(t for x in v for t in [_txt(x)] if t)
    return str(v)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _vacio_num(v) -> bool:
    n = _num(v)
    return v is None or (n is not None and n == 0)


# ------------------------------------------------------------------ bloques

def _compare(b):
    single = bool(b.get("single"))
    rows = []
    for r in b.get("rows") or []:
        a, c = _txt(r.get("n1")), _txt(r.get("n2"))
        if single:
            if a:
                rows.append(r)
            continue
        if not a and not c:
            continue                    # vacío en ambas
        if a and a == c:
            continue                    # idéntico en ambas
        rows.append(r)
    b["rows"] = rows
    return b if rows else None


def _table(b):
    cols = [c["key"] for c in b.get("columns") or []]
    pareja = "n1" in cols and "n2" in cols
    rows = []
    for r in b.get("rows") or []:
        if pareja:
            a, c = _txt(r.get("n1")), _txt(r.get("n2"))
            if a and a == c:
                continue
        if not any(_txt(r.get(k)) for k in cols if k not in _META):
            continue
        rows.append(r)
    b["rows"] = rows
    return b if rows else None


def _bars(b):
    cats = list(b.get("categories") or [])
    series = b.get("series") or []
    if not cats or not series:
        return None
    pareja = {s.get("key") for s in series} == {"n1", "n2"} and not b.get("stacked")
    keep = []
    for i in range(len(cats)):
        vals = [s["values"][i] if i < len(s.get("values") or []) else None for s in series]
        if all(_vacio_num(v) for v in vals):
            continue
        if pareja and len({_num(v) for v in vals}) == 1 and _num(vals[0]) is not None:
            continue
        keep.append(i)
    if not keep:
        return None
    b["categories"] = [cats[i] for i in keep]
    for s in series:
        v = s.get("values") or []
        s["values"] = [v[i] if i < len(v) else None for i in keep]
    return b


def _radar(b):
    axes, series = list(b.get("axes") or []), b.get("series") or []
    pareja = {s.get("key") for s in series} == {"n1", "n2"}
    keep = []
    for i in range(len(axes)):
        vals = [s["values"][i] if i < len(s.get("values") or []) else None for s in series]
        if all(_vacio_num(v) for v in vals) or (pareja and len({_num(v) for v in vals}) == 1):
            continue
        keep.append(i)
    if len(keep) < 3:
        return None
    b["axes"] = [axes[i] for i in keep]
    for s in series:
        s["values"] = [s["values"][i] for i in keep]
    return b


def _venn(b):
    s = b.get("sets") or {}
    n1, n2, sh = s.get("n1") or [], s.get("n2") or [], s.get("shared") or []
    if not (n1 or n2 or sh):
        return None
    if not n1 and not n2:               # todo es compartido: 100 % en ambas
        return None
    return b


def _scale(b):
    items = [i for i in b.get("items") or [] if _num(i.get("value")) is not None]
    if not items:
        return None
    if len(items) > 1 and len({_num(i["value"]) for i in items}) == 1:
        return None
    return b


def _diverging(b):
    rows = [r for r in b.get("rows") or [] if not (_vacio_num(r.get("n1")) and _vacio_num(r.get("n2"))) and _num(r.get("n1")) != _num(r.get("n2"))]
    b["rows"] = rows
    return b if rows else None


def _cards(b):
    items = []
    for c in b.get("items") or []:
        if any(_txt(f.get("value")) for f in c.get("fields") or []) or c.get("image"):
            items.append(c)
    b["items"] = items
    return b if items else None


def _lista(campo):
    return lambda b: b if b.get(campo) else None


def _articulos(campo):
    def f(b):
        return b if any((a.get(campo) or []) for a in b.get("articles") or []) else None
    return f


def _wordcloud(b):
    return b if any((c.get("words") or []) for c in b.get("clouds") or []) else None


def _temporal3(b):
    return b if any((c.get("items") or []) for c in b.get("columns") or []) else None


def _graph(b):
    return b if len(b.get("nodes") or []) >= 2 and (b.get("edges") or []) else None


def _pubchrono(b):
    return b if len(b.get("publications") or []) >= 2 else None


def _texto(b):
    return b if _txt(b.get("text")) else None


def _notice(b):
    return None if b.get("status") == "no_disponible" else b


_REGLAS = {
    "compare": _compare, "table": _table, "bars": _bars, "radar": _radar, "venn": _venn, "scale": _scale, "diverging": _diverging,
    "cards": _cards, "gallery": _lista("items"), "wordcloud": _wordcloud, "temporal3": _temporal3, "graph": _graph,
    "pubchrono": _pubchrono, "timeline": _lista("events"), "territory": _lista("nodes"), "map": _lista("nodes"),
    "flow": _articulos("steps"), "blocks": _articulos("segments"), "paragraph_profile": _articulos("values"),
    "cohesion": _articulos("transitions"), "argument": _articulos("nodes"), "text": _texto, "notice": _notice,
}


def curar_bloque(b: dict):
    """Devuelve el bloque sin lo vacío ni lo idéntico, o None si no queda nada que mostrar."""
    try:
        r = _REGLAS.get(b.get("kind"))
        return r(b) if r else b
    except Exception:                    # ante un bloque inesperado se conserva tal cual
        return b


def curar(p: dict) -> dict:
    """Copia del proyecto con las fases, secciones y bloques curados y la numeración visible continua."""
    q = dict(p)
    fases, omitidas = {}, []
    pos = 0
    for k in sorted((p.get("phases") or {}), key=lambda x: int(x)):
        ph = copy.deepcopy(p["phases"][k])
        secs, j = [], 0
        for s in ph.get("secciones") or []:
            bloques = [x for b in s.get("blocks") or [] for x in [curar_bloque(b)] if x]
            if not any(b.get("kind") != "notice" for b in bloques):
                continue
            j += 1
            s["blocks"] = bloques
            secs.append(s)
        if not secs and ph.get("estado") != "error":
            omitidas.append({"numero": int(k), "titulo": ph.get("titulo", "")})
            continue
        pos += 1
        ph["secciones"], ph["posicion"], ph["original"] = secs, pos, int(k)
        for i, s in enumerate(secs, 1):
            s["etiqueta"] = f"{pos}.{i}"
        fases[k] = ph
    q["phases"] = fases
    q["curaduria"] = {"omitidas": omitidas}
    return q
