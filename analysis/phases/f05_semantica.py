"""Fase 5. Análisis semántico, temático y textual."""
from __future__ import annotations

import re

from ...llm.prompts import CERTEZA, EVIDENCE, EVIDENCES, NIVEL, SYNTHESIS, s_arr, s_enum, s_obj, s_str
from ...nlp.features import content_tokens, distinctive_terms
from ...nlp.text import norm_key, stem
from ..base import Context, Phase, heuristic_synthesis, verif_merge
from ..helpers import D, L, S, ev_cell, synth_from

TREAT = s_enum(["amplio", "moderado", "superficial", "ausente"])
SCHEMA_A = s_obj({
    "temas": s_arr(s_obj({"id": s_str("T1..."), "nombre": s_str(), "nivel": s_enum(["central", "secundario", "subtema"]),
                          "padre": s_str("id del tema del que depende, o vacío"), "tratamiento_n1": TREAT, "tratamiento_n2": TREAT,
                          "evidencias": EVIDENCES}, ["id", "nombre", "nivel", "tratamiento_n1", "tratamiento_n2", "evidencias"])),
    "campos_semanticos": s_arr(s_obj({"nombre": s_str(), "descripcion": s_str(),
                                      "terminos": s_arr(s_str(), "Palabras LITERALES de los textos que pertenecen al campo (formas tal cual aparecen)")},
                                     ["nombre", "terminos"])),
    "asociaciones": s_arr(s_obj({"termino_a": s_str(), "termino_b": s_str(), "relacion": s_str(), "n": {"type": "integer", "enum": [1, 2]}, "p": s_str(), "cita": s_str()})),
    "lexico": s_arr(s_obj({"n": {"type": "integer", "enum": [1, 2]}, "p": s_str(), "cita": s_str("La expresión literal"),
                           "denotacion": s_str(), "connotacion": s_str(), "valoracion": s_enum(["positiva", "negativa", "neutral"]),
                           "recurso": s_enum(["intensificador", "atenuador", "eufemismo", "denominacion", "valorativo", "neutro"]),
                           "funcion": s_str()}, ["n", "p", "cita", "denotacion", "connotacion", "valoracion", "recurso", "funcion"])),
    "denominaciones_acontecimiento": s_obj({"n1": s_arr(EVIDENCE), "n2": s_arr(EVIDENCE)}, ["n1", "n2"]),
    "relaciones": s_arr(s_obj({"tipo": s_enum(["causa", "consecuencia", "oposicion", "contraste", "condicion", "asociacion", "explicacion"]),
                               "origen": s_str("Idea o hecho A"), "destino": s_str("Idea o hecho B"), "explicita": {"type": "boolean"},
                               "n": {"type": "integer", "enum": [1, 2]}, "p": s_str(), "cita": s_str()},
                              ["tipo", "origen", "destino", "explicita", "n", "p", "cita"])),
}, ["temas", "campos_semanticos", "lexico", "denominaciones_acontecimiento", "relaciones"])
INSTR_A = """Fase 5 (primera parte) — Temas, campos semánticos, selección léxica y relaciones semánticas.
1) Identifica el tema central, los temas secundarios y los subtemas de AMBAS noticias en una lista unificada,
   con su relación jerárquica (padre) y cuánto desarrolla cada noticia cada tema (amplio, moderado, superficial, ausente).
2) Agrupa el vocabulario en campos semánticos (p. ej. «violencia del suceso», «investigación», «dolor»): lista solo
   palabras que aparecen literalmente; el sistema contará sus apariciones.
3) Analiza las expresiones léxicamente significativas (denotación, connotación, valoración, intensificadores,
   atenuadores, eufemismos) y las distintas denominaciones del acontecimiento en cada noticia.
4) Identifica relaciones semánticas entre hechos e ideas (causas, consecuencias, oposiciones, contrastes,
   condiciones, asociaciones, explicaciones), indicando si son explícitas o implícitas."""
