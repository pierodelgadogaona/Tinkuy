"""Resumen ejecutivo, síntesis comparativa general y limitaciones del análisis."""
from __future__ import annotations

from datetime import datetime

from ..config import settings
from ..geo import geocoder
from ..llm.prompts import EVIDENCES, s_arr, s_obj, s_str
from ..nlp import engine
from .base import Context
from .helpers import D, L, S

QUESTIONS = [
    ("coincidencias", "¿En qué coinciden las noticias?"),
    ("diferencias", "¿Cuáles son sus principales diferencias?"),
    ("acontecimientos", "¿Qué acontecimientos prioriza cada una?"),
    ("actores", "¿Qué actores reciben mayor protagonismo?"),
    ("perspectivas", "¿Qué perspectivas se privilegian?"),
    ("semantica", "¿Qué diferencias existen en la construcción semántica?"),
    ("datos", "¿Qué diferencias aparecen en el tratamiento de los datos?"),
    ("lenguaje", "¿Qué diferencias existen en la presentación lingüística?"),
    ("espacios", "¿Cómo se representan los espacios y las relaciones entre actores?"),
    ("conclusiones", "¿Qué conclusiones generales pueden extraerse de la comparación?"),
]
SCHEMA = s_obj({
    "titulo_informe": s_str("Título breve y descriptivo del estudio"),
    "acontecimiento": s_str("Descripción neutral del acontecimiento en una frase"),
    "resumen_ejecutivo": s_arr(s_str(), "Entre 3 y 5 hallazgos principales, cada uno en una frase"),
    "respuestas": s_obj({k: s_str("Respuesta directa en una o dos frases (máximo 45 palabras)") for k, _ in QUESTIONS}, [k for k, _ in QUESTIONS]),
    "limitaciones": s_arr(s_str(), "Limitaciones interpretativas del estudio"),
    "evidencias": EVIDENCES,
}, ["titulo_informe", "acontecimiento", "resumen_ejecutivo", "respuestas", "limitaciones"])
INSTRUCTIONS = """Síntesis comparativa general.
Con las síntesis de las diez fases (abajo) y los textos, redacta:
1) Un resumen ejecutivo de las principales diferencias y semejanzas (3–5 hallazgos de una frase).
2) Respuestas directas a las diez preguntas: cada una en una o dos frases (máximo 45 palabras), integrando las fases
   sin repetirlas una por una ni añadir salvedades metodológicas.
3) Limitaciones interpretativas. Mantén afirmaciones prudentes: se comparan dos noticias concretas, no las líneas
   editoriales de los medios."""


def phase_digest(project: dict) -> str:
    lines = []
    for k in sorted(project.get("phases", {}), key=lambda x: int(x)):
        ph = project["phases"][k]
        s = D(ph.get("sintesis"))
        if not s:
            continue
        lines.append(f"FASE {k} — {ph.get('titulo')}\n  Diferencias: {S(s.get('diferencias'))}\n  Semejanzas: {S(s.get('semejanzas'))}\n"
                     f"  Conclusiones: {S(s.get('conclusiones'))}")
    return "\n".join(lines)


