"""Fase 8. Actores, representación social, política e ideológica."""
from __future__ import annotations

from ...llm.prompts import EVIDENCE, EVIDENCES, NIVEL, SYNTHESIS, s_arr, s_enum, s_num, s_obj, s_str
from ...nlp import engine
from ...nlp.features import count_mentions
from ..base import Context, Phase, heuristic_synthesis, verif_merge
from ..helpers import D, L, S, ev_cell, origin_from_counts, synth_from

AGENCY = s_enum(["activa", "pasiva", "mixta", "ausente"])
ACTOR = s_obj({
    "id": s_str("A1, A2..."), "nombre": s_str("Nombre canónico"),
    "alias": s_arr(s_str(), "TODAS las formas literales con que se le nombra en cualquiera de las noticias (apellido, cargo, sigla)"),
    "tipo": s_enum(["persona", "institucion", "autoridad", "organizacion", "empresa", "grupo", "colectivo"]),
    "categoria": s_enum(["autoridad", "afectado", "victima", "presunto_responsable", "testigo", "experto", "familiar", "institucion", "medio", "otro"]),
    "rol": s_enum(["principal", "secundario"]),
    "agencia_n1": AGENCY, "agencia_n2": AGENCY,
    "acciones_n1": s_arr(s_obj({"accion": s_str(), "p": s_str(), "cita": s_str(), "n": {"type": "integer", "enum": [1]}})),
    "acciones_n2": s_arr(s_obj({"accion": s_str(), "p": s_str(), "cita": s_str(), "n": {"type": "integer", "enum": [2]}})),
    "decide": {"type": "boolean", "description": "¿Toma decisiones que afectan al acontecimiento según algún texto?"},
    "representacion": s_obj({"genero": s_str("Solo si el texto lo explicita; si no, «no consta»"), "edad": s_str(), "ocupacion": s_str(),
                             "pertenencia": s_str(), "vulnerabilidad": s_str(), "autonomia": s_str()}),
    "denominaciones": s_arr(s_obj({"n": {"type": "integer", "enum": [1, 2]}, "p": s_str(), "cita": s_str("Expresión literal usada para nombrarlo"),
                                   "valoracion": s_enum(["favorable", "desfavorable", "neutral"])}, ["n", "p", "cita", "valoracion"])),
}, ["id", "nombre", "alias", "tipo", "categoria", "rol", "agencia_n1", "agencia_n2", "denominaciones"])
SCHEMA_A = s_obj({"actores": s_arr(ACTOR), "victimas": s_obj({"n1": s_str(), "n2": s_str()}),
                  "autoridades": s_obj({"n1": s_str(), "n2": s_str()})}, ["actores"])
INSTR_A = """Fase 8 (primera parte) — Identificación y caracterización de actores.
1) Elabora un inventario UNIFICADO de actores (personas, instituciones, autoridades, afectados, víctimas, presuntos
   responsables, organizaciones) de ambas noticias. Incluye en «alias» todas las formas literales con que se nombra
   a cada uno: el sistema contará sus menciones con ellas.
2) Para cada actor y noticia, indica su agencia (activa: actúa o decide; pasiva: le ocurren cosas; mixta; ausente)
   y sus acciones con evidencia.
3) Representación social: registra género, edad, ocupación, pertenencia cultural o vulnerabilidad SOLO cuando el texto
   lo explicita; en otro caso, escribe «no consta».
4) Registra las denominaciones y caracterizaciones con que cada noticia nombra a cada actor (literal) y su valoración."""
REL = s_obj({"origen": s_str("id del actor"), "destino": s_str("id del actor"),
             "tipo": s_enum(["autoridad", "subordinacion", "conflicto", "apoyo", "alianza", "acusacion", "investigacion", "negociacion",
                             "dependencia", "atencion", "sancion", "comunicacion", "otro"]),
             "etiqueta": s_str("Verbo o frase breve"), "noticias": s_arr({"type": "integer", "enum": [1, 2]}), "nivel": NIVEL, "evidencias": EVIDENCES},
            ["origen", "destino", "tipo", "etiqueta", "noticias", "evidencias"])
POLDIM = [("legitimacion_institucional", "Legitimación institucional"), ("cuestionamiento_institucional", "Cuestionamiento institucional"),
          ("responsabilidad_politica", "Responsabilidad política"), ("enfasis_ciudadano", "Énfasis ciudadano"),
          ("perspectiva_estructural", "Perspectiva estructural"), ("conflicto_poder", "Conflicto de poder")]
