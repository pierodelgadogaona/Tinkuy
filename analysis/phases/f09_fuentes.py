"""Fase 9. Fuentes, testimonios y atribución de la información."""
from __future__ import annotations

from collections import Counter, defaultdict

from ...llm.prompts import EVIDENCES, SYNTHESIS, s_arr, s_enum, s_obj, s_str
from ...nlp.text import count_words
from ..base import Context, Phase, heuristic_synthesis, verif_merge
from ..helpers import D, L, S, ev_cell, synth_from

SOURCE_TYPES = ["oficial", "institucional", "experta", "testimonial", "documental", "independiente", "anonima", "mediatica", "empresarial"]
TYPE_LABELS = {"oficial": "Oficial", "institucional": "Institucional", "experta": "Experta", "testimonial": "Testimonial", "documental": "Documental",
               "independiente": "Independiente", "anonima": "Anónima", "mediatica": "Mediática", "empresarial": "Empresarial"}
SCHEMA = s_obj({
    "fuentes": s_arr(s_obj({"id": s_str("F1..."), "nombre": s_str(), "tipo": s_enum(SOURCE_TYPES), "identificada": {"type": "boolean"},
                            "noticias": s_arr({"type": "integer", "enum": [1, 2]}), "descripcion": s_str()},
                           ["id", "nombre", "tipo", "identificada", "noticias"])),
    "citas": s_arr(s_obj({"ref": {"type": ["string", "null"], "description": "Identificador de cita directa detectada por el sistema (N1-C2); null si es indirecta"},
                          "n": {"type": "integer", "enum": [1, 2]}, "p": s_str(), "cita": s_str("Fragmento literal (para indirectas, la oración que lo reporta)"),
                          "fuente": s_str("id de la fuente"), "modalidad": s_enum(["directa", "indirecta"]),
                          "tipo": s_enum(["testimonio", "declaracion_institucional", "dato", "opinion", "acusacion", "descargo"])},
                         ["n", "p", "cita", "fuente", "modalidad", "tipo"])),
    "versiones": s_arr(s_obj({"tema": s_str(), "posiciones": s_arr(s_obj({"fuente": s_str(), "n": {"type": "integer", "enum": [1, 2]}, "posicion": s_str()})),
                              "contraste": s_enum(["coincidencia", "contradiccion", "respuesta", "descargo", "sin_contraste"]), "explicacion": s_str()},
                             ["tema", "posiciones", "contraste"])),
    "trazabilidad": s_arr(s_obj({"n": {"type": "integer", "enum": [1, 2]}, "p": s_str(), "cita": s_str(), "afirmacion": s_str(),
                                 "origen": s_str("id de la fuente, «medio» si la afirma el propio medio, o «no_atribuida»"),
                                 "explicita": {"type": "boolean"}, "documento": s_str()}, ["n", "p", "cita", "afirmacion", "origen", "explicita"])),
    "sintesis": SYNTHESIS,
}, ["fuentes", "citas", "versiones", "trazabilidad", "sintesis"])
INSTRUCTIONS = """Fase 9 — Fuentes, testimonios y atribución.
Se te entrega el listado de citas directas detectadas por el sistema (N1-Cx / N2-Cx).
1) Inventaría las fuentes (oficiales, institucionales, expertas, testimoniales, documentales, independientes,
   anónimas, mediáticas, empresariales), indicando si están identificadas y en qué noticias aparecen.
2) Asigna cada cita directa detectada a su fuente (usa «ref») y añade las citas indirectas (discurso referido sin
   comillas) con su fragmento literal. No inventes fuentes que el texto no nombra.
3) Contrasta versiones: temas sobre los que distintas fuentes coinciden, se contradicen, responden o se descargan.
4) Traza el origen de las afirmaciones relevantes (fuente, el propio medio o sin atribuir) y la documentación
   mencionada. El sistema calculará palabras atribuidas, porcentajes y concentración de voces. Elabora la síntesis."""


