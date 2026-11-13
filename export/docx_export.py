"""Exportación del informe a DOCX: tablas nativas de Word y figuras capturadas del propio informe."""
from __future__ import annotations

import io

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .common import ORIGIN, block_table, fmt_dt, project_labels

INK = RGBColor(0x1E, 0x22, 0x27)
MUTED = RGBColor(0x6C, 0x70, 0x78)
N1 = RGBColor(0x2F, 0x67, 0xA8)
N2 = RGBColor(0xA8, 0x5D, 0x16)
FIGURE_KINDS = {"bars", "radar", "timeline", "pubchrono", "graph", "map", "territory", "venn", "wordcloud", "flow", "blocks", "diverging",
                "paragraph_profile", "cohesion", "temporal3", "argument", "scale", "cards", "gallery"}


def _shade(cell, hex_fill: str):
    tc = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc.append(shd)


def _table(doc, head, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(head))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j, h in enumerate(head):
        c = t.rows[0].cells[j]
        c.text = ""
        run = c.paragraphs[0].add_run(str(h))
        run.bold = True
        run.font.size = Pt(8.5)
        _shade(c, "EFEDE6")
    for row in rows:
        cells = t.add_row().cells
        for j, v in enumerate(row[: len(head)]):
            cells[j].text = ""
            run = cells[j].paragraphs[0].add_run(str(v))
            run.font.size = Pt(8.5)
    doc.add_paragraph()
    return t


def _para(doc, text, *, size=10.5, italic=False, color=None, bold=False, style=None, space_after=4):
    p = doc.add_paragraph(style=style)
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.italic = italic
    r.bold = bold
    if color:
        r.font.color.rgb = color
    p.paragraph_format.space_after = Pt(space_after)
    return p


def _bullets(doc, items):
    for it in items:
        if it:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(str(it)).font.size = Pt(10)


