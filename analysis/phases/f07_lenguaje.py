"""Fase 7. Análisis lingüístico, emocional y retórico."""
from __future__ import annotations

from collections import Counter

from ...llm.prompts import EVIDENCES, SYNTHESIS, s_arr, s_enum, s_num, s_obj, s_str
from ...nlp import engine
from ...nlp.features import count_mentions
from ..base import Context, Phase, heuristic_synthesis, verif_merge
from ..helpers import D, L, S, ev_cell, synth_from

TONES = [("informativo", "Informativo"), ("critico", "Crítico"), ("alarmista", "Alarmista"), ("empatico", "Empático"), ("acusatorio", "Acusatorio")]
SCORE = s_obj({"valor": s_num("0 = ausente, 4 = dominante", 0, 4), "justificacion": s_str(), "evidencias": EVIDENCES}, ["valor", "justificacion"])
TONE = s_obj({k: SCORE for k, _ in TONES}, [k for k, _ in TONES])
SCHEMA = s_obj({
    "tono_n1": TONE, "tono_n2": TONE,
    "emotividad_n1": SCORE, "emotividad_n2": SCORE, "sensacionalismo_n1": SCORE, "sensacionalismo_n2": SCORE,
    "sentimiento_n1": s_arr(s_obj({"p": s_str(), "valor": s_enum(["positivo", "negativo", "neutro"])}, ["p", "valor"]), "Un elemento por cada párrafo P1..Pn"),
    "sentimiento_n2": s_arr(s_obj({"p": s_str(), "valor": s_enum(["positivo", "negativo", "neutro"])}, ["p", "valor"])),
    "expresiones": s_arr(s_obj({"n": {"type": "integer", "enum": [1, 2]}, "p": s_str(), "cita": s_str(),
                                "tipo": s_enum(["impactante", "exageracion", "emotiva", "sensacionalista"]), "efecto": s_str()},
                               ["n", "p", "cita", "tipo", "efecto"])),
    "modalidad": s_arr(s_obj({"n": {"type": "integer", "enum": [1, 2]}, "p": s_str(), "cita": s_str(),
                              "tipo": s_enum(["categorica", "certeza", "probabilidad", "posibilidad", "incertidumbre", "hipotesis", "atribucion"]),
                              "comentario": s_str()}, ["n", "p", "cita", "tipo"])),
    "recursos": s_arr(s_obj({"n": {"type": "integer", "enum": [1, 2]}, "p": s_str(), "cita": s_str(),
                             "recurso": s_enum(["metafora", "hiperbole", "eufemismo", "ironia", "repeticion", "analogia", "contraste",
                                                "pregunta_retorica", "personificacion", "otro"]), "funcion": s_str()},
                            ["n", "p", "cita", "recurso", "funcion"])),
    "adjetivos_valorativos": s_arr(s_obj({"n": {"type": "integer", "enum": [1, 2]}, "adjetivo": s_str("forma literal"),
                                          "valoracion": s_enum(["positiva", "negativa"]), "p": s_str(), "cita": s_str()},
                                         ["n", "adjetivo", "valoracion"])),
    "formalidad_n1": s_obj({"tecnicismos": s_arr(s_str()), "coloquialismos": s_arr(s_str()), "formulas_institucionales": s_arr(s_str()),
                            "lenguaje_juridico": s_arr(s_str()), "claridad": s_str(), "registro": s_enum(["formal", "neutro", "informal", "mixto"])},
                           ["claridad", "registro"]),
    "formalidad_n2": s_obj({"tecnicismos": s_arr(s_str()), "coloquialismos": s_arr(s_str()), "formulas_institucionales": s_arr(s_str()),
                            "lenguaje_juridico": s_arr(s_str()), "claridad": s_str(), "registro": s_enum(["formal", "neutro", "informal", "mixto"])},
                           ["claridad", "registro"]),
    "sintesis": SYNTHESIS,
}, ["tono_n1", "tono_n2", "emotividad_n1", "emotividad_n2", "sensacionalismo_n1", "sensacionalismo_n2", "sentimiento_n1",
    "sentimiento_n2", "expresiones", "recursos", "adjetivos_valorativos", "formalidad_n1", "formalidad_n2", "sintesis"])
