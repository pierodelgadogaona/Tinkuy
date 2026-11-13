"""Detección de la naturaleza del acontecimiento y plan adaptativo de indicadores (sección 6)."""
from __future__ import annotations

import re
from datetime import datetime

from ..nlp.text import norm_key
from ..llm.prompts import EVIDENCES, s_arr, s_enum, s_obj, s_str
from .base import Context

TYPE_KEYWORDS = {
    "accidente": ["accidente", "despiste", "despisto", "choque", "volcadura", "volco", "siniestro", "atropello", "colision", "descarrilamiento", "derrumbe"],
    "sanitario": ["contagio", "contagios", "brote", "epidemia", "pandemia", "infectados", "vacuna", "virus", "dengue", "casos confirmados", "minsa"],
    "delito": ["robo", "asalto", "hurto", "delincuentes", "banda criminal", "extorsion", "sicario", "asesinato", "secuestro", "estafa"],
    "politico": ["congreso", "congresista", "ministro", "presidente de la republica", "gobierno", "vacancia", "partido", "elecciones", "censura", "premier"],
    "protesta": ["protesta", "marcha", "manifestantes", "planton", "huelga", "bloqueo", "paro", "movilizacion"],
    "judicial": ["fiscalia", "fiscal", "juez", "prision preventiva", "investigacion preparatoria", "sentencia", "imputado", "poder judicial"],
    "ambiental": ["derrame", "contaminacion", "incendio forestal", "deforestacion", "especies", "ecosistema", "relave"],
    "desastre": ["sismo", "terremoto", "huaico", "inundacion", "lluvias intensas", "damnificados", "desborde", "tsunami"],
    "economico": ["inflacion", "precios", "pbi", "exportaciones", "mercado", "aranceles", "tipo de cambio", "inversion"],
    "transporte": ["bus", "buses", "transporte", "pasajeros", "carretera", "panamericana", "transito", "sutran", "conductor"],
}
TYPE_LABELS = {"accidente": "Accidente", "sanitario": "Sanitario o epidemiológico", "delito": "Delito o seguridad ciudadana",
               "politico": "Político o institucional", "protesta": "Protesta social", "judicial": "Judicial",
               "ambiental": "Ambiental", "desastre": "Desastre o emergencia", "economico": "Económico",
               "transporte": "Transporte y seguridad vial"}
