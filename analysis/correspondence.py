"""Comprobación de correspondencia entre las dos noticias (obligatoria antes del análisis).

Se combinan:
* indicadores programáticos auxiliares (coincidencia de entidades, lugares, cifras,
  fechas y similitud léxica), que nunca deciden por sí solos;
* la clasificación del modelo de lenguaje (A: mismo acontecimiento, B: relacionados,
  C: diferentes) justificada con evidencias verificadas;
* si no hay modelo, una clasificación heurística prudente.

Del conjunto sale un **porcentaje de correspondencia** (0–100) que gobierna el flujo:

* ``porcentaje_codigo``: puntuación ponderada de los indicadores programáticos (personas e instituciones,
  lugares, vocabulario, cifras y fechas compartidas; se atenúa si las publicaciones están muy separadas en el tiempo);
* ``porcentaje_modelo``: si hay modelo, este clasifica cuánto coinciden seis elementos del acontecimiento
  (acción, actores, lugar, fecha, circunstancias y consecuencias) y el código calcula el porcentaje con pesos fijos;
* ``porcentaje``: media de ambos (o solo el de código si no hay modelo). Si el modelo concluye que son
  acontecimientos diferentes, el porcentaje no puede superar el umbral.

Regla funcional: por debajo de ``UMBRAL`` (40 %) la persona usuaria decide si continúa o revisa las noticias;
a partir de ese valor el análisis continúa automáticamente.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime

from ..llm import client as llm
from ..llm.evidence import Verifier
from ..llm.prompts import (CERTEZA, EVIDENCES, SYSTEM_RULES, articles_text, s_arr, s_enum, s_obj, s_str)
from ..nlp.features import content_tokens
from ..nlp.text import norm_key, stem

UMBRAL = 40  # % mínimo de correspondencia para continuar sin preguntar
# pesos de los elementos del acontecimiento que clasifica el modelo (suman 1)
ELEMENT_WEIGHTS = {"accion": 0.30, "actores": 0.20, "lugar": 0.15, "fecha": 0.15, "circunstancias": 0.12, "consecuencias": 0.08}
MATCH_VALUE = {"total": 1.0, "parcial": 0.5, "ninguna": 0.0}

RELATION_LABELS = {"mismo": "A · Mismo acontecimiento", "relacionados": "B · Acontecimientos relacionados",
                   "diferentes": "C · Acontecimientos diferentes"}


def _tokset(name: str) -> set[str]:
    return {t for t in re.findall(r"\w+", norm_key(name)) if len(t) > 2 and t not in {"del", "las", "los", "para"}}


def _match_names(a: list[str], b: list[str]) -> list[tuple[str, str]]:
    pairs, used = [], set()
    for x in a:
        tx = _tokset(x)
        if not tx:
            continue
        for y in b:
            if y in used:
                continue
            ty = _tokset(y)
            if ty and len(tx & ty) / min(len(tx), len(ty)) >= 0.6:
                pairs.append((x, y))
                used.add(y)
                break
    return pairs


def _cosine(c1: Counter, c2: Counter) -> float:
    inter = set(c1) & set(c2)
    num = sum(c1[w] * c2[w] for w in inter)
    den = math.sqrt(sum(v * v for v in c1.values())) * math.sqrt(sum(v * v for v in c2.values()))
    return num / den if den else 0.0


def indicators(project: dict) -> dict:
    a1, a2 = project["articles"]
    f1, f2 = project["features"]["1"], project["features"]["2"]
    ent = {}
    for kind in ("persona", "organizacion", "lugar"):
        e1 = [e["nombre"] for e in f1["entidades"] if e["tipo"] == kind]
        e2 = [e["nombre"] for e in f2["entidades"] if e["tipo"] == kind]
        pairs = _match_names(e1, e2)
        union = len(e1) + len(e2) - len(pairs)
        ent[kind] = {"n1": e1, "n2": e2, "coincidencias": [{"n1": x, "n2": y} for x, y in pairs],
                     "jaccard": round(len(pairs) / union, 3) if union else 0}
    def nums(f):
        return {(round(d["valor"], 2), d["tipo"]) for d in f["cifras"] if d["valor"] is not None and d["tipo"] in ("cantidad", "edad", "moneda", "porcentaje", "ubicacion")}
    shared_nums = sorted(nums(f1) & nums(f2))
    d1 = {t["normalizada"] for t in f1["temporales"] if t.get("normalizada") and len(str(t["normalizada"])) == 10}
    d2 = {t["normalizada"] for t in f2["temporales"] if t.get("normalizada") and len(str(t["normalizada"])) == 10}
    pub_diff = None
    p1, p2 = (a1["meta"].get("fecha_publicacion"), a2["meta"].get("fecha_publicacion"))
    if p1 and p2:
        try:
            pub_diff = round(abs((datetime.fromisoformat(p1).replace(tzinfo=None) - datetime.fromisoformat(p2).replace(tzinfo=None)).total_seconds()) / 86400, 2)
        except ValueError:
            pass
    def bag(a):
        txt = " ".join(b["text"] for b in a["blocks"] if b["type"] == "paragraph") + " " + (a["meta"].get("titular") or "")
        return Counter(stem(t) for t in content_tokens(txt))
    cos = _cosine(bag(a1), bag(a2))
    tcos = _cosine(Counter(stem(t) for t in content_tokens(a1["meta"].get("titular") or "")),
                   Counter(stem(t) for t in content_tokens(a2["meta"].get("titular") or "")))
    return {"entidades": ent, "cifras_compartidas": [{"valor": v, "tipo": t} for v, t in shared_nums],
            "fechas_compartidas": sorted(d1 & d2), "fechas_n1": sorted(d1), "fechas_n2": sorted(d2),
            "dias_entre_publicaciones": pub_diff, "similitud_lexica": round(cos, 3), "similitud_titulares": round(tcos, 3),
            "nota": "Indicadores auxiliares calculados por código. No determinan por sí solos la correspondencia: "
                    "compartir palabras, personas o instituciones no implica que se trate del mismo suceso."}


def heuristic(ind: dict) -> dict:
    e = ind["entidades"]
    score = (0.30 * min(1, e["persona"]["jaccard"] * 2 + e["organizacion"]["jaccard"] * 2)
             + 0.25 * min(1, e["lugar"]["jaccard"] * 2)
             + 0.30 * min(1, ind["similitud_lexica"] * 2.5)
             + 0.10 * min(1, len(ind["cifras_compartidas"]) / 3)
             + 0.05 * (1 if ind["fechas_compartidas"] else 0))
    d = ind.get("dias_entre_publicaciones")
    if d is not None and d > 30:
        score *= 0.7
    if score >= 0.45 and (d is None or d <= 3):
        rel = "mismo"
    elif score >= 0.45:
        rel = "relacionados"  # mucha coincidencia pero publicaciones distantes: probable acontecimiento de seguimiento
    elif score >= 0.22:
        rel = "relacionados"
    else:
        rel = "diferentes"
    return {"relacion": rel, "puntuacion": round(score, 3), "confianza": "baja",
            "explicacion": ("Clasificación heurística basada en coincidencias de entidades, lugares, cifras, fechas y "
                            "vocabulario. Es orientativa: sin modelo de lenguaje no se comparan acciones, circunstancias "
                            "ni consecuencias, por lo que se requiere tu confirmación.")}


SCHEMA = s_obj({
    "evento_n1": s_obj({"resumen": s_str("Acontecimiento principal en una o dos frases"), "accion_principal": s_str(),
                        "actores": s_arr(s_str()), "lugares": s_arr(s_str()), "fechas": s_arr(s_str()),
                        "circunstancias": s_arr(s_str()), "consecuencias": s_arr(s_str()), "evidencias": EVIDENCES},
                       ["resumen", "accion_principal", "actores", "lugares", "fechas", "evidencias"]),
    "evento_n2": s_obj({"resumen": s_str(), "accion_principal": s_str(), "actores": s_arr(s_str()),
                        "lugares": s_arr(s_str()), "fechas": s_arr(s_str()), "circunstancias": s_arr(s_str()),
                        "consecuencias": s_arr(s_str()), "evidencias": EVIDENCES},
                       ["resumen", "accion_principal", "actores", "lugares", "fechas", "evidencias"]),
    "actores_coincidentes": s_arr(s_str()),
    "lugares_coincidentes": s_arr(s_str()),
    "fechas_relacionadas": s_arr(s_obj({"n1": s_str(), "n2": s_str(), "relacion": s_str()})),
    "coincidencias": s_arr(s_obj({"aspecto": s_str(), "descripcion": s_str(), "evidencias": EVIDENCES})),
    "diferencias": s_arr(s_obj({"aspecto": s_str(), "descripcion": s_str(), "evidencias": EVIDENCES})),
    "relacion": s_enum(["mismo", "relacionados", "diferentes"]),
    "tipo_vinculo": s_str("Si son relacionados: mismo caso, proceso, investigación, conflicto o contexto"),
    "explicacion_relacion": s_str(),
    "confianza": CERTEZA,
    "incertidumbres": s_arr(s_str()),
    "elementos": s_arr(s_obj({
        "elemento": s_enum(list(ELEMENT_WEIGHTS), "Elemento del acontecimiento que se compara"),
        "coincidencia": s_enum(list(MATCH_VALUE), "total: el mismo; parcial: parecido o solo uno de varios; ninguna: distinto o ausente"),
        "nota": s_str("Justificación en una frase"),
    }, ["elemento", "coincidencia"]), "Un registro por cada uno de los seis elementos: accion, actores, lugar, fecha, circunstancias y consecuencias"),
}, ["evento_n1", "evento_n2", "coincidencias", "diferencias", "relacion", "explicacion_relacion", "confianza"])

INSTRUCTIONS = """Determina si las dos noticias describen el MISMO acontecimiento, acontecimientos RELACIONADOS
(sucesos distintos de un mismo caso, proceso, investigación, conflicto o contexto) o acontecimientos DIFERENTES.
Compara acontecimiento principal, personas, instituciones, lugar, fecha, acciones, circunstancias y consecuencias.
Compartir protagonistas, instituciones o vocabulario NO basta: dos noticias pueden hablar de la misma persona y
referirse a sucesos distintos. Diferencias de cifras o de enfoque entre dos coberturas del mismo suceso no lo
convierten en otro acontecimiento. Justifica con evidencias literales. Si la relación es ambigua, explica la
incertidumbre y usa confianza «media» o «baja».
Rellena también «elementos»: para cada uno de los seis elementos (accion, actores, lugar, fecha, circunstancias,
consecuencias) indica si coinciden totalmente, parcialmente o en nada. No calcules porcentajes: los calcula el sistema."""



def model_percentage(m: dict) -> tuple[int | None, list[dict]]:
    """Porcentaje calculado por código a partir de la clasificación por elementos que hace el modelo."""
    rows, got = [], {}
    for e in (m.get("elementos") or []):
        if isinstance(e, dict) and e.get("elemento") in ELEMENT_WEIGHTS and e.get("coincidencia") in MATCH_VALUE:
            got.setdefault(e["elemento"], e)
    if len(got) < 3:
        return None, []
    total_w = sum(ELEMENT_WEIGHTS[k] for k in got)
    score = sum(ELEMENT_WEIGHTS[k] * MATCH_VALUE[e["coincidencia"]] for k, e in got.items()) / total_w
    for k in ELEMENT_WEIGHTS:
        if k in got:
            rows.append({"elemento": k, "coincidencia": got[k]["coincidencia"], "peso": ELEMENT_WEIGHTS[k], "nota": got[k].get("nota", "")})
    return round(100 * score), rows


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def facts(ind: dict) -> dict:
    """Coincidencias concretas encontradas por código (para mostrar junto al porcentaje)."""
    e = ind["entidades"]
    return {"personas": len(e["persona"]["coincidencias"]), "instituciones": len(e["organizacion"]["coincidencias"]),
            "lugares": len(e["lugar"]["coincidencias"]), "cifras": len(ind["cifras_compartidas"]), "fechas": len(ind["fechas_compartidas"]),
            "vocabulario": round(100 * ind["similitud_lexica"])}


def plain_summary(ind: dict, pct: int) -> str:
    f = facts(ind)
    parts = []
    for key, one, many in (("personas", "persona", "personas"), ("instituciones", "institución", "instituciones"),
                           ("lugares", "lugar", "lugares"), ("cifras", "cifra", "cifras"), ("fechas", "fecha", "fechas")):
        if f[key]:
            parts.append(_plural(f[key], one, many))
    shared = ("Las noticias comparten " + ", ".join(parts[:-1]) + (" y " if len(parts) > 1 else "") + parts[-1] + ".") if parts else \
        "Las noticias no comparten personas, instituciones, lugares, cifras ni fechas."
    d = ind.get("dias_entre_publicaciones")
    gap = f" Se publicaron con {d:g} días de diferencia." if d is not None and d >= 1 else ""
    return f"{shared} La similitud de vocabulario es del {f['vocabulario']} %.{gap}"


def _first_sentences(text: str, n: int = 2, limit: int = 320) -> str:
    sents = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    out = " ".join(sents[:n]).strip()
    return out if len(out) <= limit else out[:limit].rsplit(" ", 1)[0] + "…"


def run(project: dict) -> dict:
    ind = indicators(project)
    heur = heuristic(ind)
    res = {"indicadores": ind, "heuristica": heur, "modelo": None, "error_modelo": None, "uso": None,
           "generado": datetime.now().isoformat(timespec="seconds")}
    if llm.available():
        extra = ("Indicadores auxiliares calculados por el sistema (solo orientativos): "
                 f"similitud léxica {ind['similitud_lexica']}, cifras compartidas {len(ind['cifras_compartidas'])}, "
                 f"días entre publicaciones {ind['dias_entre_publicaciones']}.")
        user = articles_text(project["articles"]) + "\n\n" + extra + "\n\nTAREA\n" + INSTRUCTIONS
        try:
            out, usage = llm.call("correspondencia", SYSTEM_RULES, user, SCHEMA,
                                  description="Registra la comparación de acontecimientos.")
            v = Verifier(project["articles"])
            v.walk(out)
            out["__verificacion__"] = v.stats
            res["modelo"] = out
            res["uso"] = usage
        except llm.LLMError as e:
            res["error_modelo"] = str(e)
    codigo = round(100 * heur["puntuacion"])
    pct_modelo, elementos = (None, [])
    if res["modelo"]:
        m = res["modelo"]
        pct_modelo, elementos = model_percentage(m)
        rel = m.get("relacion", "relacionados")
        conf = m.get("confianza", "media")
        final = {"relacion": rel, "confianza": conf, "fuente": "modelo"}
    else:
        final = {"relacion": heur["relacion"], "confianza": "baja", "fuente": "heuristica"}
    pct = round((codigo + pct_modelo) / 2) if pct_modelo is not None else codigo
    limitado = bool(res["modelo"] and final["relacion"] == "diferentes" and pct >= UMBRAL)
    if limitado:  # el modelo no reconoce el mismo acontecimiento: el porcentaje no puede dar paso automático
        pct = UMBRAL - 1
    auto = pct >= UMBRAL
    final.update({
        "porcentaje": pct, "porcentaje_codigo": codigo, "porcentaje_modelo": pct_modelo, "umbral": UMBRAL,
        "limitado_por_modelo": limitado, "elementos": elementos, "coincidencias": facts(ind),
        "resumen": _first_sentences(res["modelo"].get("explicacion_relacion")) if res["modelo"] else plain_summary(ind, pct),
        "requiere_confirmacion": not auto, "bloquea": False,
        "confirmada": auto, "decision": "automatica" if auto else None,
        "confirmada_en": datetime.now().isoformat(timespec="seconds") if auto else None,
    })
    final["etiqueta"] = RELATION_LABELS[final["relacion"]]
    res["final"] = final
    return res
