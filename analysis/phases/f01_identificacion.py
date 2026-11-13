"""Fase 1. Identificación y contexto de comunicación."""
from __future__ import annotations

import re

from ...llm.prompts import EVIDENCES, SYNTHESIS, s_arr, s_enum, s_obj, s_str
from ..base import Context, Phase, heuristic_synthesis, verif_merge
from ..helpers import NA, D, L, S, ev_cell, fmt_dt, hours_between, synth_from

GENRES = ["noticia", "nota_breve", "cronica", "reportaje", "entrevista", "analisis", "opinion", "editorial", "otro"]
GENRE_LABELS = {"noticia": "Noticia", "nota_breve": "Nota breve", "cronica": "Crónica", "reportaje": "Reportaje",
                "entrevista": "Entrevista", "analisis": "Análisis", "opinion": "Opinión", "editorial": "Editorial", "otro": "Otro"}

GENRE_ITEM = s_obj({"genero": s_enum(GENRES), "caracteristicas": s_arr(s_str()), "justificacion": s_str(),
                    "evidencias": EVIDENCES}, ["genero", "justificacion"])
SCHEMA = s_obj({
    "genero_n1": GENRE_ITEM, "genero_n2": GENRE_ITEM,
    "contexto_n1": s_str("Contexto editorial de publicación de la noticia 1 (sección, momento, enfoque de presentación)"),
    "contexto_n2": s_str(),
    "diferencias_presentacion": s_arr(s_obj({"aspecto": s_str(), "n1": s_str(), "n2": s_str(), "evidencias": EVIDENCES})),
    "sintesis": SYNTHESIS,
}, ["genero_n1", "genero_n2", "contexto_n1", "contexto_n2", "diferencias_presentacion", "sintesis"])

INSTRUCTIONS = """Fase 1 — Identificación y contexto de comunicación.
1) Clasifica el género periodístico de cada noticia y explica las características que lo justifican.
2) Caracteriza el contexto editorial de cada publicación a partir de lo observable (sección, fecha, firma,
   tipo de titular, subtítulo, recursos visibles). No supongas la línea editorial general del medio.
3) Señala diferencias de presentación editorial entre ambas (titular, subtítulo, firma, sección, recursos).
4) Elabora la síntesis de la fase."""


def headline_features(a: dict) -> dict:
    t = (a["meta"].get("titular") or "")
    return {
        "palabras": len(re.findall(r"\w+", t)),
        "cita": bool(re.search(r"[«“\"]", t)),
        "cifras": bool(re.search(r"\d|\b(dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\b", t, re.I)),
        "dos_puntos": ":" in t,
        "interrogacion": "?" in t, "exclamacion": "!" in t,
    }