def build_docx(p: dict, base: str) -> tuple[bytes, str]:
    figures, note = {}, ""
    try:
        from .pdf import capture_figures
        figures = capture_figures(base, p["id"])
    except Exception as e:  # sin navegador: el documento se genera sin figuras
        note = f"Figuras no incluidas ({type(e).__name__})."
    labels = project_labels(p)
    a1, a2 = p["articles"]
    syn = p.get("synthesis") or {}
    doc = Document()
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21)
    for side in ("left_margin", "right_margin"):
        setattr(sec, side, Cm(2.2))
    sec.top_margin, sec.bottom_margin = Cm(2), Cm(2)
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    for lvl, size in ((1, 18), (2, 14), (3, 12)):
        hs = doc.styles[f"Heading {lvl}"]
        hs.font.name = "Georgia"
        hs.font.size = Pt(size)
        hs.font.color.rgb = INK
        hs.font.bold = lvl == 3

    # Portada
    _para(doc, "TINKUY · ANÁLISIS COMPARATIVO DE NOTICIAS", size=9, color=MUTED, bold=True)
    doc.add_heading(syn.get("titulo") or p.get("title", "Análisis comparativo"), level=0)
    if syn.get("acontecimiento"):
        _para(doc, syn["acontecimiento"], size=12, italic=True)
    for a, col in ((a1, N1), (a2, N2)):
        _para(doc, f"Noticia {a['n']} · {a['meta'].get('medio', '')}", size=10, bold=True, color=col, space_after=0)
        _para(doc, a["meta"].get("titular", ""), size=11)
        _para(doc, f"{fmt_dt(a['meta'].get('fecha_publicacion'))} · {a.get('url') or 'texto manual'}", size=9, color=MUTED)
    _para(doc, f"Análisis realizado el {fmt_dt(p.get('analizado') or p.get('updated'))} · Relación: {((p.get('correspondence') or {}).get('final') or {}).get('etiqueta', '')}",
          size=9, color=MUTED)
    if any(l.get("texto", "").startswith("Informe generado en modo de demostración") for l in syn.get("limitaciones", [])):
        _para(doc, "Modo de demostración: las interpretaciones proceden de respuestas pregrabadas.", size=9, italic=True, color=N2)
    doc.add_page_break()

    doc.add_heading("Identificación de las noticias", level=1)
    _table(doc, ["", labels["n1"], labels["n2"]], [
        ["Titular", a1["meta"].get("titular", ""), a2["meta"].get("titular", "")],
        ["Publicación", fmt_dt(a1["meta"].get("fecha_publicacion")), fmt_dt(a2["meta"].get("fecha_publicacion"))],
        ["Autoría", ", ".join(a1["meta"].get("autoria") or []) or "—", ", ".join(a2["meta"].get("autoria") or []) or "—"],
        ["Sección", a1["meta"].get("seccion") or "—", a2["meta"].get("seccion") or "—"],
        ["Estado de lectura", a1.get("status_label", ""), a2.get("status_label", "")],
        ["Enlace", a1.get("url") or "texto manual", a2.get("url") or "texto manual"]])

    corr = p.get("correspondence") or {}
    doc.add_heading("Comprobación de correspondencia", level=1)
    f = corr.get("final") or {}
    _para(doc, f"{f.get('etiqueta', '')} · confianza {f.get('confianza', '')} · {'modelo de lenguaje' if f.get('fuente') == 'modelo' else 'heurística'}"
          + (" · confirmada por la persona usuaria" if f.get("confirmada") else ""), bold=True)
    m = corr.get("modelo") or {}
    _para(doc, m.get("explicacion_relacion") or (corr.get("heuristica") or {}).get("explicacion", ""))
    if m:
        _bullets(doc, [f"Coincidencia — {x.get('aspecto')}: {x.get('descripcion')}" for x in m.get("coincidencias", [])])
        _bullets(doc, [f"Diferencia — {x.get('aspecto')}: {x.get('descripcion')}" for x in m.get("diferencias", [])])

    doc.add_heading("Resumen ejecutivo", level=1)
    _bullets(doc, syn.get("resumen_ejecutivo", []))

    for k, ph in sorted((p.get("phases") or {}).items(), key=lambda kv: int(kv[0])):
        doc.add_page_break()
        doc.add_heading(f"Fase {ph.get('posicion', k)}. {ph.get('titulo', '')}", level=1)
        _para(doc, ph.get("descripcion", ""), italic=True, color=MUTED)
        for s in ph.get("secciones", []):
            doc.add_heading(f"{s.get('etiqueta', s['id'])} {s['title']}", level=2)
            if s.get("question"):
                _para(doc, s["question"], italic=True, color=MUTED)
            if s.get("status") != "ok":
                _para(doc, f"Estado: {s.get('status_label')}. {s.get('status_note', '')}", size=9, color=MUTED)
            for b in s.get("blocks", []):
                kind = b.get("kind")
                if kind == "notice":
                    _para(doc, f"[{b.get('status_label')}] {b.get('text')}", size=9.5, italic=True, color=MUTED)
                    continue
                if b.get("title"):
                    doc.add_heading(b["title"], level=3)
                meta = ORIGIN.get(b.get("origin", ""), "")
                if b.get("description") or meta:
                    _para(doc, f"{b.get('description', '')} [{meta}]".strip(), size=9, color=MUTED)
                if kind == "text":
                    for line in str(b.get("text", "")).split("\n"):
                        _para(doc, line)
                elif kind in FIGURE_KINDS and b["id"] in figures:
                    doc.add_picture(io.BytesIO(figures[b["id"]]), width=Cm(16.4))
                    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                    if kind in ("graph", "timeline", "map", "territory", "cards"):
                        t = block_table(b, labels)
                        if t and t[1]:
                            _table(doc, *t)
                else:
                    t = block_table(b, labels)
                    if t and t[1]:
                        _table(doc, *t)
                if b.get("interpretation"):
                    _para(doc, b["interpretation"], italic=True)
        sy = ph.get("sintesis") or {}
        if sy:
            doc.add_heading(f"Síntesis de la fase {k}", level=2)
            for key, lbl in (("diferencias", "Diferencias"), ("semejanzas", "Semejanzas"), ("patrones", "Patrones"),
                             ("destaca_n1", "Destaca la noticia 1"), ("destaca_n2", "Destaca la noticia 2"),
                             ("conclusiones", "Conclusiones"), ("limitaciones", "Limitaciones")):
                v = sy.get(key)
                if not v:
                    continue
                _para(doc, lbl, bold=True, size=10, space_after=1)
                if isinstance(v, list):
                    _bullets(doc, v)
                else:
                    _para(doc, str(v))

    doc.add_page_break()
    doc.add_heading("Síntesis comparativa general", level=1)
    for q in syn.get("respuestas", []):
        _para(doc, q["pregunta"], bold=True, space_after=1)
        _para(doc, q.get("respuesta") or "Requiere modelo de lenguaje.")
    doc.add_heading("Limitaciones del análisis", level=1)
    _bullets(doc, [l.get("texto") for l in syn.get("limitaciones", [])] + list(syn.get("limitaciones_modelo", [])))
    doc.add_heading("Referencias", level=1)
    for a in (a1, a2):
        mm = a["meta"]
        _para(doc, f"{', '.join(mm.get('autoria') or []) or mm.get('medio', '')} ({fmt_dt(mm.get('fecha_publicacion'))}). {mm.get('titular', '')}. "
                   f"{mm.get('medio', '')}. {a.get('url') or 'Texto introducido manualmente'}. Consultado el {fmt_dt(a.get('extracted_at'))}.")
    if note:
        _para(doc, note, size=8.5, italic=True, color=MUTED)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue(), note