ARG = s_obj({"id": s_str("A1..."), "texto": s_str(), "tipo": s_enum(["tesis", "afirmacion", "argumento", "ejemplo", "justificacion", "contraargumento", "conclusion"]),
             "apoya_a": s_str("id del elemento al que sostiene, o vacío"), "p": s_str(), "cita": s_str(), "n": {"type": "integer", "enum": [1, 2]}},
            ["id", "texto", "tipo", "p", "cita", "n"])
FRAME = s_obj({"definicion_problema": s_str(), "dimensiones": s_arr(s_str()), "causas": s_arr(s_str()), "consecuencias": s_arr(s_str()),
               "soluciones": s_arr(s_str()), "interpretacion": s_str(), "evidencias": EVIDENCES},
              ["definicion_problema", "dimensiones", "causas", "consecuencias", "soluciones", "interpretacion"])
SCHEMA_B = s_obj({
    "cohesion_n1": s_obj({"continuidad": s_str(), "cambios_abruptos": s_arr(s_obj({"p": s_str(), "descripcion": s_str()})),
                          "contradicciones": s_arr(s_str()), "referencias": s_arr(s_str())}, ["continuidad"]),
    "cohesion_n2": s_obj({"continuidad": s_str(), "cambios_abruptos": s_arr(s_obj({"p": s_str(), "descripcion": s_str()})),
                          "contradicciones": s_arr(s_str()), "referencias": s_arr(s_str())}, ["continuidad"]),
    "presuposiciones": s_arr(s_obj({"n": {"type": "integer", "enum": [1, 2]}, "p": s_str(), "cita": s_str(), "presuposicion": s_str(),
                                    "inferencia": s_str(), "efecto": s_str(), "nivel": NIVEL, "certeza": CERTEZA},
                                   ["n", "p", "cita", "presuposicion", "efecto", "certeza"])),
    "argumentacion_n1": s_arr(ARG), "argumentacion_n2": s_arr(ARG),
    "encuadre_n1": FRAME, "encuadre_n2": FRAME,
    "sintesis": SYNTHESIS,
}, ["cohesion_n1", "cohesion_n2", "presuposiciones", "argumentacion_n1", "argumentacion_n2", "encuadre_n1", "encuadre_n2", "sintesis"])
INSTR_B = """Fase 5 (segunda parte) — Cohesión, implícitos, argumentación y encuadre.
1) Valora la cohesión y coherencia de cada noticia: continuidad temática, cambios abruptos de tema (indica el
   párrafo), contradicciones internas y referencias entre párrafos. Se te dan los recuentos de conectores y el
   solapamiento léxico entre párrafos calculados por el sistema.
2) Identifica presuposiciones e información implícita (lo que se da por conocido, ideas sugeridas) y su efecto
   interpretativo. Marca su nivel (casi siempre «inferencia») y certeza.
3) Reconstruye la estructura argumentativa de cada noticia: tesis o afirmación principal, argumentos de apoyo,
   ejemplos, justificaciones, contraargumentos y conclusión; indica a qué elemento apoya cada uno.
4) Describe el encuadre de cada noticia: definición del problema, dimensiones destacadas, causas, consecuencias,
   soluciones e interpretación general. Elabora la síntesis de toda la fase 5."""


def field_counts(article, terms: list[str]) -> tuple[int, list[str]]:
    keys = {stem(t.lower()) for t in terms if isinstance(t, str) and len(t) >= 3}
    found = []
    n = 0
    for b in article["blocks"]:
        if b["type"] not in ("paragraph", "heading"):
            continue
        for t in content_tokens(b["text"]):
            if stem(t) in keys:
                n += 1
                found.append(t)
    for k in ("titular", "subtitulo"):
        for t in content_tokens(article["meta"].get(k) or ""):
            if stem(t) in keys:
                n += 1
                found.append(t)
    return n, sorted(set(found))