POL = s_obj({"estado": s_str("Cómo se representa al Estado"), "instituciones": s_str(), "gobierno": s_str(), "autoridades": s_str(),
             "legitimacion": s_str(), "cuestionamiento": s_str(), "responsabilidad_politica": s_str(), "soluciones_politicas": s_str(),
             "enfasis": s_enum(["institucional", "ciudadano", "mixto"]), "perspectiva_estructural": s_str(),
             "radar": s_obj({k: s_num("", 0, 4) for k, _ in POLDIM}, [k for k, _ in POLDIM]), "evidencias": EVIDENCES},
            ["estado", "instituciones", "legitimacion", "cuestionamiento", "enfasis", "radar"])
SCHEMA_B = s_obj({
    "relaciones": s_arr(REL),
    "politica_n1": POL, "politica_n2": POL,
    "responsabilidades": s_arr(s_obj({"actor": s_str("id del actor"), "tipo": s_enum(["individual", "institucional"]),
                                      "estado": s_enum(["acusacion_atribuida", "responsabilidad_establecida", "negada", "descargo", "no_determinada", "sugerida_por_el_medio"]),
                                      "atribuida_por": s_str("Quién la atribuye según el texto"), "n": {"type": "integer", "enum": [1, 2]},
                                      "p": s_str(), "cita": s_str()}, ["actor", "tipo", "estado", "atribuida_por", "n", "p", "cita"])),
    "victimizacion": s_obj({"n1": s_str("Cómo se representa a las víctimas"), "n2": s_str()}),
    "sintesis_actores": s_obj({"protagonistas": s_str(), "diferencias_representacion": s_str(), "relaciones_poder": s_str(),
                               "agencia": s_str(), "legitimidad": s_str(), "responsabilidades": s_str()}),
    "sintesis": SYNTHESIS,
}, ["relaciones", "politica_n1", "politica_n2", "responsabilidades", "sintesis_actores", "sintesis"])
INSTR_B_TMPL = """Fase 8 (segunda parte) — Relaciones de poder, representación política y responsabilidad.
Inventario de actores (usa estos identificadores):
{actors}
1) Identifica relaciones entre actores (autoridad, subordinación, conflicto, apoyo, alianza, acusación, investigación,
   negociación, dependencia, atención...) indicando en qué noticias aparecen.
2) Describe la representación del Estado, las instituciones, el gobierno y las autoridades en cada noticia
   (legitimación o cuestionamiento, responsabilidad política, soluciones, énfasis institucional o ciudadano,
   perspectiva estructural) y puntúa de 0 a 4 las dimensiones del radar. No asignes una ideología al medio.
3) Registra las atribuciones de responsabilidad distinguiendo acusación atribuida, responsabilidad establecida,
   negación, descargo y responsabilidad no determinada. Una acusación de un testigo NO es responsabilidad demostrada.
4) Sintetiza la representación de los actores y elabora la síntesis de la fase."""


