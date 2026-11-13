"""Fase 3. Análisis cronológico y evolución temporal."""
from __future__ import annotations

from ...llm.prompts import EVIDENCE, EVIDENCES, SYNTHESIS, s_arr, s_enum, s_obj, s_str
from ..base import Context, Phase, heuristic_synthesis, verif_merge
from ..helpers import D, L, S, ev_cell, fmt_dt, hours_between, origin_of, parse_dt, synth_from

EVENT = s_obj({
    "id": s_str("E1, E2..."), "descripcion": s_str("Acontecimiento breve"),
    "fecha_texto": s_str("Cómo lo expresa el texto (p. ej. «la madrugada de este jueves»)"),
    "fecha_normalizada": s_str("AAAA-MM-DD o AAAA-MM-DDTHH:MM si puede establecerse; vacío si no"),
    "precision": s_enum(["hora", "dia", "mes", "año", "relativa", "desconocida"]),
    "tipo": s_enum(["antecedente", "central", "consecuencia", "posterior", "proyeccion"]),
    "orden": {"type": "integer", "description": "Orden cronológico relativo (1 = más antiguo)"},
    "menciones": s_arr(EVIDENCE, "Una evidencia por cada noticia que lo menciona"),
    "diferencias": s_str("Si las noticias lo narran distinto (hora, cifras, detalles), explícalo"),
}, ["id", "descripcion", "precision", "tipo", "orden", "menciones"])
REF = s_obj({"texto": s_str(), "n": {"type": "integer", "enum": [1, 2]}, "p": s_str(), "cita": s_str()}, ["texto", "n", "p", "cita"])
PERSP = s_obj({"pasado": s_arr(REF), "presente": s_arr(REF), "futuro": s_arr(REF),
               "consecuencias_inmediatas": s_arr(REF), "consecuencias_largo_plazo": s_arr(REF),
               "referencias_historicas": s_arr(REF), "enfasis": s_enum(["pasado", "presente", "futuro", "equilibrado"])},
              ["pasado", "presente", "futuro", "enfasis"])
SCHEMA = s_obj({
    "acontecimientos": s_arr(EVENT),
    "duraciones": s_arr(s_obj({"descripcion": s_str(), "n": {"type": "integer", "enum": [1, 2]}, "p": s_str(), "cita": s_str()})),
    "perspectiva_n1": PERSP, "perspectiva_n2": PERSP,
    "evolucion": s_obj({"informacion_nueva_n1": s_arr(REF), "informacion_nueva_n2": s_arr(REF),
                        "cambios": s_arr(s_obj({"aspecto": s_str(), "n1": s_str(), "n2": s_str(), "explicacion": s_str(), "evidencias": EVIDENCES}))}),
    "sintesis": SYNTHESIS,
}, ["acontecimientos", "perspectiva_n1", "perspectiva_n2", "evolucion", "sintesis"])
INSTRUCTIONS = """Fase 3 — Análisis cronológico y evolución temporal.
1) Elabora UN inventario unificado de acontecimientos mencionados por cualquiera de las dos noticias
   (antecedentes, hecho central, consecuencias, hechos posteriores, proyecciones). Si ambas mencionan el mismo
   acontecimiento, regístralo una sola vez con una mención por noticia. Normaliza la fecha solo cuando el texto
   y la fecha de publicación permitan establecerla; si es una inferencia (p. ej. «este jueves»), usa precisión
   «dia» y explícalo en «diferencias» si hay discrepancia.
2) Señala duraciones e intervalos expresados.
3) Clasifica la perspectiva temporal de cada noticia (referencias al pasado, al presente, al futuro, consecuencias
   inmediatas y a largo plazo, referencias históricas) y su énfasis dominante.
4) Indica qué información aparece solo en una noticia y si puede deberse a una actualización o a una
   publicación posterior; señala cambios entre ambas versiones. Elabora la síntesis."""