INSTRUCTIONS = """Fase 7 — Análisis lingüístico, emocional y retórico.
1) Puntúa de 0 a 4 cinco dimensiones de tono (informativo, crítico, alarmista, empático, acusatorio) para cada
   noticia, con justificación y evidencias. Las dimensiones no son excluyentes.
2) Valora por separado emotividad y sensacionalismo (0–4) y clasifica el sentimiento de CADA párrafo (positivo,
   negativo, neutro). El sistema contará las proporciones. Identifica expresiones impactantes y exageraciones.
3) Ilustra la modalidad (afirmaciones categóricas, certeza, probabilidad, posibilidad, incertidumbre, hipótesis,
   atribución) con ejemplos; el sistema ya contó los marcadores léxicos.
4) Identifica recursos retóricos (metáforas, hipérboles, eufemismos, ironía, repeticiones, analogías, contrastes,
   preguntas retóricas, personificaciones) y su función.
5) Lista los adjetivos valorativos tal como aparecen (el sistema contará sus apariciones).
6) Describe formalidad, claridad y registro: tecnicismos, coloquialismos, fórmulas institucionales, lenguaje
   jurídico o burocrático. Elabora la síntesis. Puntuar el tono de un texto no implica atribuir intenciones al medio."""


class Fase7(Phase):
    number = 7
    title = "Análisis lingüístico, emocional y retórico"
    description = "Con qué tono, grado de certeza, recursos y registro presenta cada medio la información."
    sections = [("7.1", "Tono", "¿Qué tonos predominan en cada noticia?"),
                ("7.2", "Emotividad, sentimiento y sensacionalismo", "¿Cuánta carga emocional y sensacionalista tiene cada texto?"),
                ("7.3", "Modalidad, certeza e incertidumbre", "¿Con qué grado de seguridad se afirman los hechos?"),
                ("7.4", "Recursos retóricos", "¿Qué recursos retóricos usa cada medio y para qué?"),
                ("7.5", "Características gramaticales y léxicas", "¿Qué rasgos gramaticales caracterizan cada redacción?"),
                ("7.6", "Formalidad, claridad y complejidad", "¿Qué tan formal, técnico y legible es cada texto?")]

    def analyze(self, ctx: Context):
        sec = self.make_sections(self.sections)
        lx = {n: ctx.f[n]["lexico"] for n in (1, 2)}
        mod = {n: ctx.f[n]["modalidad"] for n in (1, 2)}
        extra = "Recuentos programáticos de marcadores: " + "; ".join(
            f"Noticia {n}: emotivos {lx[n]['emotivas']['n']}, sensacionalistas {lx[n]['sensacionalistas']['n']}, modalidad {mod[n]['por_categoria']}"
            for n in (1, 2))
        out = ctx.ask("fase7", INSTRUCTIONS, SCHEMA, extra=extra, description="Registra la fase 7.", max_tokens=10000)
        ok = out is not None and "__error__" not in out

        # 7.1 tono
        s = sec["7.1"]
        if ok:
            vals = {n: [float(D(D(out.get(f"tono_n{n}")).get(k)).get("valor") or 0) for k, _ in TONES] for n in (1, 2)}
            s.add("radar", "Perfil de tono", axes=[l for _, l in TONES], max=4, split=True,
                  series=[{"key": f"n{n}", "name": ctx.label(n), "values": vals[n]} for n in (1, 2)], origin="modelo",
                  description="Dos gráficos de radar (escala 0–4). Puntuación del modelo con justificación y evidencias en la tabla.")
            rows = []
            for k, lbl in TONES:
                for n in (1, 2):
                    x = D(D(out.get(f"tono_n{n}")).get(k))
                    rows.append({"dim": lbl, "n": n, "valor": x.get("valor"), "just": S(x.get("justificacion")), "ev": ev_cell(x.get("evidencias"))})
            s.table("Justificación del tono", [{"key": "dim", "label": "Dimensión"}, {"key": "n", "label": "Noticia", "type": "noticia"},
                                               {"key": "valor", "label": "0–4", "type": "num"}, {"key": "just", "label": "Justificación"},
                                               {"key": "ev", "label": "Evidencias", "type": "evidencia"}], rows, origin="modelo")
        else:
            self.llm_failed(s, out, "La valoración del tono")
            s.status = "requiere_ia" if out is None else "error"

        # 7.2 emotividad
        s = sec["7.2"]
        s.add("bars", "Marcadores emotivos y sensacionalistas (por cada 1.000 palabras)",
              categories=["Vocabulario emotivo", "Vocabulario sensacionalista", "Exclamaciones", "Preguntas"],
              series=[{"key": f"n{n}", "name": ctx.label(n), "values": [lx[n]["emotivas"]["por_1000"], lx[n]["sensacionalistas"]["por_1000"],
                                                                         round(1000 * lx[n]["exclamaciones"] / max(1, lx[n]["palabras"]), 1),
                                                                         round(1000 * len(lx[n]["preguntas"]) / max(1, lx[n]["palabras"]), 1)]} for n in (1, 2)],
              unit="por 1.000 palabras", origin="programatico",
              description="Recuentos con léxicos cerrados; incluyen titular, subtítulo y pies de foto.")
        s.table("Términos emotivos y sensacionalistas detectados", [{"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "tipo", "label": "Tipo"},
                                                                   {"key": "formas", "label": "Formas (apariciones)"}],
                [{"n": n, "tipo": t, "formas": ", ".join(f"{k} ({v})" for k, v in lx[n][key]["formas"].items()) or "—"}
                 for n in (1, 2) for key, t in (("emotivas", "Emotivo"), ("sensacionalistas", "Sensacionalista"))], origin="programatico")
        if ok:
            s.add("bars", "Emotividad y sensacionalismo (valoración 0–4)", categories=["Emotividad", "Sensacionalismo"],
                  series=[{"key": f"n{n}", "name": ctx.label(n), "values": [float(D(out.get(f"emotividad_n{n}")).get("valor") or 0),
                                                                             float(D(out.get(f"sensacionalismo_n{n}")).get("valor") or 0)]} for n in (1, 2)],
                  unit="escala 0–4", max=4, origin="modelo", description="Valoración del modelo, analizada por separado del recuento léxico.")
            sent = {n: Counter(S(x.get("valor")) for x in L(out.get(f"sentimiento_n{n}")) if isinstance(x, dict)) for n in (1, 2)}
            tot = {n: sum(sent[n].values()) or 1 for n in (1, 2)}
            s.add("bars", "Sentimiento por párrafo", categories=[ctx.label(1), ctx.label(2)], stacked=True, percent=True,
                  series=[{"key": k, "name": k.capitalize(), "values": [round(100 * sent[n][k] / tot[n], 1) for n in (1, 2)]}
                          for k in ("negativo", "neutro", "positivo")], unit="% de párrafos", origin="mixto", palette="sentiment",
                  description="El modelo clasifica cada párrafo; el sistema calcula los porcentajes.")
            ex = [e for e in L(out.get("expresiones")) if isinstance(e, dict)]
            if ex:
                s.table("Matriz de expresiones impactantes", [{"key": "ev", "label": "Expresión", "type": "evidencia_texto"},
                                                               {"key": "tipo", "label": "Tipo"}, {"key": "efe", "label": "Efecto"}],
                        [{"ev": ev_cell([e]), "tipo": S(e.get("tipo")), "efe": S(e.get("efecto"))} for e in ex], origin="modelo")
            s.table("Justificación de las valoraciones", [{"key": "dim", "label": "Dimensión"}, {"key": "n", "label": "Noticia", "type": "noticia"},
                                                          {"key": "v", "label": "0–4", "type": "num"}, {"key": "j", "label": "Justificación"},
                                                          {"key": "ev", "label": "Evidencias", "type": "evidencia"}],
                    [{"dim": lbl, "n": n, "v": D(out.get(f"{k}_n{n}")).get("valor"), "j": S(D(out.get(f"{k}_n{n}")).get("justificacion")),
                      "ev": ev_cell(D(out.get(f"{k}_n{n}")).get("evidencias"))}
                     for k, lbl in (("emotividad", "Emotividad"), ("sensacionalismo", "Sensacionalismo")) for n in (1, 2)], origin="modelo")
        else:
            self.no_llm(s, "La valoración de emotividad, sentimiento y sensacionalismo")

        # 7.3 modalidad
        s = sec["7.3"]
        cats = ["certeza", "probabilidad", "posibilidad", "incertidumbre", "hipotesis", "atribucion"]
        s.add("bars", "Marcadores de modalidad", categories=["Certeza", "Probabilidad", "Posibilidad", "Incertidumbre", "Hipótesis", "Atribución"],
              series=[{"key": f"n{n}", "name": ctx.label(n), "values": [mod[n]["por_categoria"].get(c, 0) for c in cats]} for n in (1, 2)],
              unit="marcadores", origin="programatico", description="Recuento de marcadores léxicos de modalidad epistémica (léxico cerrado).")
        s.compare("Oraciones sin marcas modales ni atribución", [
            {"label": "Oraciones sin marcas (afirmaciones categóricas aproximadas)", "n1": f"{mod[1]['oraciones_sin_marcas']} de {mod[1]['oraciones']}",
             "n2": f"{mod[2]['oraciones_sin_marcas']} de {mod[2]['oraciones']}"},
            {"label": "Oraciones con atribución, cita o verbo declarativo", "n1": f"{ctx.f[1]['atribucion']['con_atribucion']} ({ctx.f[1]['atribucion']['pct']} %)",
             "n2": f"{ctx.f[2]['atribucion']['con_atribucion']} ({ctx.f[2]['atribucion']['pct']} %)"},
            {"label": "Formas en condicional", "n1": ctx.f[1]["verbal"]["conteos"]["condicional"], "n2": ctx.f[2]["verbal"]["conteos"]["condicional"]}],
            origin="heuristico", description="Una oración sin marcadores ni atribución se presenta como afirmación del propio medio.")
        if ok:
            mm = [m for m in L(out.get("modalidad")) if isinstance(m, dict)]
            s.table("Tabla de modalidad (ejemplos)", [{"key": "ev", "label": "Fragmento", "type": "evidencia_texto"}, {"key": "tipo", "label": "Modalidad"},
                                                      {"key": "com", "label": "Comentario"}],
                    [{"ev": ev_cell([m]), "tipo": S(m.get("tipo")), "com": S(m.get("comentario"))} for m in mm], origin="modelo")

        # 7.4 recursos
        s = sec["7.4"]
        if ok:
            rec = [r for r in L(out.get("recursos")) if isinstance(r, dict)]
            if rec:
                c = {n: Counter(S(r.get("recurso")) for r in rec if r.get("n") == n) for n in (1, 2)}
                kinds = sorted(set(c[1]) | set(c[2]))
                s.add("bars", "Recursos retóricos identificados", categories=[k.replace("_", " ") for k in kinds],
                      series=[{"key": f"n{n}", "name": ctx.label(n), "values": [c[n].get(k, 0) for k in kinds]} for n in (1, 2)],
                      unit="recursos", origin="mixto")
                s.table("Matriz de recursos retóricos", [{"key": "ev", "label": "Fragmento", "type": "evidencia_texto"}, {"key": "rec", "label": "Recurso"},
                                                         {"key": "fun", "label": "Función"}],
                        [{"ev": ev_cell([r]), "rec": S(r.get("recurso")).replace("_", " "), "fun": S(r.get("funcion"))} for r in rec], origin="modelo")
            else:
                s.notice("no_disponible", "No se identificaron recursos retóricos relevantes.")
        else:
            self.llm_failed(s, out, "La identificación de recursos retóricos")
            s.status = "requiere_ia" if out is None else "error"

        # 7.5 gramática
        s = sec["7.5"]
        vb = {n: ctx.f[n]["verbal"] for n in (1, 2)}
        w = {n: max(1, ctx.f[n]["metricas"]["palabras"]) for n in (1, 2)}
        feats = [("verbos_declarativos", "Verbos de declaración"), ("preterito", "Verbos en pretérito (acción narrada)"),
                 ("pasiva_perifrastica", "Pasivas perifrásticas (ser + participio)"), ("construccion_se", "Construcciones con «se»"),
                 ("adverbios_mente", "Adverbios en -mente"), ("condicional", "Condicionales")]
        s.add("bars", "Rasgos gramaticales (por cada 100 palabras)", categories=[l for _, l in feats], orientation="h",
              series=[{"key": f"n{n}", "name": ctx.label(n), "values": [round(100 * vb[n]["conteos"].get(k, 0) / w[n], 2) for k, _ in feats]} for n in (1, 2)],
              unit="por 100 palabras", origin="heuristico",
              description="Formas reconocibles por patrones morfológicos. Las construcciones con «se» agrupan impersonales y pasivas reflejas (aproximado).")
        s.table("Ejemplos contextualizados", [{"key": "rasgo", "label": "Rasgo"}, {"key": "n", "label": "Noticia", "type": "noticia"},
                                              {"key": "ej", "label": "Ejemplos (unidad)"}],
                [{"rasgo": lbl, "n": n, "ej": ", ".join(f"{e['forma']} ({e['p']})" for e in vb[n]["ejemplos"].get(k, [])[:8]) or "—"}
                 for k, lbl in feats for n in (1, 2)], origin="heuristico")
        s.compare("Verbos de declaración más usados", [{"label": "Verbos (apariciones)", "n1": ", ".join(f"{k} ({v})" for k, v in vb[1]["declarativos_por_verbo"].items()) or "—",
                                                        "n2": ", ".join(f"{k} ({v})" for k, v in vb[2]["declarativos_por_verbo"].items()) or "—"}],
                  origin="programatico", description="Cada verbo de declaración elige cómo se presenta lo dicho (afirmar, denunciar, admitir...).")
        sp = engine.analyze([b["text"] for b in ctx.a1["blocks"] if b["type"] == "paragraph"]) if engine.load() else None
        if sp:
            sp2 = engine.analyze([b["text"] for b in ctx.a2["blocks"] if b["type"] == "paragraph"])
            cats = list(sp["pos_pct"].keys())
            s.add("bars", f"Categorías gramaticales ({sp['modelo']})", categories=cats, orientation="h",
                  series=[{"key": "n1", "name": ctx.label(1), "values": [sp["pos_pct"].get(c, 0) for c in cats]},
                          {"key": "n2", "name": ctx.label(2), "values": [sp2["pos_pct"].get(c, 0) for c in cats]}],
                  unit="% de palabras", origin="programatico", description="Etiquetado morfosintáctico con spaCy.")
        else:
            s.notice("no_disponible", "Distribución de categorías gramaticales (sustantivos, adjetivos, verbos...) no calculada: requiere el motor "
                                      "opcional spaCy. " + engine.status()["detalle"])
        if ok:
            adj = [a for a in L(out.get("adjetivos_valorativos")) if isinstance(a, dict) and a.get("adjetivo")]
            rows = []
            for n in (1, 2):
                art = ctx.articles[n - 1]
                for a in [x for x in adj if x.get("n") == n]:
                    c = count_mentions(art, [S(a.get("adjetivo"))])
                    rows.append({"n": n, "adj": S(a.get("adjetivo")), "val": S(a.get("valoracion")), "c": c["menciones"],
                                 "ev": ev_cell([a]) if a.get("cita") else {"ev": []}})
            if rows:
                s.table("Adjetivos valorativos", [{"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "adj", "label": "Adjetivo"},
                                                  {"key": "val", "label": "Valoración", "type": "valoracion"}, {"key": "c", "label": "Apariciones", "type": "num"},
                                                  {"key": "ev", "label": "Evidencia", "type": "evidencia"}], rows, origin="mixto",
                        description="El modelo identifica los adjetivos valorativos; el sistema cuenta sus apariciones literales.")

        # 7.6 formalidad
        s = sec["7.6"]
        rd = {n: ctx.f[n]["legibilidad"] for n in (1, 2)}
        if rd[1].get("disponible") and rd[2].get("disponible"):
            s.add("scale", "Legibilidad (escala INFLESZ, índice de Szigriszt-Pazos)", min=0, max=100,
                  bands=[{"from": 0, "to": 40, "label": "Muy difícil"}, {"from": 40, "to": 55, "label": "Algo difícil"},
                         {"from": 55, "to": 65, "label": "Normal"}, {"from": 65, "to": 80, "label": "Bastante fácil"}, {"from": 80, "to": 100, "label": "Muy fácil"}],
                  items=[{"key": f"n{n}", "name": ctx.label(n), "value": rd[n]["szigriszt_pazos"], "label": rd[n]["inflesz"]} for n in (1, 2)],
                  origin="programatico", description="Índice calculado por código con conteo silábico del español: 206,835 − 62,3·(sílabas/palabras) − (palabras/oraciones).")
            s.compare("Indicadores de complejidad", [
                {"label": "Índice de Fernández-Huerta", "n1": rd[1]["fernandez_huerta"], "n2": rd[2]["fernandez_huerta"]},
                {"label": "Índice de Szigriszt-Pazos (INFLESZ)", "n1": f"{rd[1]['szigriszt_pazos']} · {rd[1]['inflesz']}", "n2": f"{rd[2]['szigriszt_pazos']} · {rd[2]['inflesz']}"},
                {"label": "Sílabas por palabra", "n1": rd[1]["silabas_por_palabra"], "n2": rd[2]["silabas_por_palabra"]},
                {"label": "Palabras de 4 o más sílabas (%)", "n1": rd[1]["palabras_polisilabas_pct"], "n2": rd[2]["palabras_polisilabas_pct"]},
                {"label": "Media de palabras por oración", "n1": ctx.f[1]["metricas"]["media_palabras_oracion"], "n2": ctx.f[2]["metricas"]["media_palabras_oracion"]},
                {"label": "Densidad léxica (% de palabras de contenido)", "n1": rd[1]["densidad_lexica_pct"], "n2": rd[2]["densidad_lexica_pct"]},
                {"label": "Diversidad léxica (MATTR, ventana de 50)", "n1": rd[1]["mattr"], "n2": rd[2]["mattr"]}], origin="programatico")
        s.add("bars", "Registro institucional, jurídico y coloquial (por cada 1.000 palabras)",
              categories=["Fórmulas institucionales", "Lenguaje jurídico", "Coloquialismos"],
              series=[{"key": f"n{n}", "name": ctx.label(n), "values": [lx[n]["formulas_institucionales"]["por_1000"], lx[n]["lenguaje_juridico"]["por_1000"],
                                                                         lx[n]["coloquialismos"]["por_1000"]]} for n in (1, 2)],
              unit="por 1.000 palabras", origin="programatico")
        if ok:
            rows = []
            for k, lbl in (("registro", "Registro"), ("tecnicismos", "Tecnicismos"), ("coloquialismos", "Coloquialismos"),
                           ("formulas_institucionales", "Fórmulas institucionales"), ("lenguaje_juridico", "Lenguaje jurídico o burocrático"), ("claridad", "Claridad")):
                rows.append({"label": lbl, "n1": S(D(out.get("formalidad_n1")).get(k)) or "—", "n2": S(D(out.get("formalidad_n2")).get(k)) or "—"})
            s.compare("Formalidad y claridad", rows, origin="modelo")

        synthesis, origin = synth_from(out)
        if not synthesis:
            synthesis = heuristic_synthesis(
                [f"Vocabulario emotivo: {lx[1]['emotivas']['por_1000']} (N1) frente a {lx[2]['emotivas']['por_1000']} (N2) por 1.000 palabras.",
                 f"Legibilidad INFLESZ: {rd[1].get('inflesz')} (N1) y {rd[2].get('inflesz')} (N2)."], [],
                ["Sin modelo no se valoran tono, sentimiento ni recursos retóricos."])
            origin = "programatico"
        return list(sec.values()), synthesis, origin, verif_merge(out)


PHASE = Fase7()
