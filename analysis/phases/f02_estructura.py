"""Fase 2. Análisis estructural y formal."""
from __future__ import annotations

from ...llm.prompts import EVIDENCES, SYNTHESIS, s_arr, s_obj, s_str
from ..base import Context, Phase, heuristic_synthesis, rel_diff, verif_merge
from ..helpers import D, L, S, ev_cell, para_index, para_range, synth_from, words_in

BLOCK = s_obj({"desde": s_str("Primer párrafo del bloque, p. ej. P1"), "hasta": s_str("Último párrafo del bloque"),
               "etiqueta": s_str("Nombre breve del bloque temático"), "funcion": s_str("Función informativa o narrativa"),
               "tema": s_str()}, ["desde", "hasta", "etiqueta", "funcion"])
PART = s_obj({"parrafos": s_str("Rango de párrafos, p. ej. P1-P2"), "funcion": s_str()}, ["parrafos", "funcion"])
NARR = s_obj({"introduccion": PART, "desarrollo": PART, "conclusion": PART,
              "conduccion": s_str("Cómo conduce el relato (cronológico, pirámide invertida, testimonial, por temas...)")},
             ["introduccion", "desarrollo", "conclusion", "conduccion"])
HIER = s_obj({"titular_destaca": s_str(), "subtitulo_destaca": s_str(), "entradilla_destaca": s_str(),
              "acontecimientos_priorizados": s_arr(s_str()), "actores_destacados": s_arr(s_str()),
              "contenido_principal_en": s_str("Párrafo donde se expone por primera vez el hecho principal"),
              "contenidos_secundarios": s_arr(s_str()), "evidencias": EVIDENCES},
             ["titular_destaca", "entradilla_destaca", "acontecimientos_priorizados", "actores_destacados", "contenido_principal_en"])
SCHEMA = s_obj({"bloques_n1": s_arr(BLOCK), "bloques_n2": s_arr(BLOCK), "narrativa_n1": NARR, "narrativa_n2": NARR,
                "jerarquia_n1": HIER, "jerarquia_n2": HIER,
                "diferencias_jerarquia": s_arr(s_obj({"aspecto": s_str(), "explicacion": s_str(), "evidencias": EVIDENCES})),
                "sintesis": SYNTHESIS},
               ["bloques_n1", "bloques_n2", "narrativa_n1", "narrativa_n2", "jerarquia_n1", "jerarquia_n2", "sintesis"])
INSTRUCTIONS = """Fase 2 — Análisis estructural y formal.
1) Divide el cuerpo de cada noticia en bloques temáticos CONSECUTIVOS que cubran todos los párrafos (P1 a Pn),
   sin solapamientos, indicando rango, etiqueta, función y tema.
2) Describe la organización narrativa (introducción, desarrollo, conclusión) y la forma de conducir el relato.
3) Describe la jerarquía informativa: qué destaca el titular, el subtítulo y la entradilla; qué acontecimientos
   y actores se priorizan; en qué párrafo aparece por primera vez el hecho principal.
4) No calcules extensiones: el sistema mide las palabras de cada bloque. Elabora la síntesis de la fase."""


def heuristic_blocks(a: dict) -> list[dict]:
    """Segmentación por subtítulos internos (si no hay modelo)."""
    blocks, cur, label = [], [], "Apertura"
    for b in a["blocks"]:
        if b["type"] == "heading":
            if cur:
                blocks.append({"desde": cur[0], "hasta": cur[-1], "etiqueta": label, "funcion": "Segmento delimitado por subtítulos"})
            cur, label = [], b["text"]
        elif b["type"] == "paragraph":
            cur.append(b["id"])
    if cur:
        blocks.append({"desde": cur[0], "hasta": cur[-1], "etiqueta": label, "funcion": "Segmento delimitado por subtítulos"})
    return blocks