def limitations(project: dict) -> list[dict]:
    out = []
    for a in project["articles"]:
        if a["status"] == "parcial":
            out.append({"tipo": "extraccion", "texto": f"La noticia {a['n']} se leyó parcialmente: {a['status_detail']} Los análisis que dependen del texto completo están incompletos."})
        if a["status"] == "manual":
            out.append({"tipo": "extraccion", "texto": f"El texto de la noticia {a['n']} fue introducido manualmente y no se verificó contra la página original."})
        if a.get("method", "").endswith("jsonld"):
            out.append({"tipo": "extraccion", "texto": f"El cuerpo de la noticia {a['n']} procede de metadatos estructurados; la división en párrafos puede no coincidir con la original."})
        edits = a.get("meta_edits") or {}
        if edits:
            out.append({"tipo": "extraccion", "texto": f"Metadatos de la noticia {a['n']} corregidos manualmente: {', '.join(edits.keys())}."})
    corr = (project.get("correspondence") or {}).get("final") or {}
    if corr.get("decision") == "usuario" and corr.get("porcentaje") is not None:
        out.append({"tipo": "metodo", "texto": f"La correspondencia entre las noticias fue del {corr['porcentaje']} %, por debajo del umbral del {corr.get('umbral', 40)} %; "
                                               "la persona usuaria decidió continuar. Las diferencias pueden deberse a que narran hechos distintos."})
    if corr.get("relacion") == "relacionados":
        out.append({"tipo": "metodo", "texto": "Las noticias tratan acontecimientos relacionados pero no idénticos: las diferencias pueden deberse a que narran sucesos distintos."})
    if corr.get("fuente") == "heuristica":
        out.append({"tipo": "metodo", "texto": "El porcentaje de correspondencia se calculó solo con indicadores programáticos (entidades, lugares, vocabulario, cifras y fechas), sin modelo de lenguaje."})
    st = settings.llm_status()
    if not st["configurado"]:
        out.append({"tipo": "modelo", "texto": "No hay modelo de lenguaje configurado: solo se presentan los análisis programáticos y heurísticos; las interpretaciones semánticas, retóricas y de representación no se realizaron."})
    elif settings.llm_provider == "replay":
        out.append({"tipo": "modelo", "texto": "Informe generado en modo de demostración: las respuestas del modelo de lenguaje proceden de archivos pregrabados, no de una consulta en vivo."})
    else:
        out.append({"tipo": "modelo", "texto": f"Las interpretaciones fueron generadas por un modelo de lenguaje ({st['modelo']}); deben revisarse críticamente junto a sus evidencias."})
    tot = {"total": 0, "no_localizada": 0, "aproximada": 0}
    for ph in (project.get("phases") or {}).values():
        v = ph.get("verificacion") or {}
        for k in tot:
            tot[k] += v.get(k, 0)
    if tot["total"]:
        out.append({"tipo": "evidencia", "texto": f"Se verificaron {tot['total']} evidencias contra el texto: {tot['no_localizada']} no se localizaron "
                                                 f"literalmente y {tot['aproximada']} coinciden de forma aproximada. Las no localizadas se marcan y no deben sustentar conclusiones."})
    if engine.load() is None:
        out.append({"tipo": "pln", "texto": "Los rasgos gramaticales se estimaron con reglas morfológicas (sin etiquetador spaCy): son aproximados y no incluyen la distribución completa de categorías."})
    if (project.get("options") or {}).get("geocodificacion"):
        out.append({"tipo": "geo", "texto": f"Las distancias entre lugares se calcularon en línea recta entre centroides o puntos aproximados de OpenStreetMap; no son recorridos reales. {geocoder.status()['detalle']}"})
    else:
        out.append({"tipo": "geo", "texto": "El análisis territorial se basa en los lugares que nombra el texto y en el nivel de precisión con que los nombra; no se geolocalizan ni se representan sobre un mapa."})
    errs = [f"Fase {k}" for k, ph in (project.get("phases") or {}).items() if ph.get("estado") in ("error", "parcial")]
    if errs:
        out.append({"tipo": "proceso", "texto": f"Algunas fases tuvieron errores o quedaron incompletas: {', '.join(errs)}. Pueden repetirse individualmente."})
    out.append({"tipo": "alcance", "texto": "La comparación se limita a dos publicaciones; no permite generalizar sobre la línea editorial ni la ideología de los medios."})
    return out


def run(project: dict) -> dict:
    ctx = Context(project)
    out = ctx.ask("sintesis", INSTRUCTIONS, SCHEMA, extra="SÍNTESIS DE LAS FASES\n" + phase_digest(project), include_articles=True,
                  description="Registra la síntesis general.", max_tokens=6000)
    ok = out is not None and "__error__" not in out
    a1, a2 = project["articles"]
    f1, f2 = project["features"]["1"], project["features"]["2"]
    if ok:
        res = {"origen": "modelo", "titulo": S(out.get("titulo_informe")), "acontecimiento": S(out.get("acontecimiento")),
               "resumen_ejecutivo": [S(x) for x in L(out.get("resumen_ejecutivo"))],
               "respuestas": [{"clave": k, "pregunta": q, "respuesta": S(D(out.get("respuestas")).get(k))} for k, q in QUESTIONS],
               "limitaciones_modelo": [S(x) for x in L(out.get("limitaciones"))], "verificacion": out.get("__verificacion__")}
    else:
        m1, m2 = f1["metricas"], f2["metricas"]
        facts = [f"La noticia 1 ({a1['meta'].get('medio')}) tiene {m1['palabras']} palabras y la noticia 2 ({a2['meta'].get('medio')}), {m2['palabras']}.",
                 f"Texto entre comillas: {f1['citas']['pct_texto_citado']} % frente a {f2['citas']['pct_texto_citado']} %.",
                 f"Vocabulario emotivo: {f1['lexico']['emotivas']['por_1000']} frente a {f2['lexico']['emotivas']['por_1000']} términos por 1.000 palabras.",
                 f"Legibilidad (INFLESZ): {f1['legibilidad'].get('inflesz')} frente a {f2['legibilidad'].get('inflesz')}."]
        res = {"origen": "programatico", "titulo": f"{a1['meta'].get('medio')} y {a2['meta'].get('medio')}: análisis comparativo",
               "acontecimiento": "", "resumen_ejecutivo": facts,
               "respuestas": [{"clave": k, "pregunta": q, "respuesta": ""} for k, q in QUESTIONS], "limitaciones_modelo": [],
               "nota": "Sin modelo de lenguaje: el resumen ejecutivo se limita a hechos calculados y la síntesis interpretativa no se genera."}
        if out and "__error__" in out:
            res["error"] = out["__error__"]
    res["limitaciones"] = limitations(project)
    res["uso"] = ctx.usage
    res["generado"] = datetime.now().isoformat(timespec="seconds")
    return res