INDICATOR_CATALOG = {
    "accidente": [("fallecidos", "Personas fallecidas", "personas", "cuantitativo"),
                  ("heridos", "Personas heridas", "personas", "cuantitativo"),
                  ("graves", "Personas en estado grave u hospitalizadas", "personas", "cuantitativo"),
                  ("ocupantes", "Pasajeros u ocupantes implicados", "personas", "cuantitativo"),
                  ("hora", "Hora del suceso", "hora", "cualitativo"),
                  ("lugar_exacto", "Lugar exacto del suceso", "", "cualitativo"),
                  ("causa", "Causa atribuida", "", "cualitativo"),
                  ("investigacion", "Estado de la investigación", "", "cualitativo"),
                  ("responsables", "Responsables señalados", "", "cualitativo")],
    "sanitario": [("infectados", "Personas infectadas", "personas", "cuantitativo"),
                  ("fallecidos", "Personas fallecidas", "personas", "cuantitativo"),
                  ("hospitalizados", "Personas hospitalizadas", "personas", "cuantitativo"),
                  ("tasa", "Tasa de contagio o incidencia", "%", "cuantitativo"),
                  ("zonas", "Distribución geográfica", "", "cualitativo"),
                  ("riesgo", "Grupos de riesgo", "", "cualitativo"),
                  ("medidas", "Medidas sanitarias", "", "cualitativo")],
    "delito": [("valor", "Valor de los bienes sustraídos", "moneda", "cuantitativo"),
               ("afectados", "Personas afectadas", "personas", "cuantitativo"),
               ("sospechosos", "Número de sospechosos", "personas", "cuantitativo"),
               ("detenidos", "Detenciones", "personas", "cuantitativo"),
               ("secuencia", "Secuencia del delito", "", "cualitativo"),
               ("evidencias", "Evidencias mencionadas", "", "cualitativo"),
               ("investigacion", "Estado de la investigación", "", "cualitativo")],
    "politico": [("actores", "Actores políticos implicados", "", "cualitativo"),
                 ("decisiones", "Decisiones o votaciones", "", "cualitativo"),
                 ("posiciones", "Posiciones enfrentadas", "", "cualitativo"),
                 ("consecuencias", "Consecuencias políticas", "", "cualitativo")],
    "protesta": [("participantes", "Número de participantes", "personas", "cuantitativo"),
                 ("organizaciones", "Organizaciones participantes", "", "cualitativo"),
                 ("demandas", "Demandas", "", "cualitativo"),
                 ("actuacion", "Actuación institucional o policial", "", "cualitativo"),
                 ("heridos_detenidos", "Heridos o detenidos", "personas", "cuantitativo")],
    "judicial": [("etapa", "Etapa del proceso", "", "cualitativo"),
                 ("delitos", "Delitos investigados", "", "cualitativo"),
                 ("medidas", "Medidas cautelares o resoluciones", "", "cualitativo"),
                 ("partes", "Partes procesales", "", "cualitativo")],
    "ambiental": [("superficie", "Superficie afectada", "ha", "cuantitativo"),
                  ("contaminacion", "Niveles de contaminación", "", "cuantitativo"),
                  ("especies", "Especies involucradas", "", "cualitativo"),
                  ("zonas", "Zonas de riesgo", "", "cualitativo")],
    "desastre": [("victimas", "Víctimas mortales", "personas", "cuantitativo"),
                 ("damnificados", "Damnificados", "personas", "cuantitativo"),
                 ("viviendas", "Viviendas afectadas", "viviendas", "cuantitativo"),
                 ("respuesta", "Respuesta y ayuda", "", "cualitativo")],
    "economico": [("cifras", "Cifras económicas principales", "", "cuantitativo"),
                  ("variacion", "Variación porcentual", "%", "cuantitativo"),
                  ("sectores", "Sectores afectados", "", "cualitativo")],
    "transporte": [("empresa_antecedentes", "Antecedentes de la empresa u operador", "", "cualitativo"),
                   ("autorizacion", "Situación de la autorización o permisos", "", "cualitativo"),
                   ("infracciones", "Infracciones registradas", "infracciones", "cuantitativo"),
                   ("afectacion_via", "Afectación de la vía o del tránsito", "", "cualitativo")],
}

CONDITIONAL_SECTIONS = {
    "3.4": "Evolución y actualización del acontecimiento",
    "4.1": "Identificación de lugares", "4.2": "Recorridos, desplazamientos y traslados",
    "4.3": "Distribución territorial", "4.4": "Representación espacial",
    "6.1": "Inventario de datos cuantitativos", "6.2": "Comparación de cifras",
    "6.3": "Contextualización de los datos", "6.4": "Visualización cuantitativa",
    "8.3": "Representación social e identitaria", "8.5": "Relaciones de poder",
    "8.6": "Representación política e ideológica", "8.7": "Culpabilización, victimización y responsabilidad",
    "10.2": "Imagen principal", "10.3": "Imágenes secundarias", "10.4": "Otros recursos multimedia",
}
MOVEMENT = re.compile(r"\b(traslad\w+|evacuad\w+|recorrido|recorrió|partió|partieron|llegó|llegaron|se dirigía|se dirigían|"
                      r"marcharon|marcha|huyó|huyeron|desplaz\w+|ruta|trayecto|hacia|desde .{3,40} hasta)\b", re.I)
STATE_ORG = re.compile(r"(ministerio|gobierno|congreso|policía|fiscalía|municipalidad|superintendencia|poder judicial|"
                       r"defensoría|contraloría|presidencia|estado|alcald|ministr)", re.I)


def heuristic_types(ctx: Context) -> list[dict]:
    text = norm_key(" ".join(b["text"] for a in ctx.articles for b in a["blocks"] if b["type"] == "paragraph")
                    + " " + " ".join(a["meta"].get("titular") or "" for a in ctx.articles))
    scores = {}
    for t, kws in TYPE_KEYWORDS.items():
        s = sum(len(re.findall(r"\b" + re.escape(k) + r"\w*", text)) for k in kws)
        if s >= 2:
            scores[t] = s
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    return [{"tipo": t, "etiqueta": TYPE_LABELS[t], "peso": "principal" if i == 0 else "secundario",
             "puntuacion": s, "justificacion": f"{s} términos característicos de esta categoría en los textos."}
            for i, (t, s) in enumerate(ranked[:3])]