class Fase9(Phase):
    number = 9
    title = "Fuentes, testimonios y atribución de la información"
    description = "A quién se da la palabra, cuánto espacio recibe cada voz y de dónde procede cada afirmación."
    sections = [("9.1", "Identificación y clasificación de fuentes", "¿Qué fuentes utiliza cada noticia?"),
                ("9.2", "Testimonios y citas", "¿Cómo se citan las voces y cuánto espacio reciben?"),
                ("9.3", "Contraste de versiones", "¿Se contrastan versiones distintas?"),
                ("9.4", "Atribución y trazabilidad", "¿Puede rastrearse el origen de cada afirmación?"),
                ("9.5", "Distribución de voces", "¿Qué tipos de voces predominan y qué tan concentradas están?")]

    def analyze(self, ctx: Context):
        sec = self.make_sections(self.sections)
        q = {n: ctx.f[n]["citas"] for n in (1, 2)}
        listing = "\n".join(f"N{n}-{c['id']} [{c['p']}] «{c['texto']}» (verbo: {c['verbo'] or '—'}; hablante probable: {c['hablante_heuristico'] or '—'})"
                            for n in (1, 2) for c in q[n]["citas"]) or "(no se detectaron citas directas)"
        out = ctx.ask("fase9", INSTRUCTIONS, SCHEMA, extra="CITAS DIRECTAS DETECTADAS POR EL SISTEMA\n" + listing,
                      description="Registra la fase 9.", max_tokens=10000)
        ok = out is not None and "__error__" not in out
        att = {n: ctx.f[n]["atribucion"] for n in (1, 2)}
        decl = {n: ctx.f[n]["verbal"] for n in (1, 2)}

        fuentes = {S(f.get("id")): f for f in L(out.get("fuentes")) if isinstance(f, dict)} if ok else {}
        citas = [c for c in L(out.get("citas")) if isinstance(c, dict)] if ok else []
        qmap = {f"N{n}-{c['id']}".upper(): c for n in (1, 2) for c in q[n]["citas"]}
        words_by_source = {1: Counter(), 2: Counter()}
        inter_by_source = {1: Counter(), 2: Counter()}
        for c in citas:
            n = c.get("n") if c.get("n") in (1, 2) else 1
            ref = S(c.get("ref")).upper()
            w = qmap[ref]["palabras"] if ref in qmap else count_words(S(c.get("cita")))
            c["_palabras"] = w
            if c.get("verificacion") == "no_localizada" and ref not in qmap:
                continue
            words_by_source[n][S(c.get("fuente"))] += w
            inter_by_source[n][S(c.get("fuente"))] += 1

        # 9.1
        s = sec["9.1"]
        if ok:
            rows = []
            for fid, f in fuentes.items():
                ns = [int(x) for x in L(f.get("noticias")) if str(x) in ("1", "2")]
                rows.append({"nombre": S(f.get("nombre")), "tipo": TYPE_LABELS.get(S(f.get("tipo")), S(f.get("tipo"))),
                             "ident": "Sí" if f.get("identificada") else "No", "presencia": "shared" if set(ns) == {1, 2} else (f"n{ns[0]}" if ns else "shared"),
                             "i1": inter_by_source[1][fid], "i2": inter_by_source[2][fid], "w1": words_by_source[1][fid], "w2": words_by_source[2][fid],
                             "desc": S(f.get("descripcion"))})
            s.table("Tabla de fuentes", [{"key": "nombre", "label": "Fuente"}, {"key": "tipo", "label": "Tipo"}, {"key": "ident", "label": "Identificada"},
                                         {"key": "presencia", "label": "Presente en", "type": "presencia"}, {"key": "i1", "label": "Intervenciones N1", "type": "num"},
                                         {"key": "i2", "label": "Intervenciones N2", "type": "num"}, {"key": "w1", "label": "Palabras N1", "type": "num"},
                                         {"key": "w2", "label": "Palabras N2", "type": "num"}, {"key": "desc", "label": "Descripción"}],
                    rows, origin="mixto", description="Intervenciones y palabras atribuidas se calculan por código a partir de las citas asignadas a cada fuente.")
            by_type = {n: Counter() for n in (1, 2)}
            for fid, f in fuentes.items():
                for n in (1, 2):
                    if n in [int(x) for x in L(f.get("noticias")) if str(x) in ("1", "2")]:
                        by_type[n][S(f.get("tipo"))] += 1
            types = [t for t in SOURCE_TYPES if by_type[1][t] or by_type[2][t]]
            s.add("bars", "Fuentes por tipo", categories=[TYPE_LABELS[t] for t in types],
                  series=[{"key": f"n{n}", "name": ctx.label(n), "values": [by_type[n][t] for t in types]} for n in (1, 2)], unit="fuentes", origin="mixto")
        else:
            self.llm_failed(s, out, "La identificación y clasificación de fuentes")
            s.status = "requiere_ia" if out is None else "error"
        s.compare("Indicadores programáticos de atribución", [
            {"label": "Citas directas (≥ 4 palabras)", "n1": q[1]["n_directas"], "n2": q[2]["n_directas"]},
            {"label": "Expresiones breves entrecomilladas", "n1": q[1]["n_expresiones_breves"], "n2": q[2]["n_expresiones_breves"]},
            {"label": "Palabras entre comillas en el cuerpo", "n1": f"{q[1]['palabras_citadas']} ({q[1]['pct_texto_citado']} %)",
             "n2": f"{q[2]['palabras_citadas']} ({q[2]['pct_texto_citado']} %)"},
            {"label": "Verbos de declaración", "n1": decl[1]["conteos"]["verbos_declarativos"], "n2": decl[2]["conteos"]["verbos_declarativos"]},
            {"label": "Construcciones de discurso indirecto (verbo declarativo + «que»)", "n1": decl[1]["discurso_indirecto"], "n2": decl[2]["discurso_indirecto"]},
            {"label": "Oraciones con atribución explícita", "n1": f"{att[1]['con_atribucion']} de {att[1]['oraciones']} ({att[1]['pct']} %)",
             "n2": f"{att[2]['con_atribucion']} de {att[2]['oraciones']} ({att[2]['pct']} %)"}], origin="programatico")

        # 9.2
        s = sec["9.2"]
        if ok:
            rows = [{"fuente": S(fuentes.get(S(c.get("fuente")), {}).get("nombre"), S(c.get("fuente"))), "n": c.get("n"),
                     "mod": S(c.get("modalidad")), "tipo": S(c.get("tipo")).replace("_", " "), "pal": c.get("_palabras", 0), "ev": ev_cell([c])} for c in citas]
            s.table("Matriz de citas", [{"key": "ev", "label": "Cita", "type": "evidencia_texto"}, {"key": "fuente", "label": "Fuente"},
                                        {"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "mod", "label": "Modalidad"},
                                        {"key": "tipo", "label": "Tipo"}, {"key": "pal", "label": "Palabras", "type": "num"}], rows, origin="mixto")
            mod = {n: Counter(S(c.get("modalidad")) for c in citas if c.get("n") == n) for n in (1, 2)}
            s.add("bars", "Citas directas e indirectas", categories=["Directas", "Indirectas"],
                  series=[{"key": f"n{n}", "name": ctx.label(n), "values": [mod[n]["directa"], mod[n]["indirecta"]]} for n in (1, 2)], unit="citas", origin="mixto")
        else:
            rows = [{"n": n, "ev": {"ev": [{"n": n, "p": c["p"], "cita": c["texto"][:220], "verificacion": "literal"}]}, "verbo": c["verbo"] or "—",
                     "habl": c["hablante_heuristico"] or "—", "pal": c["palabras"]} for n in (1, 2) for c in q[n]["citas"] if not c["breve"]]
            s.table("Citas directas detectadas", [{"key": "ev", "label": "Cita", "type": "evidencia_texto"}, {"key": "n", "label": "Noticia", "type": "noticia"},
                                                  {"key": "verbo", "label": "Verbo"}, {"key": "habl", "label": "Hablante probable"},
                                                  {"key": "pal", "label": "Palabras", "type": "num"}], rows, origin="heuristico")
            self.no_llm(s, "La asignación de citas a fuentes")

        # 9.3
        s = sec["9.3"]
        if ok:
            vers = [v for v in L(out.get("versiones")) if isinstance(v, dict)]
            if vers:
                rows = []
                for v in vers:
                    pos = "; ".join(f"{S(fuentes.get(S(p.get('fuente')), {}).get('nombre'), S(p.get('fuente')))} (N{p.get('n')}): {S(p.get('posicion'))}"
                                    for p in L(v.get("posiciones")) if isinstance(p, dict))
                    rows.append({"tema": S(v.get("tema")), "pos": pos, "con": S(v.get("contraste")).replace("_", " "), "exp": S(v.get("explicacion"))})
                s.table("Matriz de contraste de versiones", [{"key": "tema", "label": "Tema"}, {"key": "pos", "label": "Posiciones"},
                                                             {"key": "con", "label": "Contraste"}, {"key": "exp", "label": "Explicación"}], rows, origin="modelo")
                cnt = Counter(r["con"] for r in rows)
                s.add("bars", "Tipos de contraste", categories=list(cnt.keys()), series=[{"key": "shared", "name": "Ambas noticias", "values": list(cnt.values())}],
                      unit="temas", origin="mixto")
            else:
                s.notice("no_disponible", "No se identificaron temas con versiones contrastadas.")
        else:
            self.llm_failed(s, out, "El contraste de versiones")
            s.status = "requiere_ia" if out is None else "error"

        # 9.4
        s = sec["9.4"]
        if ok:
            tr = [t for t in L(out.get("trazabilidad")) if isinstance(t, dict)]
            def orig(t):
                o = S(t.get("origen"))
                return "El propio medio" if o == "medio" else "Sin atribuir" if o in ("no_atribuida", "") else S(fuentes.get(o, {}).get("nombre"), o)
            s.table("Matriz de trazabilidad", [{"key": "ev", "label": "Afirmación (fragmento)", "type": "evidencia_texto"}, {"key": "af", "label": "Contenido"},
                                               {"key": "or", "label": "Origen"}, {"key": "exp", "label": "Atribución explícita"}, {"key": "doc", "label": "Documento"}],
                    [{"ev": ev_cell([t]), "af": S(t.get("afirmacion")), "or": orig(t), "exp": "Sí" if t.get("explicita") else "No",
                      "doc": S(t.get("documento"), "—")} for t in tr], origin="modelo")
            cnt = {n: Counter(("medio" if S(t.get("origen")) == "medio" else "sin" if S(t.get("origen")) in ("no_atribuida", "") else "fuente")
                              for t in tr if t.get("n") == n) for n in (1, 2)}
            s.add("bars", "Origen de las afirmaciones relevantes", categories=["Atribuidas a una fuente", "Asumidas por el medio", "Sin atribuir"],
                  series=[{"key": f"n{n}", "name": ctx.label(n), "values": [cnt[n]["fuente"], cnt[n]["medio"], cnt[n]["sin"]]} for n in (1, 2)],
                  unit="afirmaciones", origin="mixto")
        else:
            self.no_llm(s, "La trazabilidad de las afirmaciones")

        # 9.5
        s = sec["9.5"]
        if ok and fuentes:
            types = [t for t in SOURCE_TYPES if any(words_by_source[n][fid] for n in (1, 2) for fid, f in fuentes.items() if S(f.get("tipo")) == t)]
            wt = {n: {t: sum(words_by_source[n][fid] for fid, f in fuentes.items() if S(f.get("tipo")) == t) for t in types} for n in (1, 2)}
            tot = {n: sum(wt[n].values()) or 1 for n in (1, 2)}
            s.add("bars", "Distribución de palabras atribuidas por tipo de fuente", categories=[ctx.label(1), ctx.label(2)], stacked=True, percent=True,
                  series=[{"key": f"t{i}", "name": TYPE_LABELS[t], "values": [round(100 * wt[n][t] / tot[n], 1) for n in (1, 2)]} for i, t in enumerate(types)],
                  unit="% de palabras citadas", origin="mixto", palette="categorical",
                  description="Barras apiladas al 100 %: proporción de las palabras atribuidas (citas directas e indirectas) a cada tipo de fuente.")
            rows = []
            for n in (1, 2):
                vals = [v for v in words_by_source[n].values() if v]
                total = sum(vals) or 1
                hhi = round(sum((v / total) ** 2 for v in vals), 3) if vals else None
                topname = max(words_by_source[n], key=words_by_source[n].get) if vals else None
                rows.append({"n": n, "unicas": len([1 for fid, f in fuentes.items() if n in [int(x) for x in L(f.get('noticias')) if str(x) in ('1', '2')]]),
                             "interv": sum(inter_by_source[n].values()), "pal": sum(vals),
                             "top": f"{S(fuentes.get(topname, {}).get('nombre'), '—')} ({round(100 * words_by_source[n][topname] / total)} %)" if topname else "—",
                             "hhi": hhi if hhi is not None else "—"})
            s.table("Concentración de voces", [{"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "unicas", "label": "Fuentes únicas", "type": "num"},
                                               {"key": "interv", "label": "Intervenciones", "type": "num"}, {"key": "pal", "label": "Palabras atribuidas", "type": "num"},
                                               {"key": "top", "label": "Voz con más espacio"}, {"key": "hhi", "label": "Índice de concentración (HHI)", "type": "num"}],
                    rows, origin="programatico",
                    description="HHI = suma de los cuadrados de la proporción de palabras de cada fuente: 1 indica una sola voz; valores bajos, voces repartidas.")
        else:
            if not ok:
                self.no_llm(s, "La distribución de voces por fuente")
            s.add("bars", "Palabras entre comillas", categories=["Palabras citadas", "Resto del cuerpo"], stacked=False,
                  series=[{"key": f"n{n}", "name": ctx.label(n), "values": [q[n]["palabras_citadas"], max(0, ctx.f[n]["metricas"]["palabras"] - q[n]["palabras_citadas"])]}
                          for n in (1, 2)], unit="palabras", origin="programatico")

        synthesis, origin = synth_from(out)
        if not synthesis:
            synthesis = heuristic_synthesis([f"Texto entre comillas: {q[1]['pct_texto_citado']} % (N1) frente a {q[2]['pct_texto_citado']} % (N2)."], [],
                                            ["Sin modelo no se identifican ni clasifican las fuentes."])
            origin = "programatico"
        return list(sec.values()), synthesis, origin, verif_merge(out)


PHASE = Fase9()
