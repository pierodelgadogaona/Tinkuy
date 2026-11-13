"""Conversión de celdas y bloques del informe a texto plano para DOCX y XLSX."""
from __future__ import annotations

from ..analysis.helpers import fmt_dt

ORIGIN = {"programatico": "Cálculo programático", "heuristico": "Reglas heurísticas (aproximado)", "modelo": "Interpretación del modelo",
          "mixto": "Modelo + verificación programática", "usuario": "Editado"}
PRESENCE = {"shared": "Ambas", "n1": "Solo N1", "n2": "Solo N2", "none": "Ninguna"}
VERIF = {"literal": "✓", "corregida": "↻", "aproximada": "≈", "no_localizada": "⚠ no localizada", "sin_cita": ""}


def ev_text(evs) -> str:
    out = []
    for e in evs or []:
        if isinstance(e, dict) and e.get("cita"):
            out.append(f"N{e.get('n')}·{e.get('p')} «{e['cita']}» {VERIF.get(e.get('verificacion', 'literal'), '')}".strip())
    return " | ".join(out)


def cell(v, ctype: str = "") -> str:
    if v is None or v == "":
        return "—"
    if ctype == "noticia" and str(v) in ("1", "2"):
        return f"N{v}"
    if ctype == "presencia":
        return PRESENCE.get(v, str(v))
    if isinstance(v, dict):
        if "ev" in v:
            return ev_text(v["ev"]) or "—"
        if "evlist" in v:
            return ev_text(v["evlist"]) or "—"
        if "link" in v:
            return v["link"]
        if "text" in v:
            t = str(v["text"])
            if v.get("ev"):
                t += " " + ev_text(v["ev"])
            return t
        return str(v)
    if isinstance(v, list):
        return "; ".join(cell(x) for x in v)
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def block_table(block: dict, labels: dict) -> tuple[list[str], list[list[str]]] | None:
    k = block.get("kind")
    if k == "table":
        cols = block.get("columns", [])
        return [c["label"] for c in cols], [[cell(r.get(c["key"]), c.get("type", "")) for c in cols] for r in block.get("rows", [])]
    if k == "compare":
        single = block.get("single")
        head = ["Dimensión", "Síntesis"] if single else ["Dimensión", labels["n1"], labels["n2"]]
        rows = []
        for r in block.get("rows", []):
            row = [r.get("label", "") + (f" ({r['nota']})" if r.get("nota") else ""), cell(r.get("n1"))]
            if not single:
                row.append(cell(r.get("n2")))
            rows.append(row)
        ev = block.get("evidence") or {}
        if ev.get("n1") or ev.get("n2"):
            rows.append(["Evidencias", ev_text(ev.get("n1")), ev_text(ev.get("n2"))] if not single else ["Evidencias", ev_text(ev.get("n1"))])
        return head, rows
    if k == "bars" and block.get("categories"):
        series = block.get("series", [])
        return (["Categoría"] + [s.get("name", s.get("key")) for s in series],
                [[str(c)] + [cell(s["values"][i]) if i < len(s["values"]) else "" for s in series] for i, c in enumerate(block["categories"])])
    if k == "radar":
        series = block.get("series", [])
        return ["Dimensión"] + [s["name"] for s in series], [[a] + [cell(s["values"][i]) for s in series] for i, a in enumerate(block.get("axes", []))]
    if k == "map":
        pts = block.get("points", [])
        return (["Lugar", "Presente en", "Latitud", "Longitud", "Nivel representado", "Aproximada", "Fuente"],
                [[p["name"], PRESENCE.get(p.get("origin"), ""), f"{p['lat']:.4f}", f"{p['lon']:.4f}", str(p.get("nivel", "")),
                  "Sí" if p.get("aproximada") else "No", str(p.get("fuente", ""))] for p in pts])
    if k == "territory":
        names = {n["id"]: n["name"] for n in block.get("nodes", [])}
        if block.get("routes"):
            return (["#", "Origen", "Destino", "Quién", "Descrito en", "Distancia aprox. (km)"],
                    [[str(r.get("order") or ""), names.get(r["from"], r["from"]), names.get(r["to"], r["to"]), r.get("label", ""),
                      PRESENCE.get(r.get("origin"), ""), "" if r.get("distancia_km") is None else f"{r['distancia_km']:g}"] for r in block["routes"]])
        return (["Lugar", "Escala", "Contenido en", "Presente en", "Menciones N1", "Menciones N2"],
                [[n["name"], str(n.get("nivel", "")).replace("_", " "), names.get(n.get("parent"), ""), PRESENCE.get(n.get("origin"), ""),
                  str(n.get("m1", "")), str(n.get("m2", ""))] for n in block.get("nodes", [])])
    if k == "timeline":
        return (["#", "Acontecimiento", "Fecha", "Texto", "Presente en", "Evidencias"],
                [[str(i + 1), e.get("label", ""), e.get("date") or "—", e.get("date_text") or "", PRESENCE.get(e.get("origin"), ""), ev_text(e.get("ev"))]
                 for i, e in enumerate(block.get("events", []))])
    if k == "graph":
        nodes = {n["id"]: n["label"] for n in block.get("nodes", [])}
        return (["Origen", "Relación", "Destino", "Presente en", "Evidencias"],
                [[nodes.get(e["source"], e["source"]), e.get("label", ""), nodes.get(e["target"], e["target"]), PRESENCE.get(e.get("origin"), ""), ev_text(e.get("ev"))]
                 for e in block.get("edges", [])])
    if k == "diverging":
        return ["Término", "z", "N1", "N2"], [[r["label"], f"{r['value']:.2f}", str(r["n1"]), str(r["n2"])] for r in block.get("rows", [])]
    if k == "wordcloud":
        rows = []
        for c in block.get("clouds", []):
            rows += [[f"N{c['n']}", w["text"], str(w["n"])] for w in c.get("words", [])]
        return ["Noticia", "Término", "Frecuencia"], rows
    if k == "flow":
        rows = []
        for a in block.get("articles", []):
            rows += [[f"N{a['n']}", s["range"], s["label"], s.get("function", ""), str(s["words"]), f"{s['pct']}"] for s in a.get("steps", [])]
        return ["Noticia", "Párrafos", "Bloque", "Función", "Palabras", "%"], rows
    if k == "venn":
        s = block.get("sets", {})
        rows = [["Solo N1", t["label"]] for t in s.get("n1", [])] + [["Compartido", t["label"]] for t in s.get("shared", [])] + [["Solo N2", t["label"]] for t in s.get("n2", [])]
        return ["Conjunto", "Tema"], rows
    if k == "cards":
        rows = []
        for c in block.get("items", []):
            for f in c.get("fields", []):
                rows.append([c.get("title", ""), f.get("label", ""), str(f.get("value", ""))])
        return ["Ficha", "Campo", "Valor"], rows
    return None


def project_labels(p: dict) -> dict:
    a1, a2 = p["articles"]
    return {"n1": f"N1 · {a1['meta'].get('medio') or 'Noticia 1'}", "n2": f"N2 · {a2['meta'].get('medio') or 'Noticia 2'}"}


def all_evidence(p: dict):
    rows = []

    def walk(obj, where):
        if isinstance(obj, dict):
            if "cita" in obj and "n" in obj and "p" in obj:
                rows.append([where, f"N{obj.get('n')}", str(obj.get("p")), str(obj.get("cita")), obj.get("verificacion", ""), str(obj.get("p_original", ""))])
            for v in obj.values():
                walk(v, where)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, where)
    for k, ph in sorted((p.get("phases") or {}).items(), key=lambda kv: int(kv[0])):
        for s in ph.get("secciones", []):
            walk(s.get("blocks", []), f"Fase {ph.get('posicion', k)} · {s.get('etiqueta', s['id'])}")
    walk((p.get("correspondence") or {}).get("modelo"), "Correspondencia")
    seen, out = set(), []
    for r in rows:
        key = tuple(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


__all__ = ["cell", "ev_text", "block_table", "project_labels", "all_evidence", "ORIGIN", "fmt_dt"]