def normalize_blocks(a: dict, blocks: list[dict]) -> list[dict]:
    ids = [b["id"] for b in a["blocks"] if b["type"] == "paragraph"]
    covered, out = set(), []
    for bl in sorted([b for b in blocks if isinstance(b, dict)], key=lambda b: para_index(b.get("desde", ""))):
        rng = [p for p in para_range(a, bl.get("desde", ""), bl.get("hasta", "")) if p not in covered]
        if not rng:
            continue
        covered.update(rng)
        out.append({**bl, "desde": rng[0], "hasta": rng[-1], "parrafos": rng, "palabras": words_in(a, rng)})
    missing = [p for p in ids if p not in covered]
    if missing:
        out.append({"desde": missing[0], "hasta": missing[-1], "parrafos": missing, "etiqueta": "Sin clasificar",
                    "funcion": "Párrafos no asignados por la segmentación", "palabras": words_in(a, missing)})
        out.sort(key=lambda b: para_index(b["desde"]))
    total = sum(b["palabras"] for b in out) or 1
    for b in out:
        b["pct"] = round(100 * b["palabras"] / total, 1)
    return out


class Fase2(Phase):
    number = 2
    title = "Análisis estructural y formal"
    description = "Cómo se organiza cada texto, cuánto ocupa y qué información se coloca en primer plano."
    sections = [("2.1", "Organización estructural", "¿Cómo se secuencian los bloques temáticos de cada noticia?"),
                ("2.2", "Extensión y métricas textuales", "¿Cuánto texto dedica cada medio y con qué densidad?"),
                ("2.3", "Organización narrativa", "¿Cómo abren, desarrollan y cierran el relato?"),
                ("2.4", "Jerarquía informativa", "¿Qué información y qué actores se colocan en primer plano?")]

    def analyze(self, ctx: Context):
        sec = self.make_sections(self.sections)
        out = ctx.ask("fase2", INSTRUCTIONS, SCHEMA, description="Registra la fase 2.")
        ok = out is not None and "__error__" not in out
        m = {1: ctx.f[1]["metricas"], 2: ctx.f[2]["metricas"]}

        # 2.2 métricas (programático)
        s22 = sec["2.2"]
        keys = [("palabras", "Palabras (cuerpo)"), ("parrafos", "Párrafos"), ("oraciones", "Oraciones"),
                ("subtitulos", "Subtítulos internos"), ("media_palabras_parrafo", "Media de palabras por párrafo"),
                ("media_palabras_oracion", "Media de palabras por oración"), ("mediana_palabras_oracion", "Mediana de palabras por oración"),
                ("parrafo_mas_largo", "Párrafo más largo (palabras)"), ("parrafo_mas_corto", "Párrafo más corto (palabras)"),
                ("oracion_mas_larga", "Oración más larga (palabras)"), ("oraciones_largas_30", "Oraciones de más de 30 palabras"),
                ("palabras_titular", "Palabras del titular"), ("palabras_subtitulo", "Palabras del subtítulo")]
        s22.compare("Métricas textuales", [{"label": lbl, "n1": m[1][k], "n2": m[2][k], "nota": rel_diff(m[1][k], m[2][k]) if k == "palabras" else ""}
                                           for k, lbl in keys],
                    description="Calculadas por código: palabras = secuencias alfanuméricas del cuerpo; oraciones = segmentación con abreviaturas del español.")
        s22.add("bars", "Extensión comparada", categories=["Palabras", "Oraciones", "Párrafos"],
                series=[{"key": "n1", "name": ctx.label(1), "values": [m[1]["palabras"], m[1]["oraciones"], m[1]["parrafos"]]},
                        {"key": "n2", "name": ctx.label(2), "values": [m[2]["palabras"], m[2]["oraciones"], m[2]["parrafos"]]}],
                unit="unidades", small_multiples=True,
                description="Cada medida tiene su propia escala para no mezclar magnitudes distintas.",
                interpretation=f"En palabras, {rel_diff(m[1]['palabras'], m[2]['palabras'])}.")
        s22.add("bars", "Densidad media", categories=["Palabras por párrafo", "Palabras por oración"],
                series=[{"key": "n1", "name": ctx.label(1), "values": [m[1]["media_palabras_parrafo"], m[1]["media_palabras_oracion"]]},
                        {"key": "n2", "name": ctx.label(2), "values": [m[2]["media_palabras_parrafo"], m[2]["media_palabras_oracion"]]}],
                unit="palabras", description="Promedios calculados sobre el cuerpo de cada noticia.")
        dist = {n: [x["palabras"] for x in m[n]["palabras_por_parrafo"]] for n in (1, 2)}
        s22.add("paragraph_profile", "Distribución de la extensión por párrafo",
                articles=[{"n": n, "name": ctx.label(n), "values": m[n]["palabras_por_parrafo"]} for n in (1, 2)],
                unit="palabras", description="Cada barra es un párrafo, en el orden en que aparece en la noticia.",
                interpretation="Permite ver si el texto concentra la extensión al inicio (pirámide invertida) o la reparte.")
        bins = [(0, 10, "≤10"), (11, 20, "11–20"), (21, 30, "21–30"), (31, 40, "31–40"), (41, 10_000, ">40")]
        hist = {n: [sum(1 for x in m[n]["longitudes_oracion"] if lo <= x <= hi) for lo, hi, _ in bins] for n in (1, 2)}
        s22.add("bars", "Longitud de las oraciones", categories=[b[2] for b in bins],
                series=[{"key": "n1", "name": ctx.label(1), "values": hist[1]}, {"key": "n2", "name": ctx.label(2), "values": hist[2]}],
                unit="oraciones", description="Número de oraciones por intervalo de longitud (en palabras).")

        # 2.1 bloques
        s21 = sec["2.1"]
        blocks = {}
        for n in (1, 2):
            raw = L(out.get(f"bloques_n{n}")) if ok else heuristic_blocks(ctx.articles[n - 1])
            blocks[n] = normalize_blocks(ctx.articles[n - 1], raw)
        s21.add("flow", "Secuencia de bloques temáticos",
                articles=[{"n": n, "name": ctx.label(n), "steps": [{"label": S(b.get("etiqueta")), "range": f"{b['desde']}–{b['hasta']}" if b['desde'] != b['hasta'] else b['desde'],
                                                                    "function": S(b.get("funcion")), "words": b["palabras"], "pct": b["pct"]} for b in blocks[n]]}
                          for n in (1, 2)],
                origin="mixto" if ok else "heuristico",
                description="Diagramas de flujo independientes: cada caja es un bloque temático consecutivo del cuerpo.",
                interpretation="" if ok else "Sin modelo de lenguaje, los bloques se delimitan solo por los subtítulos internos.")
        s21.table("Bloques temáticos",
                  [{"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "rango", "label": "Párrafos"},
                   {"key": "etiqueta", "label": "Bloque"}, {"key": "funcion", "label": "Función"},
                   {"key": "palabras", "label": "Palabras", "type": "num"}, {"key": "pct", "label": "% del cuerpo", "type": "num"}],
                  [{"n": n, "rango": f"{b['desde']}–{b['hasta']}", "etiqueta": S(b.get("etiqueta")), "funcion": S(b.get("funcion")),
                    "palabras": b["palabras"], "pct": b["pct"]} for n in (1, 2) for b in blocks[n]],
                  origin="mixto" if ok else "heuristico", description="Las palabras y porcentajes de cada bloque se calculan por código.")

        # 2.3 narrativa
        s23 = sec["2.3"]
        if ok:
            rows = []
            for part, lbl in (("introduccion", "Introducción"), ("desarrollo", "Desarrollo"), ("conclusion", "Conclusión")):
                p1, p2 = D(D(out.get("narrativa_n1")).get(part)), D(D(out.get("narrativa_n2")).get(part))
                rows.append({"label": lbl, "n1": f"{S(p1.get('parrafos'))} — {S(p1.get('funcion'))}",
                             "n2": f"{S(p2.get('parrafos'))} — {S(p2.get('funcion'))}"})
            rows.append({"label": "Conducción del relato", "n1": S(D(out.get("narrativa_n1")).get("conduccion")),
                         "n2": S(D(out.get("narrativa_n2")).get("conduccion"))})
            s23.compare("Introducción, desarrollo y conclusión", rows, origin="modelo")
        else:
            rows = []
            for n in (1, 2):
                ids = [b["id"] for b in ctx.articles[n - 1]["blocks"] if b["type"] == "paragraph"]
                rows.append(ids)
            s23.compare("Partes del relato (convención estructural)", [
                {"label": "Introducción", "n1": rows[0][0] if rows[0] else "—", "n2": rows[1][0] if rows[1] else "—"},
                {"label": "Desarrollo", "n1": f"{rows[0][1]}–{rows[0][-2]}" if len(rows[0]) > 2 else "—", "n2": f"{rows[1][1]}–{rows[1][-2]}" if len(rows[1]) > 2 else "—"},
                {"label": "Conclusión", "n1": rows[0][-1] if rows[0] else "—", "n2": rows[1][-1] if rows[1] else "—"}],
                origin="heuristico", description="Sin modelo, solo se indica la posición convencional (primer párrafo, intermedios, último).")
            self.no_llm(s23, "La función de cada parte del relato")

        # 2.4 jerarquía
        s24 = sec["2.4"]
        s24.add("blocks", "Diagrama de bloques: espacio dedicado a cada tema",
                articles=[{"n": n, "name": ctx.label(n), "segments": [{"label": S(b.get("etiqueta")), "words": b["palabras"], "pct": b["pct"],
                                                                        "range": f"{b['desde']}–{b['hasta']}"} for b in blocks[n]]} for n in (1, 2)],
                origin="mixto" if ok else "heuristico", unit="% de palabras del cuerpo",
                description="Proporción del cuerpo de cada noticia ocupada por cada bloque (de arriba abajo, en orden de aparición).")
        if ok:
            rows = []
            for key, lbl in (("titular_destaca", "Destaca el titular"), ("subtitulo_destaca", "Destaca el subtítulo"),
                             ("entradilla_destaca", "Destaca la entradilla"), ("acontecimientos_priorizados", "Acontecimientos priorizados"),
                             ("actores_destacados", "Actores con mayor atención"), ("contenido_principal_en", "Hecho principal expuesto en"),
                             ("contenidos_secundarios", "Contenidos secundarios")):
                rows.append({"label": lbl, "n1": S(D(out.get("jerarquia_n1")).get(key)), "n2": S(D(out.get("jerarquia_n2")).get(key))})
            s24.compare("Matriz de jerarquía informativa", rows, origin="modelo",
                        evidence={"n1": L(D(out.get("jerarquia_n1")).get("evidencias")), "n2": L(D(out.get("jerarquia_n2")).get("evidencias"))})
            dj = L(out.get("diferencias_jerarquia"))
            if dj:
                s24.table("Diferencias de jerarquía", [{"key": "aspecto", "label": "Aspecto"}, {"key": "exp", "label": "Explicación"},
                                                        {"key": "ev", "label": "Evidencias", "type": "evidencia"}],
                          [{"aspecto": S(d.get("aspecto")), "exp": S(d.get("explicacion")), "ev": ev_cell(d.get("evidencias"))} for d in dj if isinstance(d, dict)],
                          origin="modelo")
        else:
            self.llm_failed(s24, out, "La matriz de jerarquía informativa")

        synthesis, origin = synth_from(out)
        if not synthesis:
            synthesis = heuristic_synthesis(
                [f"Extensión: {rel_diff(m[1]['palabras'], m[2]['palabras'])} (en palabras).",
                 f"Media de palabras por oración: {m[1]['media_palabras_oracion']} (N1) frente a {m[2]['media_palabras_oracion']} (N2)."],
                [], ["La segmentación temática y la jerarquía requieren modelo de lenguaje."])
            origin = "programatico"
        return list(sec.values()), synthesis, origin, verif_merge(out)


PHASE = Fase2()