class Fase1(Phase):
    number = 1
    title = "Identificación y contexto de comunicación"
    description = "Quién publica, cuándo, en qué sección y con qué género cada una de las noticias."
    sections = [("1.1", "Identificación de los medios y las noticias", "¿Qué datos identifican a cada publicación?"),
                ("1.2", "Caracterización del contexto editorial", "¿En qué marco editorial y con qué género se presenta cada noticia?")]

    def analyze(self, ctx: Context):
        sec = self.make_sections(self.sections)
        out = ctx.ask("fase1", INSTRUCTIONS, SCHEMA, description="Registra la fase 1.")
        ok = out is not None and "__error__" not in out
        a1, a2 = ctx.a1, ctx.a2
        m1, m2 = a1["meta"], a2["meta"]

        def lead(a):
            p = next((b for b in a["blocks"] if b["type"] == "paragraph"), None)
            return p["text"] if p else NA

        def genre(n):
            if not ok:
                return "Requiere modelo de lenguaje"
            g = D(out.get(f"genero_n{n}"))
            return GENRE_LABELS.get(g.get("genero"), S(g.get("genero"), NA))

        def src(a, k):
            s = a.get("meta_sources", {}).get(k)
            e = " · corregido por la persona usuaria" if k in (a.get("meta_edits") or {}) else ""
            return (f"Fuente: {s}" if s else "") + e

        rows = [
            {"label": "Medio", "n1": m1.get("medio") or NA, "n2": m2.get("medio") or NA},
            {"label": "Titular", "n1": m1.get("titular") or NA, "n2": m2.get("titular") or NA},
            {"label": "Subtítulo", "n1": m1.get("subtitulo") or NA, "n2": m2.get("subtitulo") or NA,
             "nota": "Bajada o sumario. Si procede de la metaetiqueta «description», puede no coincidir con lo visible."},
            {"label": "Entradilla (primer párrafo)", "n1": {"text": lead(a1), "ref": {"n": 1, "p": "P1"}},
             "n2": {"text": lead(a2), "ref": {"n": 2, "p": "P1"}}},
            {"label": "Publicación", "n1": fmt_dt(m1.get("fecha_publicacion")), "n2": fmt_dt(m2.get("fecha_publicacion")),
             "nota_n1": src(a1, "fecha_publicacion"), "nota_n2": src(a2, "fecha_publicacion")},
            {"label": "Actualización", "n1": fmt_dt(m1.get("fecha_actualizacion")) if m1.get("fecha_actualizacion") != m1.get("fecha_publicacion") else "Sin actualización indicada",
             "n2": fmt_dt(m2.get("fecha_actualizacion")) if m2.get("fecha_actualizacion") != m2.get("fecha_publicacion") else "Sin actualización indicada"},
            {"label": "Autoría", "n1": ", ".join(m1.get("autoria") or []) or NA, "n2": ", ".join(m2.get("autoria") or []) or NA},
            {"label": "Sección", "n1": m1.get("seccion") or NA, "n2": m2.get("seccion") or NA,
             "nota_n1": src(a1, "seccion"), "nota_n2": src(a2, "seccion")},
            {"label": "Género periodístico", "n1": genre(1), "n2": genre(2), "origen": "modelo" if ok else ""},
            {"label": "Enlace", "n1": {"link": a1.get("url")} if a1.get("url") else "Texto introducido manualmente",
             "n2": {"link": a2.get("url")} if a2.get("url") else "Texto introducido manualmente"},
            {"label": "Estado de lectura", "n1": a1.get("status_label"), "n2": a2.get("status_label")},
        ]
        s11 = sec["1.1"]
        s11.compare("Ficha de identificación", rows, description="Tabla de doble entrada con los metadatos recuperados de cada publicación.",
                    origin="programatico" if not ok else "mixto")
        gap = hours_between(m1.get("fecha_publicacion"), m2.get("fecha_publicacion"))
        if gap is not None:
            later = 2 if gap > 0 else 1
            s11.text(f"La noticia {later} se publicó {abs(gap)} horas después que la otra "
                     f"({round(abs(gap) / 24, 1)} días).", origin="programatico", title="Distancia entre publicaciones")

        s12 = sec["1.2"]
        hf = {1: headline_features(a1), 2: headline_features(a2)}
        figs = {n: [b for b in ctx.articles[n - 1]["blocks"] if b["type"] == "figure"] for n in (1, 2)}
        si = lambda v: "Sí" if v else "No"
        s12.compare("Rasgos de presentación observables", [
            {"label": "Palabras del titular", "n1": hf[1]["palabras"], "n2": hf[2]["palabras"]},
            {"label": "Cita textual en el titular", "n1": si(hf[1]["cita"]), "n2": si(hf[2]["cita"])},
            {"label": "Cifras en el titular", "n1": si(hf[1]["cifras"]), "n2": si(hf[2]["cifras"])},
            {"label": "Titular con dos puntos", "n1": si(hf[1]["dos_puntos"]), "n2": si(hf[2]["dos_puntos"])},
            {"label": "Subtítulo", "n1": si(m1.get("subtitulo")), "n2": si(m2.get("subtitulo"))},
            {"label": "Firma personal", "n1": si(m1.get("autoria")), "n2": si(m2.get("autoria"))},
            {"label": "Subtítulos internos", "n1": sum(1 for b in a1["blocks"] if b["type"] == "heading"),
             "n2": sum(1 for b in a2["blocks"] if b["type"] == "heading")},
            {"label": "Imágenes", "n1": len(figs[1]), "n2": len(figs[2])},
        ], description="Rasgos calculados a partir del texto y la estructura extraídos.", origin="programatico")
        if ok:
            cards = []
            for n in (1, 2):
                g = D(out.get(f"genero_n{n}"))
                cards.append({"n": n, "title": f"{ctx.label(n)} — {GENRE_LABELS.get(g.get('genero'), S(g.get('genero')))}",
                              "fields": [{"label": "Características", "value": S(g.get("caracteristicas"))},
                                         {"label": "Justificación", "value": S(g.get("justificacion"))},
                                         {"label": "Contexto editorial", "value": S(out.get(f"contexto_n{n}"))}],
                              "ev": L(g.get("evidencias"))})
            s12.add("cards", "Género y contexto editorial", items=cards, origin="modelo",
                    description="Clasificación del género y lectura del contexto editorial con sus evidencias.")
            diffs = L(out.get("diferencias_presentacion"))
            if diffs:
                s12.table("Diferencias en la presentación editorial",
                          [{"key": "aspecto", "label": "Aspecto"}, {"key": "n1", "label": "Noticia 1"},
                           {"key": "n2", "label": "Noticia 2"}, {"key": "ev", "label": "Evidencias", "type": "evidencia"}],
                          [{"aspecto": S(d.get("aspecto")), "n1": S(d.get("n1")), "n2": S(d.get("n2")), "ev": ev_cell(d.get("evidencias"))}
                           for d in diffs if isinstance(d, dict)], origin="modelo")
        else:
            self.llm_failed(s12, out, "La clasificación del género y la lectura del contexto editorial")
            s12.status = "parcial" if out is None else "error"

        synthesis, origin = synth_from(out)
        if not synthesis:
            diffs = []
            if gap is not None:
                diffs.append(f"Las publicaciones están separadas por {abs(gap)} horas.")
            if hf[1]["cita"] != hf[2]["cita"]:
                diffs.append("Solo una de las noticias utiliza una cita textual en el titular.")
            synthesis = heuristic_synthesis(diffs, [], ["Sin modelo de lenguaje no se clasifica el género ni se interpreta el contexto editorial."])
            origin = "programatico"
        return list(sec.values()), synthesis, origin, verif_merge(out)


PHASE = Fase1()