class Fase5(Phase):
    number = 5
    title = "Análisis semántico, temático y textual"
    description = "Qué temas trata cada noticia, con qué vocabulario, qué relaciones establece y cómo encuadra el problema."
    sections = [("5.1", "Identificación y clasificación de temas", "¿Qué temas comparten y cuáles son exclusivos?"),
                ("5.2", "Campos semánticos y conceptos clave", "¿Qué vocabulario predomina y cuál distingue a cada medio?"),
                ("5.3", "Denotación, connotación y selección léxica", "¿Con qué palabras valora cada medio el acontecimiento?"),
                ("5.4", "Relaciones semánticas entre acontecimientos e ideas", "¿Qué causas, consecuencias y contrastes establece cada texto?"),
                ("5.5", "Cohesión y coherencia textual", "¿Cómo se encadenan los párrafos y las ideas?"),
                ("5.6", "Presuposiciones e información implícita", "¿Qué da por sabido o sugiere cada texto sin afirmarlo?"),
                ("5.7", "Construcción argumentativa", "¿Qué se afirma y en qué se apoya?"),
                ("5.8", "Encuadre temático y construcción del problema", "¿Cómo define cada medio el problema y sus causas?")]

    def analyze(self, ctx: Context):
        sec = self.make_sections(self.sections)
        f1, f2 = ctx.f[1], ctx.f[2]
        coh = {n: ctx.f[n]["cohesion"] for n in (1, 2)}
        con = {n: ctx.f[n]["conectores"] for n in (1, 2)}
        extra_b = ("Datos calculados por el sistema:\n" +
                   "\n".join(f"Noticia {n}: conectores por categoría {con[n]['por_categoria']}; solapamiento léxico medio entre "
                             f"párrafos consecutivos (Jaccard) {coh[n]['media_jaccard']}; transiciones sin vocabulario compartido ni conector: "
                             f"{[t['de'] + '→' + t['a'] for t in coh[n]['cambios_candidatos']]}" for n in (1, 2)))
        outA = ctx.ask("fase5a", INSTR_A, SCHEMA_A, description="Registra la primera parte de la fase 5.", max_tokens=10000)
        outB = ctx.ask("fase5b", INSTR_B, SCHEMA_B, extra=extra_b, description="Registra la segunda parte de la fase 5.", max_tokens=10000)
        okA = outA is not None and "__error__" not in outA
        okB = outB is not None and "__error__" not in outB

        # 5.1 temas
        s = sec["5.1"]
        if okA:
            temas = [t for t in L(outA.get("temas")) if isinstance(t, dict)]
            def present(t, n):
                return S(t.get(f"tratamiento_n{n}")) not in ("ausente", "")
            venn = {"n1": [], "n2": [], "shared": []}
            for t in temas:
                item = {"label": S(t.get("nombre")), "nivel": S(t.get("nivel")), "t1": S(t.get("tratamiento_n1")), "t2": S(t.get("tratamiento_n2"))}
                if present(t, 1) and present(t, 2):
                    venn["shared"].append(item)
                elif present(t, 1):
                    venn["n1"].append(item)
                elif present(t, 2):
                    venn["n2"].append(item)
            s.add("venn", "Temas compartidos y exclusivos", sets=venn, labels={"n1": ctx.label(1), "n2": ctx.label(2)}, origin="modelo",
                  description="Diagrama de Venn de los temas identificados; el tamaño del texto indica su nivel (central, secundario, subtema).",
                  interpretation=f"{len(venn['shared'])} temas compartidos, {len(venn['n1'])} exclusivos de la noticia 1 y {len(venn['n2'])} de la noticia 2.")
            names = {S(t.get("id")): S(t.get("nombre")) for t in temas}
            s.table("Matriz temática", [{"key": "tema", "label": "Tema"}, {"key": "nivel", "label": "Nivel"}, {"key": "padre", "label": "Depende de"},
                                        {"key": "t1", "label": "Tratamiento N1", "type": "tratamiento"}, {"key": "t2", "label": "Tratamiento N2", "type": "tratamiento"},
                                        {"key": "ev", "label": "Evidencias", "type": "evidencia"}],
                    [{"tema": S(t.get("nombre")), "nivel": S(t.get("nivel")), "padre": names.get(S(t.get("padre")), "—"),
                      "t1": S(t.get("tratamiento_n1")), "t2": S(t.get("tratamiento_n2")), "ev": ev_cell(t.get("evidencias"))} for t in temas],
                    origin="modelo")
        else:
            self.llm_failed(s, outA, "La identificación de temas")

        # 5.2 vocabulario
        s = sec["5.2"]
        s.add("wordcloud", "Nubes de palabras", clouds=[{"n": n, "name": ctx.label(n), "words": [{"text": w["forma"], "n": w["n"]} for w in ctx.f[n]["frecuencias"][:45]]} for n in (1, 2)],
              origin="programatico", description="Palabras de contenido (sin palabras vacías) agrupadas por raíz; el tamaño es proporcional a la frecuencia.")
        top = {n: ctx.f[n]["frecuencias"][:15] for n in (1, 2)}
        for n in (1, 2):
            s.add("bars", f"Términos más frecuentes · {ctx.label(n)}", categories=[w["forma"] for w in top[n]], orientation="h",
                  series=[{"key": f"n{n}", "name": ctx.label(n), "values": [w["n"] for w in top[n]]}], unit="apariciones", origin="programatico",
                  description="Recuento de apariciones de cada raíz en titular, subtítulo, cuerpo y pies de foto.")
        dt = distinctive_terms(f1["frecuencias"], f2["frecuencias"], 0, 0)
        rows = [{"label": r["forma"], "value": r["z"], "n1": r["n1"], "n2": r["n2"]} for r in dt["noticia1"]] + \
               [{"label": r["forma"], "value": r["z"], "n1": r["n1"], "n2": r["n2"]} for r in dt["noticia2"]]
        s.add("diverging", "Vocabulario distintivo de cada medio", rows=rows, labels={"n1": ctx.label(1), "n2": ctx.label(2)}, origin="programatico",
              description="Log-odds ponderado con prior de Dirichlet informativo (Monroe, Colaresi y Quinn, 2008). Valores positivos: términos "
                          "característicos de la noticia 1; negativos: de la noticia 2. |z| ≥ 1,96 equivale a una diferencia significativa al 95 %.",
              interpretation=("Ningún término alcanza |z| ≥ 1,96: con textos breves las diferencias de vocabulario son orientativas."
                              if not any(abs(r["value"]) >= 1.96 for r in rows) else "Los términos con |z| ≥ 1,96 distinguen con claridad a cada medio."))
        s.table("Vocabulario compartido", [{"key": "forma", "label": "Término"}, {"key": "n1", "label": "N1", "type": "num"}, {"key": "n2", "label": "N2", "type": "num"}],
                [{"forma": r["forma"], "n1": r["n1"], "n2": r["n2"]} for r in dt["compartidos"]], origin="programatico")
        if okA:
            fields = [c for c in L(outA.get("campos_semanticos")) if isinstance(c, dict)]
            frows, cats, v1, v2 = [], [], [], []
            for c in fields:
                n1, w1 = field_counts(ctx.a1, L(c.get("terminos")))
                n2, w2 = field_counts(ctx.a2, L(c.get("terminos")))
                per1 = round(1000 * n1 / max(1, f1["metricas"]["palabras"]), 1)
                per2 = round(1000 * n2 / max(1, f2["metricas"]["palabras"]), 1)
                frows.append({"campo": S(c.get("nombre")), "desc": S(c.get("descripcion")), "w1": ", ".join(w1) or "—", "w2": ", ".join(w2) or "—",
                              "n1": n1, "n2": n2, "p1": per1, "p2": per2})
                cats.append(S(c.get("nombre"))); v1.append(per1); v2.append(per2)
            if frows:
                s.add("bars", "Campos semánticos (por cada 1.000 palabras)", categories=cats, orientation="h",
                      series=[{"key": "n1", "name": ctx.label(1), "values": v1}, {"key": "n2", "name": ctx.label(2), "values": v2}],
                      unit="apariciones por 1.000 palabras", origin="mixto",
                      description="El modelo propone los campos y sus términos; el sistema cuenta las apariciones y normaliza por la extensión.")
                s.table("Mapa de campos semánticos", [{"key": "campo", "label": "Campo"}, {"key": "desc", "label": "Descripción"},
                                                       {"key": "w1", "label": "Términos en N1"}, {"key": "n1", "label": "N1", "type": "num"},
                                                       {"key": "w2", "label": "Términos en N2"}, {"key": "n2", "label": "N2", "type": "num"}],
                        frows, origin="mixto")
            asoc = [a for a in L(outA.get("asociaciones")) if isinstance(a, dict)]
            if asoc:
                s.table("Asociaciones entre términos", [{"key": "a", "label": "Término A"}, {"key": "b", "label": "Término B"},
                                                         {"key": "rel", "label": "Relación"}, {"key": "ev", "label": "Evidencia", "type": "evidencia"}],
                        [{"a": S(a.get("termino_a")), "b": S(a.get("termino_b")), "rel": S(a.get("relacion")), "ev": ev_cell([a])} for a in asoc], origin="modelo")
        else:
            self.no_llm(s, "La agrupación en campos semánticos")

        # 5.3 léxico
        s = sec["5.3"]
        lx = {n: ctx.f[n]["lexico"] for n in (1, 2)}
        s.add("bars", "Marcadores léxicos (por cada 1.000 palabras)", categories=["Intensificadores", "Atenuadores", "Vocabulario emotivo", "Vocabulario sensacionalista"],
              series=[{"key": f"n{n}", "name": ctx.label(n), "values": [lx[n]["intensificadores"]["por_1000"], lx[n]["atenuadores"]["por_1000"],
                                                                         lx[n]["emotivas"]["por_1000"], lx[n]["sensacionalistas"]["por_1000"]]} for n in (1, 2)],
              unit="por 1.000 palabras", origin="programatico",
              description="Recuento con léxicos cerrados del español (ver documentación); normalizado por la extensión del cuerpo.")
        if okA:
            lex = [x for x in L(outA.get("lexico")) if isinstance(x, dict)]
            s.table("Expresiones, significados y connotaciones", [
                {"key": "ev", "label": "Expresión", "type": "evidencia_texto"}, {"key": "den", "label": "Denotación"}, {"key": "con", "label": "Connotación"},
                {"key": "val", "label": "Valoración", "type": "valoracion"}, {"key": "rec", "label": "Recurso"}, {"key": "fun", "label": "Función"}],
                [{"ev": ev_cell([x]), "den": S(x.get("denotacion")), "con": S(x.get("connotacion")), "val": S(x.get("valoracion")),
                  "rec": S(x.get("recurso")), "fun": S(x.get("funcion"))} for x in lex], origin="modelo")
            den = D(outA.get("denominaciones_acontecimiento"))
            s.compare("Denominaciones del acontecimiento", [{"label": "Cómo se nombra el suceso",
                                                             "n1": {"evlist": L(den.get("n1"))}, "n2": {"evlist": L(den.get("n2"))}}], origin="modelo")
        else:
            self.no_llm(s, "El análisis de connotaciones y denominaciones")

        # 5.4 relaciones
        s = sec["5.4"]
        if okA:
            rels = [r for r in L(outA.get("relaciones")) if isinstance(r, dict)]
            nodes, edges, idx = [], [], {}
            for r in rels:
                n = r.get("n")
                for key in ("origen", "destino"):
                    lbl = S(r.get(key))[:70]
                    k = norm_key(lbl)
                    if k not in idx:
                        idx[k] = {"id": f"I{len(idx) + 1}", "label": lbl, "type": "idea", "ns": set()}
                    idx[k]["ns"].add(n)
                edges.append({"source": idx[norm_key(S(r.get('origen'))[:70])]["id"], "target": idx[norm_key(S(r.get('destino'))[:70])]["id"],
                              "label": S(r.get("tipo")) + ("" if r.get("explicita") else " (implícita)"), "origin": f"n{n}", "dashed": not r.get("explicita"),
                              "ev": [r]})
            for v in idx.values():
                nodes.append({"id": v["id"], "label": v["label"], "type": "idea", "origin": "shared" if v["ns"] == {1, 2} else f"n{min(v['ns'])}"})
            s.add("graph", "Mapa semántico de relaciones", nodes=nodes, edges=edges, directed=True, origin="modelo",
                  description="Nodos: hechos o ideas; flechas: relación semántica (causa, consecuencia, contraste...). Trazo discontinuo: relación implícita.")
            s.table("Relaciones semánticas", [{"key": "tipo", "label": "Relación"}, {"key": "a", "label": "A"}, {"key": "b", "label": "B"},
                                               {"key": "exp", "label": "Explícita"}, {"key": "ev", "label": "Evidencia", "type": "evidencia"}],
                    [{"tipo": S(r.get("tipo")), "a": S(r.get("origen")), "b": S(r.get("destino")), "exp": "Sí" if r.get("explicita") else "No (implícita)",
                      "ev": ev_cell([r])} for r in rels], origin="modelo")
        else:
            self.no_llm(s, "La identificación de relaciones semánticas")

        # 5.5 cohesión
        s = sec["5.5"]
        cats = list(con[1]["por_categoria"].keys())
        s.add("bars", "Conectores por función (por cada 100 palabras)", categories=[c.replace("_", " ") for c in cats],
              series=[{"key": f"n{n}", "name": ctx.label(n), "values": [con[n]["por_100_palabras"][c] for c in cats]} for n in (1, 2)],
              unit="por 100 palabras", origin="programatico",
              description="Conectores y marcadores discursivos de un léxico cerrado. «Como», «si», «cuando» o «tras» son polisémicos: el recuento es orientativo.")
        s.add("cohesion", "Continuidad léxica entre párrafos consecutivos",
              articles=[{"n": n, "name": ctx.label(n), "transitions": coh[n]["transiciones"], "mean": coh[n]["media_jaccard"]} for n in (1, 2)],
              origin="programatico",
              description="Índice de Jaccard entre las raíces de contenido de cada par de párrafos. Las transiciones marcadas no comparten "
                          "vocabulario ni empiezan con conector: son candidatas a cambio abrupto de tema (no lo prueban).")
        if okB:
            rows = []
            for n in (1, 2):
                c = D(outB.get(f"cohesion_n{n}"))
                rows.append({"n": n, "cont": S(c.get("continuidad")),
                             "cambios": "; ".join(f"{S(x.get('p'))}: {S(x.get('descripcion'))}" for x in L(c.get("cambios_abruptos")) if isinstance(x, dict)) or "—",
                             "contr": S(c.get("contradicciones")) or "—", "refs": S(c.get("referencias")) or "—"})
            s.table("Matriz de cohesión", [{"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "cont", "label": "Continuidad temática"},
                                           {"key": "cambios", "label": "Cambios abruptos"}, {"key": "contr", "label": "Contradicciones internas"},
                                           {"key": "refs", "label": "Referencias entre párrafos"}], rows, origin="modelo")
        else:
            self.no_llm(s, "La valoración cualitativa de la coherencia")

        # 5.6 presuposiciones
        s = sec["5.6"]
        if okB:
            pre = [p for p in L(outB.get("presuposiciones")) if isinstance(p, dict)]
            s.table("Matriz de presuposiciones e inferencias", [
                {"key": "ev", "label": "Fragmento", "type": "evidencia_texto"}, {"key": "pre", "label": "Presuposición"},
                {"key": "inf", "label": "Inferencia"}, {"key": "efe", "label": "Efecto interpretativo"},
                {"key": "nivel", "label": "Nivel", "type": "nivel"}, {"key": "cer", "label": "Certeza", "type": "certeza"}],
                [{"ev": ev_cell([p]), "pre": S(p.get("presuposicion")), "inf": S(p.get("inferencia")), "efe": S(p.get("efecto")),
                  "nivel": S(p.get("nivel"), "inferencia"), "cer": S(p.get("certeza"))} for p in pre], origin="modelo")
        else:
            self.llm_failed(s, outB, "La identificación de presuposiciones")
            s.status = "requiere_ia" if outB is None else "error"

        # 5.7 argumentación
        s = sec["5.7"]
        if okB:
            arts = []
            for n in (1, 2):
                nodes = [a for a in L(outB.get(f"argumentacion_n{n}")) if isinstance(a, dict)]
                arts.append({"n": n, "name": ctx.label(n), "nodes": [{"id": S(a.get("id")), "texto": S(a.get("texto")), "tipo": S(a.get("tipo")),
                                                                      "apoya_a": S(a.get("apoya_a")), "ev": [a]} for a in nodes]})
            s.add("argument", "Estructura argumentativa", articles=arts, origin="modelo",
                  description="Árbol de cada noticia: la afirmación principal arriba y, debajo, los elementos que la sostienen.")
            rows = []
            for t in ("tesis", "afirmacion", "argumento", "ejemplo", "justificacion", "contraargumento", "conclusion"):
                c1 = [x["texto"] for x in arts[0]["nodes"] if x["tipo"] == t]
                c2 = [x["texto"] for x in arts[1]["nodes"] if x["tipo"] == t]
                if c1 or c2:
                    rows.append({"label": t.capitalize(), "n1": "; ".join(c1) or "—", "n2": "; ".join(c2) or "—"})
            s.compare("Matriz comparativa de la argumentación", rows, origin="modelo")
        else:
            self.llm_failed(s, outB, "La reconstrucción argumentativa")
            s.status = "requiere_ia" if outB is None else "error"

        # 5.8 encuadre
        s = sec["5.8"]
        if okB:
            e1, e2 = D(outB.get("encuadre_n1")), D(outB.get("encuadre_n2"))
            rows = [{"label": lbl, "n1": S(e1.get(k)) or "—", "n2": S(e2.get(k)) or "—"} for k, lbl in (
                ("definicion_problema", "Definición del problema"), ("dimensiones", "Dimensiones destacadas"), ("causas", "Causas presentadas"),
                ("consecuencias", "Consecuencias destacadas"), ("soluciones", "Soluciones mencionadas"), ("interpretacion", "Interpretación general"))]
            s.compare("Matriz comparativa de encuadres", rows, origin="modelo",
                      evidence={"n1": L(e1.get("evidencias")), "n2": L(e2.get("evidencias"))})
        else:
            self.llm_failed(s, outB, "El análisis del encuadre")
            s.status = "requiere_ia" if outB is None else "error"

        synthesis, origin = synth_from(outB)
        if not synthesis:
            synthesis = heuristic_synthesis(
                [f"Términos característicos de N1: {', '.join(r['forma'] for r in dt['noticia1'][:5]) or '—'}.",
                 f"Términos característicos de N2: {', '.join(r['forma'] for r in dt['noticia2'][:5]) or '—'}."],
                [f"Vocabulario compartido: {', '.join(r['forma'] for r in dt['compartidos'][:6]) or '—'}."],
                ["Sin modelo de lenguaje la fase se limita a frecuencias, vocabulario distintivo, conectores y continuidad léxica."])
            origin = "programatico"
        return list(sec.values()), synthesis, origin, verif_merge(outA, outB)


PHASE = Fase5()