def availability(ctx: Context) -> dict[str, dict]:
    """Comprobaciones programáticas de disponibilidad de datos para las secciones condicionales."""
    out = {}
    def blocks(n, kinds):
        return [b for b in ctx.articles[n - 1]["blocks"] if b["type"] in kinds]
    nums = {n: [d for d in ctx.f[n]["cifras"] if d["tipo"] in ("cantidad", "porcentaje", "moneda", "medida", "cantidad_indeterminada")] for n in (1, 2)}
    places = {n: [e for e in ctx.f[n]["entidades"] if e["tipo"] == "lugar"] for n in (1, 2)}
    persons = {n: [e for e in ctx.f[n]["entidades"] if e["tipo"] == "persona"] for n in (1, 2)}
    orgs = {n: [e for e in ctx.f[n]["entidades"] if e["tipo"] == "organizacion"] for n in (1, 2)}
    move = {n: bool(MOVEMENT.search(" ".join(b["text"] for b in blocks(n, ("paragraph",))))) for n in (1, 2)}
    legal = {n: ctx.f[n]["lexico"]["lenguaje_juridico"]["n"] for n in (1, 2)}
    imgs = {n: blocks(n, ("figure",)) for n in (1, 2)}
    other = {n: [b for b in ctx.articles[n - 1]["blocks"] if b["type"] not in ("paragraph", "heading", "figure")] for n in (1, 2)}

    def st(cond1, cond2, what):
        if cond1 and cond2:
            return {"estado": "aplicable", "motivo": f"Ambas noticias contienen {what}."}
        if cond1 or cond2:
            who = 1 if cond1 else 2
            return {"estado": "aplicable", "motivo": f"Solo la noticia {who} contiene {what}; se analizará y se indicará la ausencia en la otra."}
        return {"estado": "no_aplicable", "motivo": f"Ninguna de las noticias contiene {what}."}

    pubs = [a["meta"].get("fecha_publicacion") for a in ctx.articles]
    upd = [a["meta"].get("fecha_actualizacion") for a in ctx.articles]
    out["3.4"] = ({"estado": "aplicable", "motivo": "Hay fechas de publicación o actualización con las que reconstruir la evolución."}
                  if any(pubs) or any(upd) else {"estado": "insuficiente", "motivo": "Ninguna noticia tiene fecha de publicación disponible."})
    out["4.1"] = st(places[1], places[2], "referencias a lugares")
    out["4.3"] = dict(out["4.1"])
    out["4.4"] = dict(out["4.1"])
    out["4.2"] = st(move[1], move[2], "verbos o expresiones de desplazamiento o traslado")
    for s in ("6.1", "6.2", "6.3", "6.4"):
        out[s] = st(nums[1], nums[2], "datos cuantitativos")
    out["8.3"] = st(persons[1], persons[2], "personas mencionadas")
    out["8.5"] = st(len(persons[1]) + len(orgs[1]) >= 2, len(persons[2]) + len(orgs[2]) >= 2, "al menos dos actores")
    out["8.6"] = st(any(STATE_ORG.search(e["nombre"]) for e in orgs[1]), any(STATE_ORG.search(e["nombre"]) for e in orgs[2]),
                    "instituciones del Estado o actores políticos")
    out["8.7"] = st(legal[1] > 0, legal[2] > 0, "vocabulario de responsabilidad, acusación o investigación")
    out["10.2"] = st(any(b.get("principal") for b in imgs[1]), any(b.get("principal") for b in imgs[2]), "imagen principal")
    out["10.3"] = st(len([b for b in imgs[1] if not b.get("principal")]) > 0, len([b for b in imgs[2] if not b.get("principal")]) > 0,
                     "imágenes secundarias")
    out["10.4"] = st(bool(other[1]), bool(other[2]), "vídeos, inserciones u otros recursos multimedia")
    return out


