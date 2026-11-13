"""Exportación de todas las tablas y datos del informe a XLSX (una hoja por tabla)."""
from __future__ import annotations

import io
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .common import ORIGIN, all_evidence, block_table, fmt_dt, project_labels

HEAD_FILL = PatternFill("solid", fgColor="EFEDE6")
HEAD_FONT = Font(bold=True, color="1E2227")


def _sheet_name(wb, base: str) -> str:
    base = re.sub(r"[\[\]\:\*\?\/\\]", " ", base).strip()[:31] or "Hoja"
    name, i = base, 2
    while name in wb.sheetnames:
        suffix = f" ({i})"
        name = base[: 31 - len(suffix)] + suffix
        i += 1
    return name


def _write(ws, head, rows, title=None, note=None):
    r = 1
    if title:
        ws.cell(row=r, column=1, value=title).font = Font(bold=True, size=12)
        r += 1
    if note:
        ws.cell(row=r, column=1, value=note).font = Font(italic=True, color="6C7078")
        r += 1
    if title or note:
        r += 1
    for j, h in enumerate(head, 1):
        c = ws.cell(row=r, column=j, value=h)
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for row in rows:
        r += 1
        for j, v in enumerate(row, 1):
            try:
                num = float(v) if isinstance(v, str) and re.fullmatch(r"-?\d+(\.\d+)?", v) else None
            except ValueError:
                num = None
            c = ws.cell(row=r, column=j, value=num if num is not None else v)
            c.alignment = Alignment(wrap_text=True, vertical="top")
    for j in range(1, len(head) + 1):
        width = max([len(str(head[j - 1]))] + [len(str(row[j - 1])) for row in rows if j - 1 < len(row)] + [8])
        ws.column_dimensions[get_column_letter(j)].width = min(70, max(10, width * 0.9))
    ws.freeze_panes = ws.cell(row=(4 if (title or note) else 2), column=1)


def build_xlsx(p: dict) -> bytes:
    wb = Workbook()
    labels = project_labels(p)
    a1, a2 = p["articles"]
    ws = wb.active
    ws.title = "Resumen"
    syn = p.get("synthesis") or {}
    corr = (p.get("correspondence") or {}).get("final") or {}
    rows = [["Título", syn.get("titulo") or p.get("title", "")], ["Acontecimiento", syn.get("acontecimiento", "")],
            ["Fecha del análisis", fmt_dt(p.get("analizado") or p.get("updated"))], ["Relación entre noticias", corr.get("etiqueta", "")],
            ["Confianza", corr.get("confianza", "")], ["Origen de la síntesis", ORIGIN.get(syn.get("origen", ""), "")]]
    for a in (a1, a2):
        m = a["meta"]
        rows += [[f"Noticia {a['n']} · medio", m.get("medio", "")], [f"Noticia {a['n']} · titular", m.get("titular", "")],
                 [f"Noticia {a['n']} · publicación", fmt_dt(m.get("fecha_publicacion"))], [f"Noticia {a['n']} · enlace", a.get("url", "")],
                 [f"Noticia {a['n']} · estado", a.get("status_label", "")]]
    rows += [["Resumen ejecutivo", "\n".join(f"• {x}" for x in syn.get("resumen_ejecutivo", []))]]
    for q in syn.get("respuestas", []):
        rows.append([q["pregunta"], q.get("respuesta", "")])
    _write(ws, ["Campo", "Valor"], rows, title="Tinkuy")
    ws.column_dimensions["B"].width = 100

    # textos extraídos
    wt = wb.create_sheet("Textos")
    trows = []
    for a in (a1, a2):
        for b in a["blocks"]:
            if b["type"] in ("paragraph", "heading"):
                trows.append([f"N{a['n']}", b["id"], "Subtítulo" if b["type"] == "heading" else "Párrafo", b["text"], b.get("palabras", "")])
            elif b["type"] == "figure":
                trows.append([f"N{a['n']}", b["id"], "Imagen", b.get("caption", ""), ""])
    _write(wt, ["Noticia", "Unidad", "Tipo", "Texto", "Palabras"], trows, title="Textos extraídos")
    wt.column_dimensions["D"].width = 110

    for k, ph in sorted((p.get("phases") or {}).items(), key=lambda kv: int(kv[0])):
        for s in ph.get("secciones", []):
            for b in s.get("blocks", []):
                t = block_table(b, labels)
                if not t or not t[1]:
                    continue
                head, rows = t
                name = _sheet_name(wb, f"{s.get('etiqueta', s['id'])} {b.get('title') or s['title']}")
                _write(wb.create_sheet(name), head, rows, title=f"Fase {ph.get('posicion', k)} · {s.get('etiqueta', s['id'])} · {b.get('title', '')}",
                       note=f"{ORIGIN.get(b.get('origin', ''), '')}. {b.get('description', '')}".strip())
    ev = all_evidence(p)
    if ev:
        _write(wb.create_sheet("Evidencias"), ["Dónde", "Noticia", "Unidad", "Fragmento", "Verificación", "Unidad indicada originalmente"], ev,
               title="Evidencias textuales y su verificación")
    lim = [[l.get("tipo", ""), l.get("texto", "")] for l in syn.get("limitaciones", [])]
    if lim:
        _write(wb.create_sheet("Limitaciones"), ["Tipo", "Limitación"], lim, title="Limitaciones del análisis")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