class Fase8(Phase):
    number = 8
    title = "Actores, representación social, política e ideológica"
    description = "Quiénes aparecen, cuánto espacio y agencia reciben, cómo se les nombra y qué relaciones y responsabilidades se les atribuyen."
    sections = [("8.1", "Identificación y clasificación de actores", "¿Qué actores intervienen en cada relato?"),
                ("8.2", "Protagonismo, visibilidad y agencia", "¿Quién ocupa más espacio y quién actúa o padece?"),
                ("8.3", "Representación social e identitaria", "¿Cómo se representa socialmente a los actores?"),
                ("8.4", "Caracterización y denominación", "¿Con qué palabras se nombra a cada actor?"),
                ("8.5", "Relaciones de poder", "¿Qué relaciones de autoridad, conflicto o apoyo se establecen?"),
                ("8.6", "Representación política e ideológica", "¿Cómo aparecen el Estado y las instituciones?"),
                ("8.7", "Culpabilización, victimización y responsabilidad", "¿A quién se atribuye responsabilidad y con qué fundamento?"),
                ("8.8", "Síntesis de la representación de los actores", "¿Qué diferencias globales de representación hay?")]

    def analyze(self, ctx: Context):
        sec = self.make_sections(self.sections)
        for sid in ("8.3", "8.5", "8.6", "8.7"):
            p = ctx.plan_status(sid)
            if p.get("estado") == "no_aplicable":
                sec[sid].set_status("no_aplicable", p.get("motivo", ""))
                sec[sid].notice("no_aplicable", p.get("motivo", ""))
        cands = "Entidades detectadas por el sistema (orientativas): " + "; ".join(
            f"N{n}: " + ", ".join(f"{e['nombre']} ({e['tipo']})" for e in ctx.f[n]["entidades"][:40]) for n in (1, 2))
        outA = ctx.ask("fase8a", INSTR_A, SCHEMA_A, extra=cands, description="Registra los actores.", max_tokens=11000)
        okA = outA is not None and "__error__" not in outA
        actors = []
        if okA:
            actors = [a for a in L(outA.get("actores")) if isinstance(a, dict) and a.get("nombre")]
        else:
            for n in (1, 2):
                for e in ctx.f[n]["entidades"]:
                    if e["tipo"] in ("persona", "organizacion") and not any(a["nombre"].lower() == e["nombre"].lower() for a in actors):
                        actors.append({"id": f"A{len(actors) + 1}", "nombre": e["nombre"], "alias": e.get("alias", []),
                                       "tipo": "persona" if e["tipo"] == "persona" else "organizacion", "categoria": "", "rol": ""})
        for a in actors:
            al = [a["nombre"]] + [x for x in L(a.get("alias")) if isinstance(x, str)]
            a["_m"] = {1: count_mentions(ctx.a1, al), 2: count_mentions(ctx.a2, al)}
            a["_origin"] = origin_from_counts(a["_m"][1]["menciones"], a["_m"][2]["menciones"])
        actors.sort(key=lambda a: -(a["_m"][1]["menciones"] + a["_m"][2]["menciones"]))
        outB = None
        if okA and actors:
            listing = "\n".join(f"{a['id']}: {a['nombre']} ({S(a.get('tipo'))}, {S(a.get('categoria'))})" for a in actors)
            outB = ctx.ask("fase8b", INSTR_B_TMPL.format(actors=listing), SCHEMA_B, description="Registra relaciones y responsabilidad.", max_tokens=10000)
        okB = outB is not None and "__error__" not in outB

        # 8.1
        s = sec["8.1"]
        s.table("Inventario de actores", [
            {"key": "nombre", "label": "Actor"}, {"key": "tipo", "label": "Tipo"}, {"key": "cat", "label": "Categoría"}, {"key": "rol", "label": "Rol"},
            {"key": "presencia", "label": "Presente en", "type": "presencia"}, {"key": "m1", "label": "Menciones N1", "type": "num"},
            {"key": "m2", "label": "Menciones N2", "type": "num"}, {"key": "alias", "label": "Formas de mención"}],
            [{"nombre": a["nombre"], "tipo": S(a.get("tipo")), "cat": S(a.get("categoria")).replace("_", " ") or "—", "rol": S(a.get("rol")) or "—",
              "presencia": a["_origin"], "m1": a["_m"][1]["menciones"], "m2": a["_m"][2]["menciones"], "alias": ", ".join(L(a.get("alias")))} for a in actors],
            origin="mixto" if okA else "heuristico",
            description="Menciones contadas por código con todas las formas de mención (sin distinguir mayúsculas ni tildes).")
        if okA:
            cats = {}
            for a in actors:
                c = S(a.get("categoria")).replace("_", " ") or "otro"
                cats.setdefault(c, [0, 0])
                for n in (1, 2):
                    if a["_m"][n]["menciones"]:
                        cats[c][n - 1] += 1
            s.add("bars", "Actores por categoría", categories=list(cats.keys()),
                  series=[{"key": f"n{n}", "name": ctx.label(n), "values": [v[n - 1] for v in cats.values()]} for n in (1, 2)],
                  unit="actores", origin="mixto")
        else:
            self.no_llm(s, "La consolidación y clasificación de actores")

        # 8.2 protagonismo
        s = sec["8.2"]
        top = actors[:12]
        s.add("bars", "Protagonismo: menciones por actor", categories=[a["nombre"] for a in top], orientation="h",
              series=[{"key": f"n{n}", "name": ctx.label(n), "values": [a["_m"][n]["menciones"] for a in top]} for n in (1, 2)],
              unit="menciones", origin="programatico")
        s.add("bars", "Visibilidad: palabras de los párrafos donde aparece cada actor", categories=[a["nombre"] for a in top], orientation="h",
              series=[{"key": f"n{n}", "name": ctx.label(n), "values": [a["_m"][n]["palabras_contexto"] for a in top]} for n in (1, 2)],
              unit="palabras", origin="programatico", description="Aproximación al espacio dedicado: suma de las palabras de los párrafos en los que se menciona al actor.")
        sp = None
        if engine.load():
            aliases = {a["id"]: [a["nombre"]] + L(a.get("alias")) for a in actors}
            sp = {n: engine.analyze([b["text"] for b in ctx.articles[n - 1]["blocks"] if b["type"] == "paragraph"], aliases) for n in (1, 2)}
        rows = []
        for a in actors:
            r = {"nombre": a["nombre"]}
            for n in (1, 2):
                m = a["_m"][n]
                r[f"pos{n}"] = m["primera"] or ("Solo titular/subtítulo" if m["en_titular"] or m["en_subtitulo"] else "—")
                r[f"tit{n}"] = "Sí" if m["en_titular"] or m["en_subtitulo"] else "No"
                r[f"ag{n}"] = S(a.get(f"agencia_n{n}")) or "—"
                if sp and sp[n]:
                    g = sp[n]["agencia"].get(a["id"], {})
                    r[f"sx{n}"] = f"{g.get('agente', 0)} / {g.get('paciente', 0)}"
            r["decide"] = "Sí" if a.get("decide") else ("No" if okA else "—")
            rows.append(r)
        cols = [{"key": "nombre", "label": "Actor"},
                {"key": "tit1", "label": "En titular o subtítulo N1"}, {"key": "pos1", "label": "Primera aparición N1", "type": "ref"},
                {"key": "ag1", "label": "Agencia N1", "type": "agencia"},
                {"key": "tit2", "label": "En titular o subtítulo N2"}, {"key": "pos2", "label": "Primera aparición N2", "type": "ref"},
                {"key": "ag2", "label": "Agencia N2", "type": "agencia"}, {"key": "decide", "label": "Toma decisiones"}]
        if sp:
            cols += [{"key": "sx1", "label": "Sujeto/objeto sintáctico N1"}, {"key": "sx2", "label": "Sujeto/objeto sintáctico N2"}]
        s.table("Matriz de agencia y visibilidad", cols, rows, origin="mixto" if okA else "programatico",
                description="Presencia en titulares y primera aparición se calculan por código; la agencia (activa/pasiva) la valora el modelo." +
                            (" El índice sintáctico procede de spaCy." if sp else ""))
        if okA:
            items = []
            for a in actors[:14]:
                for n in (1, 2):
                    for ac in L(a.get(f"acciones_n{n}")):
                        if isinstance(ac, dict):
                            items.append({"actor": a["nombre"], "n": n, "accion": S(ac.get("accion")), "ev": ev_cell([{**ac, "n": n}])})
            if items:
                s.table("Acciones atribuidas a los actores", [{"key": "actor", "label": "Actor"}, {"key": "n", "label": "Noticia", "type": "noticia"},
                                                              {"key": "accion", "label": "Acción"}, {"key": "ev", "label": "Evidencia", "type": "evidencia"}],
                        items, origin="modelo")

        # 8.3 representación social
        s = sec["8.3"]
        if s.status != "no_aplicable":
            if okA:
                rows = []
                for a in actors:
                    r = D(a.get("representacion"))
                    if not r or all(S(v).lower() in ("", "no consta", "no_consta") for v in r.values()):
                        continue
                    rows.append({"actor": a["nombre"], "gen": S(r.get("genero"), "no consta"), "edad": S(r.get("edad"), "no consta"),
                                 "ocu": S(r.get("ocupacion"), "no consta"), "per": S(r.get("pertenencia"), "no consta"),
                                 "vul": S(r.get("vulnerabilidad"), "no consta"), "aut": S(r.get("autonomia"), "no consta")})
                s.table("Matriz de representación social", [{"key": "actor", "label": "Actor"}, {"key": "gen", "label": "Género"},
                                                            {"key": "edad", "label": "Edad"}, {"key": "ocu", "label": "Ocupación"},
                                                            {"key": "per", "label": "Pertenencia"}, {"key": "vul", "label": "Vulnerabilidad"},
                                                            {"key": "aut", "label": "Autonomía"}], rows, origin="modelo",
                        description="Solo se registran atributos explícitos en el texto; «no consta» indica que la noticia no los menciona (no se infieren).")
                vic = D(outA.get("victimas"))
                if vic:
                    s.compare("Representación de las víctimas y de las autoridades", [
                        {"label": "Víctimas", "n1": S(vic.get("n1"), "—"), "n2": S(vic.get("n2"), "—")},
                        {"label": "Autoridades", "n1": S(D(outA.get("autoridades")).get("n1"), "—"), "n2": S(D(outA.get("autoridades")).get("n2"), "—")}],
                        origin="modelo")
            else:
                self.llm_failed(s, outA, "La representación social")
                s.status = "requiere_ia" if outA is None else "error"

        # 8.4 denominaciones
        s = sec["8.4"]
        if okA:
            rows = []
            for a in actors:
                for d in L(a.get("denominaciones")):
                    if isinstance(d, dict):
                        rows.append({"actor": a["nombre"], "n": d.get("n"), "ev": ev_cell([d]), "val": S(d.get("valoracion"))})
            s.table("Tabla de denominaciones y caracterizaciones", [{"key": "actor", "label": "Actor"}, {"key": "n", "label": "Noticia", "type": "noticia"},
                                                                    {"key": "ev", "label": "Denominación", "type": "evidencia_texto"},
                                                                    {"key": "val", "label": "Valoración", "type": "valoracion"}], rows, origin="modelo")
            changes = []
            for a in actors:
                f1 = {S(d.get("cita")).lower() for d in L(a.get("denominaciones")) if isinstance(d, dict) and d.get("n") == 1}
                f2 = {S(d.get("cita")).lower() for d in L(a.get("denominaciones")) if isinstance(d, dict) and d.get("n") == 2}
                if f1 and f2 and f1 != f2:
                    changes.append({"label": a["nombre"], "n1": ", ".join(sorted(f1)), "n2": ", ".join(sorted(f2))})
            if changes:
                s.compare("Cambios en la forma de nombrar a un mismo actor", changes, origin="mixto")
        else:
            self.llm_failed(s, outA, "El análisis de denominaciones")
            s.status = "requiere_ia" if outA is None else "error"

        # 8.5 relaciones de poder
        by_id = {a["id"]: a for a in actors}
        s = sec["8.5"]
        if s.status != "no_aplicable":
            if okB:
                rels = [r for r in L(outB.get("relaciones")) if isinstance(r, dict) and r.get("origen") in by_id and r.get("destino") in by_id]
                used = {r["origen"] for r in rels} | {r["destino"] for r in rels}
                nodes = [{"id": a["id"], "label": a["nombre"], "type": S(a.get("tipo")), "origin": a["_origin"],
                          "size": a["_m"][1]["menciones"] + a["_m"][2]["menciones"], "categoria": S(a.get("categoria"))} for a in actors if a["id"] in used]
                edges = []
                for r in rels:
                    ns = [int(x) for x in L(r.get("noticias")) if str(x) in ("1", "2")]
                    edges.append({"source": r["origen"], "target": r["destino"], "label": S(r.get("etiqueta")) or S(r.get("tipo")),
                                  "tipo": S(r.get("tipo")), "origin": "shared" if set(ns) == {1, 2} else f"n{ns[0]}" if ns else "shared",
                                  "nivel": S(r.get("nivel")), "ev": L(r.get("evidencias"))})
                s.add("graph", "Grafo de actores y relaciones", nodes=nodes, edges=edges, directed=True, origin="modelo",
                      description="Cada color corresponde a un medio; el color neutro indica lo compartido. El tamaño del nodo es proporcional a las menciones.")
                s.table("Relaciones entre actores", [{"key": "a", "label": "Origen"}, {"key": "rel", "label": "Relación"}, {"key": "b", "label": "Destino"},
                                                     {"key": "presencia", "label": "Presente en", "type": "presencia"}, {"key": "nivel", "label": "Nivel", "type": "nivel"},
                                                     {"key": "ev", "label": "Evidencias", "type": "evidencia"}],
                        [{"a": by_id[e["source"]]["nombre"], "rel": e["label"], "b": by_id[e["target"]]["nombre"], "presencia": e["origin"],
                          "nivel": e["nivel"] or "explicito", "ev": ev_cell(e["ev"])} for e in edges], origin="modelo")
            else:
                self.llm_failed(s, outB, "El grafo de relaciones de poder")
                s.status = "requiere_ia" if outB is None else "error"

        # 8.6 representación política
        s = sec["8.6"]
        if s.status != "no_aplicable":
            if okB:
                p1, p2 = D(outB.get("politica_n1")), D(outB.get("politica_n2"))
                s.compare("Matriz de encuadre político e institucional", [{"label": lbl, "n1": S(p1.get(k)) or "—", "n2": S(p2.get(k)) or "—"} for k, lbl in (
                    ("estado", "Representación del Estado"), ("instituciones", "Instituciones"), ("gobierno", "Gobierno"), ("autoridades", "Autoridades"),
                    ("legitimacion", "Legitimación"), ("cuestionamiento", "Cuestionamiento"), ("responsabilidad_politica", "Responsabilidad política"),
                    ("soluciones_politicas", "Soluciones políticas"), ("enfasis", "Énfasis"), ("perspectiva_estructural", "Perspectiva estructural"))],
                    origin="modelo", evidence={"n1": L(p1.get("evidencias")), "n2": L(p2.get("evidencias"))},
                    description="Representación en estas dos noticias concretas: no describe la línea editorial general de los medios.")
                s.add("radar", "Dimensiones político-institucionales (0–4)", axes=[l for _, l in POLDIM], max=4,
                      series=[{"key": f"n{n}", "name": ctx.label(n), "values": [float(D(D(outB.get(f"politica_n{n}")).get("radar")).get(k) or 0) for k, _ in POLDIM]}
                              for n in (1, 2)], origin="modelo")
            else:
                self.llm_failed(s, outB, "La representación política e institucional")
                s.status = "requiere_ia" if outB is None else "error"

        # 8.7 responsabilidad
        s = sec["8.7"]
        if s.status != "no_aplicable":
            if okB:
                lbl = {"acusacion_atribuida": "Acusación atribuida", "responsabilidad_establecida": "Responsabilidad establecida", "negada": "Negada",
                       "descargo": "Descargo", "no_determinada": "No determinada", "sugerida_por_el_medio": "Sugerida por el medio"}
                rows = [{"actor": by_id.get(r.get("actor"), {}).get("nombre", S(r.get("actor"))), "tipo": S(r.get("tipo")),
                         "estado": lbl.get(S(r.get("estado")), S(r.get("estado"))), "por": S(r.get("atribuida_por")), "n": r.get("n"),
                         "ev": ev_cell([r])} for r in L(outB.get("responsabilidades")) if isinstance(r, dict)]
                s.table("Matriz de responsabilidades", [{"key": "actor", "label": "Actor"}, {"key": "tipo", "label": "Tipo"},
                                                        {"key": "estado", "label": "Estado de la atribución"}, {"key": "por", "label": "Atribuida por"},
                                                        {"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "ev", "label": "Evidencia", "type": "evidencia"}],
                        rows, origin="modelo", description="Se distingue la acusación atribuida a una fuente de la responsabilidad establecida.")
                vic = D(outB.get("victimizacion"))
                if vic:
                    s.compare("Representación de las víctimas", [{"label": "Víctimas", "n1": S(vic.get("n1"), "—"), "n2": S(vic.get("n2"), "—")}], origin="modelo")
            else:
                self.llm_failed(s, outB, "El análisis de responsabilidades")
                s.status = "requiere_ia" if outB is None else "error"

        # 8.8 síntesis de actores
        s = sec["8.8"]
        if okB:
            sa = D(outB.get("sintesis_actores"))
            s.compare("Síntesis de la representación de los actores", [{"label": lbl, "n1": S(sa.get(k)) or "—", "n2": ""} for k, lbl in (
                ("protagonistas", "Protagonistas"), ("diferencias_representacion", "Diferencias de representación"), ("relaciones_poder", "Relaciones de poder"),
                ("agencia", "Agencia"), ("legitimidad", "Legitimidad"), ("responsabilidades", "Responsabilidades"))], origin="modelo", single=True)
        else:
            shared = [a["nombre"] for a in actors if a["_origin"] == "shared"]
            s.text(f"Actores presentes en ambas noticias: {', '.join(shared[:10]) or 'ninguno identificado'}. "
                   f"Exclusivos de N1: {sum(1 for a in actors if a['_origin'] == 'n1')}; exclusivos de N2: {sum(1 for a in actors if a['_origin'] == 'n2')}.",
                   origin="programatico" if not okA else "mixto")

        synthesis, origin = synth_from(outB)
        if not synthesis:
            synthesis = heuristic_synthesis([f"Actores con más menciones: {', '.join(a['nombre'] for a in actors[:4])}."], [],
                                            ["Sin modelo, los actores se detectan por mayúsculas y no se valoran agencia, relaciones ni responsabilidades."])
            origin = "programatico"
        for a in actors:
            a.pop("_m", None)
        return list(sec.values()), synthesis, origin, verif_merge(outA, outB)


PHASE = Fase8()