class Fase3(Phase):
    number = 3
    title = "Análisis cronológico y evolución temporal"
    description = "Qué acontecimientos se narran, en qué orden y con qué perspectiva temporal."
    sections = [("3.1", "Identificación de acontecimientos y fechas", "¿Qué acontecimientos y referencias temporales recoge cada noticia?"),
                ("3.2", "Reconstrucción de la línea del tiempo", "¿Coinciden las secuencias de hechos narradas por ambos medios?"),
                ("3.3", "Perspectiva temporal del relato", "¿Miran los textos al pasado, al presente o al futuro?"),
                ("3.4", "Evolución y actualización del acontecimiento", "¿Qué información se incorporó entre una publicación y otra?")]

    def analyze(self, ctx: Context):
        sec = self.make_sections(self.sections)
        out = ctx.ask("fase3", INSTRUCTIONS, SCHEMA, description="Registra la fase 3.", max_tokens=9000)
        ok = out is not None and "__error__" not in out
        m1, m2 = ctx.a1["meta"], ctx.a2["meta"]

        # 3.1 inventario
        s31 = sec["3.1"]
        tex_rows = []
        for n in (1, 2):
            for t in ctx.f[n]["temporales"]:
                tex_rows.append({"n": n, "p": t["p"], "expresion": t["expresion"], "tipo": t["tipo"].replace("_", " "),
                                 "normalizada": t["normalizada"] or "—", "inferida": "Sí" if t.get("inferida") else ("No" if t.get("normalizada") else "—")})
        s31.table("Expresiones temporales detectadas", [
            {"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "p", "label": "Unidad", "type": "ref"},
            {"key": "expresion", "label": "Expresión"}, {"key": "tipo", "label": "Tipo"},
            {"key": "normalizada", "label": "Fecha normalizada"}, {"key": "inferida", "label": "Inferida de la fecha de publicación"}],
            tex_rows, origin="heuristico",
            description="Detección por patrones del español; las fechas relativas («ayer», «este jueves») se calculan desde la fecha de publicación.")
        events = []
        if ok:
            for e in L(out.get("acontecimientos")):
                if not isinstance(e, dict):
                    continue
                ns = sorted({int(m.get("n", 0)) for m in L(e.get("menciones")) if isinstance(m, dict) and m.get("n") in (1, 2)})
                events.append({**e, "articles": ns, "origin": origin_of(ns)})
            events.sort(key=lambda e: (e.get("orden") or 99))
            s31.table("Inventario cronológico de acontecimientos", [
                {"key": "orden", "label": "#", "type": "num"}, {"key": "descripcion", "label": "Acontecimiento"},
                {"key": "tipo", "label": "Tipo"}, {"key": "fecha", "label": "Fecha (texto)"}, {"key": "norm", "label": "Fecha normalizada"},
                {"key": "presencia", "label": "Mencionado en", "type": "presencia"}, {"key": "ev", "label": "Evidencias", "type": "evidencia"},
                {"key": "dif", "label": "Diferencias"}],
                [{"orden": e.get("orden"), "descripcion": S(e.get("descripcion")), "tipo": S(e.get("tipo")),
                  "fecha": S(e.get("fecha_texto"), "—"), "norm": S(e.get("fecha_normalizada"), "—"), "presencia": e["origin"],
                  "ev": ev_cell(e.get("menciones")), "dif": S(e.get("diferencias"))} for e in events], origin="mixto")
            durs = L(out.get("duraciones"))
            if durs:
                s31.table("Duraciones e intervalos", [{"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "d", "label": "Duración o intervalo"},
                                                      {"key": "ev", "label": "Evidencia", "type": "evidencia"}],
                          [{"n": d.get("n"), "d": S(d.get("descripcion")), "ev": ev_cell([d])} for d in durs if isinstance(d, dict)], origin="modelo")
        else:
            self.llm_failed(s31, out, "El inventario unificado de acontecimientos")

        # 3.2 línea del tiempo
        s32 = sec["3.2"]
        pubs = [{"n": n, "tipo": "publicacion", "fecha": ctx.articles[n - 1]["meta"].get("fecha_publicacion")} for n in (1, 2)]
        pubs += [{"n": n, "tipo": "actualizacion", "fecha": ctx.articles[n - 1]["meta"].get("fecha_actualizacion")} for n in (1, 2)
                 if ctx.articles[n - 1]["meta"].get("fecha_actualizacion") and ctx.articles[n - 1]["meta"].get("fecha_actualizacion") != ctx.articles[n - 1]["meta"].get("fecha_publicacion")]
        if ok and events:
            tl = [{"id": S(e.get("id")), "label": S(e.get("descripcion")), "date": S(e.get("fecha_normalizada")) or None,
                   "date_text": S(e.get("fecha_texto")), "precision": S(e.get("precision")), "tipo": S(e.get("tipo")),
                   "order": e.get("orden") or 0, "articles": e["articles"], "origin": e["origin"], "ev": L(e.get("menciones")),
                   "diferencias": S(e.get("diferencias"))} for e in events]
            shared = [e for e in events if e["origin"] == "shared"]
            only1 = [e for e in events if e["origin"] == "n1"]
            only2 = [e for e in events if e["origin"] == "n2"]
            s32.add("timeline", "Línea del tiempo comparativa", events=tl, publications=[p for p in pubs if p["fecha"]], origin="mixto",
                    description="Dos bandas horizontales (una por noticia); los acontecimientos compartidos se enlazan con una línea punteada y se muestran en el color neutro de «compartido». "
                                "Los hechos sin fecha establecida se ordenan por su posición cronológica relativa.",
                    interpretation=f"{len(shared)} acontecimientos compartidos, {len(only1)} exclusivos de la noticia 1 y {len(only2)} exclusivos de la noticia 2.")
            s32.table("Acontecimientos exclusivos", [{"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "d", "label": "Acontecimiento"},
                                                     {"key": "ev", "label": "Evidencia", "type": "evidencia"}],
                      [{"n": 1 if e["origin"] == "n1" else 2, "d": S(e.get("descripcion")), "ev": ev_cell(e.get("menciones"))} for e in only1 + only2],
                      origin="mixto")
        else:
            tl = []
            for n in (1, 2):
                for t in ctx.f[n]["temporales"]:
                    if t.get("normalizada") and len(str(t["normalizada"])) == 10:
                        tl.append({"id": f"{n}-{t['id']}", "label": t["contexto"][:110], "date": t["normalizada"], "date_text": t["expresion"],
                                   "precision": "dia", "tipo": "", "order": 0, "articles": [n], "origin": f"n{n}",
                                   "ev": [{"n": n, "p": t["p"], "cita": t["expresion"], "verificacion": "literal"}]})
            if tl:
                s32.add("timeline", "Referencias temporales fechadas", events=tl, publications=[p for p in pubs if p["fecha"]],
                        origin="heuristico", description="Sin modelo, se ubican solo las expresiones temporales que pudieron fecharse.")
            else:
                s32.set_status("insuficiente", "No hay referencias temporales fechables.")
                s32.notice("insuficiente", "No se identificaron referencias temporales que puedan situarse en una línea del tiempo.")

        # 3.3 perspectiva
        s33 = sec["3.3"]
        vb = {n: ctx.f[n]["verbal"]["conteos"] for n in (1, 2)}
        cats = [("preterito", "Pretérito perfecto simple"), ("preterito_compuesto", "Pretérito compuesto"),
                ("imperfecto", "Pretérito imperfecto"), ("futuro", "Futuro"), ("condicional", "Condicional")]
        s33.add("bars", "Rasgos verbales de temporalidad", categories=[c[1] for c in cats],
                series=[{"key": f"n{n}", "name": ctx.label(n), "values": [vb[n].get(k, 0) for k, _ in cats]} for n in (1, 2)],
                unit="formas verbales", origin="heuristico",
                description="Formas reconocibles por su terminación (p. ej. -ó, -aron, -rá). El presente no se cuenta: "
                            "sin etiquetador morfosintáctico es ambiguo con sustantivos y adjetivos.")
        if ok:
            cols = []
            for col, lbl in (("pasado", "Pasado"), ("presente", "Presente"), ("futuro", "Futuro")):
                items = []
                for n in (1, 2):
                    for r in L(D(out.get(f"perspectiva_n{n}")).get(col)):
                        if isinstance(r, dict):
                            items.append({"n": n, "text": S(r.get("texto")), "ev": [r]})
                cols.append({"key": col, "label": lbl, "items": items})
            s33.add("temporal3", "Diagrama pasado – presente – futuro", columns=cols, origin="modelo",
                    description="Referencias temporales clasificadas por el modelo; el color indica la noticia.")
            rows = []
            for key, lbl in (("consecuencias_inmediatas", "Consecuencias inmediatas"), ("consecuencias_largo_plazo", "Consecuencias a largo plazo"),
                             ("referencias_historicas", "Referencias históricas"), ("enfasis", "Énfasis dominante")):
                v1, v2 = D(out.get("perspectiva_n1")).get(key), D(out.get("perspectiva_n2")).get(key)
                fmt = lambda v: "; ".join(S(x.get("texto")) for x in L(v) if isinstance(x, dict)) or ("—" if isinstance(v, list) else S(v, "—"))
                rows.append({"label": lbl, "n1": fmt(v1), "n2": fmt(v2)})
            s33.compare("Matriz de perspectiva temporal", rows, origin="modelo")
        else:
            self.llm_failed(s33, out, "La clasificación de la perspectiva temporal")

        # 3.4 evolución
        s34 = sec["3.4"]
        plan = ctx.plan_status("3.4")
        if plan.get("estado") == "insuficiente":
            s34.set_status("insuficiente", plan.get("motivo", ""))
            s34.notice("insuficiente", plan.get("motivo", "Sin fechas disponibles."))
        else:
            rows = []
            for n in (1, 2):
                mm = ctx.articles[n - 1]["meta"]
                upd = mm.get("fecha_actualizacion")
                lag = hours_between(mm.get("fecha_publicacion"), upd) if upd and upd != mm.get("fecha_publicacion") else None
                central = next((e for e in events if e.get("tipo") == "central" and len(S(e.get("fecha_normalizada"))) >= 10), None) if ok else None
                since = hours_between(central.get("fecha_normalizada"), mm.get("fecha_publicacion")) if central else None
                rows.append({"n": n, "pub": fmt_dt(mm.get("fecha_publicacion")),
                             "upd": fmt_dt(upd) if upd and upd != mm.get("fecha_publicacion") else "Sin actualización indicada",
                             "lag": f"{lag} h" if lag is not None else "—",
                             "since": f"{since} h" if since is not None else ("Fecha del hecho no establecida" if ok else "Requiere modelo")})
            s34.table("Tabla de evolución temporal", [
                {"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "pub", "label": "Publicación"},
                {"key": "upd", "label": "Actualización"}, {"key": "lag", "label": "Tiempo hasta la actualización"},
                {"key": "since", "label": "Tiempo entre el hecho central y la publicación"}], rows, origin="programatico" if not ok else "mixto",
                description="Intervalos calculados por código a partir de las fechas extraídas (y de la fecha del hecho central, si pudo establecerse).")
            s34.add("pubchrono", "Cronología de publicaciones", publications=[p for p in pubs if p["fecha"]],
                    labels={1: ctx.label(1), 2: ctx.label(2)}, origin="programatico",
                    description="Momentos de publicación y actualización de cada noticia.")
            if ok:
                ev = D(out.get("evolucion"))
                rows = []
                for n in (1, 2):
                    for r in L(ev.get(f"informacion_nueva_n{n}")):
                        if isinstance(r, dict):
                            rows.append({"n": n, "info": S(r.get("texto")), "ev": ev_cell([r])})
                if rows:
                    s34.table("Información presente solo en una de las publicaciones", [
                        {"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "info", "label": "Información"},
                        {"key": "ev", "label": "Evidencia", "type": "evidencia"}], rows, origin="modelo")
                ch = L(ev.get("cambios"))
                if ch:
                    s34.table("Cambios entre versiones del acontecimiento", [
                        {"key": "aspecto", "label": "Aspecto"}, {"key": "n1", "label": "Noticia 1"}, {"key": "n2", "label": "Noticia 2"},
                        {"key": "exp", "label": "Explicación"}, {"key": "ev", "label": "Evidencias", "type": "evidencia"}],
                        [{"aspecto": S(c.get("aspecto")), "n1": S(c.get("n1")), "n2": S(c.get("n2")), "exp": S(c.get("explicacion")),
                          "ev": ev_cell(c.get("evidencias"))} for c in ch if isinstance(c, dict)], origin="modelo")

        synthesis, origin = synth_from(out)
        if not synthesis:
            gap = hours_between(m1.get("fecha_publicacion"), m2.get("fecha_publicacion"))
            synthesis = heuristic_synthesis(
                [f"Separación entre publicaciones: {abs(gap)} horas." if gap is not None else "No hay fechas comparables."],
                [], ["Sin modelo no se reconstruye el inventario unificado de acontecimientos."])
            origin = "programatico"
        return list(sec.values()), synthesis, origin, verif_merge(out)


PHASE = Fase3()