SCHEMA = s_obj({
    "tipos": s_arr(s_obj({"tipo": s_str("Tipo de acontecimiento (accidente, sanitario, delito, político, protesta, judicial, ambiental, económico, desastre, transporte u otro)"),
                          "peso": s_enum(["principal", "secundario"]), "justificacion": s_str()}, ["tipo", "peso", "justificacion"])),
    "tema_principal": s_str(),
    "sectores": s_arr(s_str("Sectores involucrados: salud, transporte, justicia, política, economía...")),
    "actores_principales": s_arr(s_str()),
    "naturaleza_datos": s_str("Qué tipo de datos ofrecen las noticias (cifras de víctimas, económicas, temporales...)"),
    "dimensiones_relevantes": s_arr(s_str()),
    "indicadores_especificos": s_arr(s_obj({
        "id": s_str("identificador corto sin espacios"), "nombre": s_str(), "descripcion": s_str(),
        "tipo": s_enum(["cuantitativo", "cualitativo"]), "unidad": s_str()}, ["id", "nombre", "tipo"]),
        "Indicadores propios de este acontecimiento (además de los generales). Máximo 10."),
    "secciones_condicionales": s_arr(s_obj({
        "seccion": s_enum(list(CONDITIONAL_SECTIONS.keys())), "aplicable": {"type": "boolean"}, "motivo": s_str()},
        ["seccion", "aplicable", "motivo"])),
    "evidencias": EVIDENCES,
}, ["tipos", "tema_principal", "indicadores_especificos", "secciones_condicionales"])

INSTRUCTIONS = """Identifica la naturaleza del acontecimiento para adaptar la metodología. Puede tener varias
categorías a la vez (p. ej., sanitario y político). Propón indicadores específicos que tengan sentido para este
caso (no fuerces indicadores de otros tipos de noticia) y decide, para cada sección condicional listada, si es
aplicable a estas noticias. No declares no aplicable una dimensión importante solo porque el texto no use su
vocabulario habitual."""


def run(project: dict) -> dict:
    ctx = Context(project)
    avail = availability(ctx)
    heur = heuristic_types(ctx)
    out = ctx.ask("perfil", INSTRUCTIONS + "\n\nSecciones condicionales: " +
                  "; ".join(f"{k} {v}" for k, v in CONDITIONAL_SECTIONS.items()), SCHEMA,
                  description="Registra el perfil del acontecimiento.")
    model = out if out and "__error__" not in out else None
    plan = {}
    llm_cond = {c["seccion"]: c for c in (model or {}).get("secciones_condicionales", []) if isinstance(c, dict)}
    for sid, label in CONDITIONAL_SECTIONS.items():
        prog = avail.get(sid, {"estado": "aplicable", "motivo": ""})
        m = llm_cond.get(sid)
        estado, motivo = prog["estado"], prog["motivo"]
        if m is not None:
            if m.get("aplicable") and estado != "aplicable":
                estado, motivo = "aplicable", f"{motivo} El modelo considera pertinente la dimensión: {m.get('motivo', '')}"
            elif not m.get("aplicable") and estado == "aplicable":
                # se conserva (regla 6.3): solo se omite si tampoco hay datos
                motivo = f"{motivo} (El modelo sugiere que es poco pertinente: {m.get('motivo', '')})"
        plan[sid] = {"seccion": label, "estado": estado, "motivo": motivo.strip()}
    if model and model.get("indicadores_especificos"):
        indicators = [dict(i, origen="modelo") for i in model["indicadores_especificos"][:12]]
    else:
        indicators = []
        for t in heur:
            for iid, name, unit, kind in INDICATOR_CATALOG.get(t["tipo"], []):
                if not any(i["id"] == iid for i in indicators):
                    indicators.append({"id": iid, "nombre": name, "unidad": unit, "tipo": kind, "origen": "catalogo",
                                       "descripcion": f"Indicador del catálogo para «{t['etiqueta']}»."})
    types = []
    if model:
        types = [{"tipo": t.get("tipo"), "etiqueta": str(t.get("tipo", "")).capitalize(), "peso": t.get("peso"),
                  "justificacion": t.get("justificacion"), "origen": "modelo"} for t in model.get("tipos", [])]
    else:
        types = [dict(t, origen="heuristico") for t in heur]
    return {"tipos": types, "heuristica": heur, "modelo": model,
            "error_modelo": out.get("__error__") if out and "__error__" in out else None,
            "disponibilidad": avail, "plan": plan, "indicadores": indicators, "uso": ctx.usage,
            "generado": datetime.now().isoformat(timespec="seconds")}
