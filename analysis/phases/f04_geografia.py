"""Fase 4. Análisis geográfico y territorial."""
from __future__ import annotations

import re

from ...geo import geocoder
from ...llm.prompts import CERTEZA, EVIDENCE, EVIDENCES, SYNTHESIS, s_arr, s_enum, s_obj, s_str
from ...nlp.features import count_mentions
from ...nlp.text import norm_key
from ..base import Context, Phase, heuristic_synthesis, verif_merge
from ..helpers import D, L, S, ev_cell, origin_from_counts, presence_label, synth_from

LEVELS = ["pais", "region", "provincia", "ciudad", "distrito", "localidad", "via", "edificio", "punto"]
PLACE = s_obj({
    "id": s_str("L1, L2..."), "nombre": s_str("Nombre tal como aparece"),
    "alias": s_arr(s_str(), "Otras formas literales con que se nombra el mismo lugar en los textos"),
    "tipo": s_enum(["lugar_acontecimiento", "institucion", "hospital", "espacio_publico", "via", "ciudad", "region", "pais", "otro"]),
    "roles": s_arr(s_enum(["escenario", "origen", "destino", "ubicacion_actor", "consecuencia", "contexto"])),
    "nivel_precision": s_enum(LEVELS, "Máxima precisión que el TEXTO permite establecer"),
    "consulta_geocodificacion": s_str("Consulta para un geocodificador con la jerarquía que el texto permite (p. ej. «San Bartolo, Lima, Perú»). No añadas datos que el texto no da."),
    "codigo_pais": s_str("Código ISO de dos letras del país, si el texto lo permite"),
    "centralidad_n1": s_enum(["alta", "media", "baja", "ausente"]), "centralidad_n2": s_enum(["alta", "media", "baja", "ausente"]),
    "menciones": s_arr(EVIDENCE),
}, ["id", "nombre", "tipo", "roles", "nivel_precision", "consulta_geocodificacion", "menciones"])
ROUTE = s_obj({"id": s_str(), "desde": s_str("id del lugar de origen"), "hasta": s_str("id del lugar de destino"),
               "quien": s_str("Quién o qué se desplaza"), "medio": s_str(), "orden": {"type": "integer"},
               "noticias": s_arr({"type": "integer", "enum": [1, 2]}), "certeza": CERTEZA, "evidencias": EVIDENCES},
              ["id", "desde", "hasta", "quien", "noticias", "evidencias"])
SCHEMA = s_obj({
    "lugares": s_arr(PLACE), "recorridos": s_arr(ROUTE),
    "escala_n1": s_enum(["local", "regional", "nacional", "internacional"]), "escala_n2": s_enum(["local", "regional", "nacional", "internacional"]),
    "justificacion_escala": s_str(),
    "relaciones_entre_lugares": s_arr(s_str()),
    "diferencias_precision": s_arr(s_obj({"lugar": s_str(), "n1": s_str(), "n2": s_str()})),
    "sintesis": SYNTHESIS,
}, ["lugares", "recorridos", "escala_n1", "escala_n2", "sintesis"])
INSTRUCTIONS = """Fase 4 — Análisis geográfico y territorial.
1) Identifica TODOS los lugares mencionados (escenario del hecho, instituciones, hospitales, espacios públicos,
   vías, ciudades, regiones, países, ubicaciones de actores, orígenes y destinos) en un inventario unificado.
   Para cada uno, indica la precisión máxima que el texto permite: si solo se menciona un distrito, el nivel es
   «distrito», aunque conozcas la dirección exacta. La consulta de geocodificación solo puede contener la
   jerarquía de lugares que el propio texto ofrece (más el país si se deduce claramente).
2) Identifica recorridos o traslados descritos (origen → destino), quién se desplaza y en qué orden. No inventes
   rutas que la noticia no permita establecer.
3) Valora la escala geográfica de cada noticia y las diferencias en la precisión con que cada una ubica los
   hechos. Elabora la síntesis."""


def _norm(t: str) -> str:
    return " ".join(re.findall(r"\w+", norm_key(t or "")))


def _rank(level: str) -> int:
    return LEVELS.index(level) if level in LEVELS else len(LEVELS)


def assign_parents(places: list[dict]) -> None:
    """Jerarquía territorial a partir de la consulta que el modelo construyó con lo que el texto permite
    («San Bartolo, Lima, Perú»: Lima contiene a San Bartolo). Solo se enlaza con lugares que la noticia también
    menciona y de escala mayor, de modo que no se inventan relaciones ni se forman ciclos."""
    by_name = {}
    for q in places:
        for nm in [q["nombre"]] + [a for a in L(q.get("alias")) if isinstance(a, str)]:
            by_name.setdefault(_norm(nm), q)
    for p in places:
        p["_parent"] = None
        parts = [x.strip() for x in S(p.get("consulta_geocodificacion")).split(",")][1:]
        for part in parts:
            q = by_name.get(_norm(part))
            if q and q is not p and _rank(S(q.get("nivel_precision"))) < _rank(S(p.get("nivel_precision"))):
                p["_parent"] = q.get("id")
                break


def territory_node(p: dict) -> dict:
    k1, k2 = p["_c"][0], p["_c"][1]
    return {"id": p.get("id"), "name": p["nombre"], "nivel": S(p.get("nivel_precision")) or "sin_determinar", "tipo": S(p.get("tipo")),
            "roles": [S(r) for r in L(p.get("roles"))], "origin": p["_origin"], "m1": k1, "m2": k2, "parent": p.get("_parent"),
            "consulta": S(p.get("consulta_geocodificacion")), "ev": L(p.get("menciones"))}


class Fase4(Phase):
    number = 4
    title = "Análisis geográfico y territorial"
    description = "Dónde ocurre el acontecimiento, qué recorridos se describen y con qué precisión espacial."
    sections = [("4.1", "Identificación de lugares", "¿Qué lugares menciona cada noticia y con qué función?"),
                ("4.2", "Recorridos, desplazamientos y traslados", "¿Qué desplazamientos describen y coinciden?"),
                ("4.3", "Distribución territorial y escala geográfica", "¿A qué escala y con qué precisión sitúan los hechos?"),
                ("4.4", "Comparación de la representación espacial", "¿Qué espacios reciben más atención en cada medio?")]

    def analyze(self, ctx: Context):
        sec = self.make_sections(self.sections)
        for sid in ("4.1", "4.2", "4.3", "4.4"):
            p = ctx.plan_status(sid)
            if p.get("estado") == "no_aplicable":
                sec[sid].set_status("no_aplicable", p.get("motivo", ""))
                sec[sid].notice("no_aplicable", p.get("motivo", ""))
        if sec["4.1"].status == "no_aplicable":
            return list(sec.values()), heuristic_synthesis([], [], ["Las noticias no mencionan lugares."]), "programatico", None
        out = ctx.ask("fase4", INSTRUCTIONS, SCHEMA, description="Registra la fase 4.", max_tokens=9000)
        ok = out is not None and "__error__" not in out
        geo_on = ctx.options.get("geocodificacion", True)

        places = []
        if ok:
            for p in L(out.get("lugares")):
                if isinstance(p, dict) and p.get("nombre"):
                    places.append(p)
        else:
            seen = set()
            for n in (1, 2):
                for e in ctx.f[n]["entidades"]:
                    if e["tipo"] == "lugar" and e["nombre"].lower() not in seen:
                        seen.add(e["nombre"].lower())
                        places.append({"id": f"L{len(places) + 1}", "nombre": e["nombre"], "alias": [], "tipo": "otro", "roles": [],
                                       "nivel_precision": "", "consulta_geocodificacion": e["nombre"], "menciones": []})
        # menciones (programático); la geocodificación es opcional y solo aporta distancias aproximadas
        for p in places:
            aliases = [p["nombre"]] + [a for a in L(p.get("alias")) if isinstance(a, str)]
            c1, c2 = count_mentions(ctx.a1, aliases), count_mentions(ctx.a2, aliases)
            # una mención verificada en una noticia cuenta aunque use otra forma
            m_ns = {int(m.get("n")) for m in L(p.get("menciones")) if isinstance(m, dict) and m.get("n") in (1, 2) and m.get("verificacion") != "no_localizada"}
            k1 = c1["menciones"] or (1 if 1 in m_ns else 0)
            k2 = c2["menciones"] or (1 if 2 in m_ns else 0)
            p["_c"] = (k1, k2, c1, c2)
            p["_origin"] = origin_from_counts(k1, k2)
            g = None
            if geo_on:
                cc = S(p.get("codigo_pais")).lower()[:2] or "pe"
                g = geocoder.geocode(S(p.get("consulta_geocodificacion")) or p["nombre"], nivel_texto=S(p.get("nivel_precision")), country_codes=cc)
            p["_geo"] = g
        assign_parents(places)
        nodes = [territory_node(p) for p in places]
        n_shared = sum(1 for p in places if p["_origin"] == "shared")

        s41 = sec["4.1"]
        s41.add("territory", "Diagrama de lugares y escalas territoriales", nodes=nodes, routes=[], mode="escalas", origin="mixto" if ok else "heuristico",
                description="Cada fila es una escala territorial (del país al punto concreto). El color indica en qué noticia aparece el lugar; "
                            "las líneas unen cada lugar con el espacio mayor que lo contiene según el propio texto.",
                interpretation=f"{len(nodes)} lugares: {n_shared} aparecen en ambas noticias, {sum(1 for p in places if p['_origin'] == 'n1')} solo en la 1 "
                               f"y {sum(1 for p in places if p['_origin'] == 'n2')} solo en la 2.")
        s41.table("Inventario de lugares", [
            {"key": "nombre", "label": "Lugar"}, {"key": "tipo", "label": "Tipo"}, {"key": "roles", "label": "Función"},
            {"key": "presencia", "label": "Mencionado en", "type": "presencia"}, {"key": "m1", "label": "Menciones N1", "type": "num"},
            {"key": "m2", "label": "Menciones N2", "type": "num"}, {"key": "nivel", "label": "Precisión del texto"},
            *([{"key": "ubic", "label": "Coordenadas (OpenStreetMap)"}] if geo_on else []),
            {"key": "ev", "label": "Evidencias", "type": "evidencia"}],
            [{"nombre": p["nombre"], "tipo": S(p.get("tipo")).replace("_", " "), "roles": ", ".join(S(r) for r in L(p.get("roles"))),
              "presencia": p["_origin"], "m1": p["_c"][0], "m2": p["_c"][1], "nivel": S(p.get("nivel_precision"), "—"),
              **({"ubic": (("Aproximada · " if (p["_geo"] or {}).get("aproximada") else "") + S((p["_geo"] or {}).get("fuente")))
                  if p["_geo"] and not p["_geo"].get("no_localizado") else "No localizada"} if geo_on else {}),
              "ev": ev_cell(p.get("menciones"))} for p in places],
            origin="mixto" if ok else "heuristico",
            description="Las menciones se cuentan por código (coincidencia literal del nombre y sus variantes).")
        if not ok:
            self.llm_failed(s41, out, "La clasificación de los lugares por función y precisión")

        # 4.2 recorridos
        s42 = sec["4.2"]
        if s42.status != "no_aplicable":
            if ok:
                by_id = {p.get("id"): p for p in places}
                routes, rows = [], []
                for r in L(out.get("recorridos")):
                    if not isinstance(r, dict):
                        continue
                    a, b = by_id.get(r.get("desde")), by_id.get(r.get("hasta"))
                    ns = [int(x) for x in L(r.get("noticias")) if str(x) in ("1", "2")]
                    org = "shared" if set(ns) == {1, 2} else ("n1" if ns == [1] else "n2")
                    dist, approx = None, False
                    ga, gb = (a or {}).get("_geo"), (b or {}).get("_geo")
                    if ga and gb and not ga.get("no_localizado") and not gb.get("no_localizado"):
                        dist = round(geocoder._dist_km((ga["lat"], ga["lon"]), (gb["lat"], gb["lon"])), 1)
                        approx = bool(ga.get("aproximada") or gb.get("aproximada"))
                    rows.append({"orden": r.get("orden"), "quien": S(r.get("quien")), "desde": a["nombre"] if a else S(r.get("desde")),
                                 "hasta": b["nombre"] if b else S(r.get("hasta")), "medio": S(r.get("medio"), "—"), "presencia": org,
                                 "certeza": S(r.get("certeza")), "dist": dist, "ev": ev_cell(r.get("evidencias"))})
                    if a and b:
                        routes.append({"from": a.get("id"), "to": b.get("id"), "origin": org, "label": S(r.get("quien")), "medio": S(r.get("medio")),
                                       "order": r.get("orden") or 0, "certeza": S(r.get("certeza")), "distancia_km": dist, "aproximada": approx,
                                       "ev": L(r.get("evidencias"))})
                if rows:
                    involved = {r["from"] for r in routes} | {r["to"] for r in routes}
                    s42.add("territory", "Diagrama de recorridos y traslados", nodes=[n for n in nodes if n["id"] in involved], routes=routes, mode="rutas",
                            origin="mixto", description="Las flechas van del origen al destino que describen las noticias y se numeran por orden. "
                                                         "Indican la relación entre lugares, no la ruta real recorrida, que las noticias no establecen.")
                    s42.table("Secuencia de desplazamientos", [
                        {"key": "orden", "label": "#", "type": "num"}, {"key": "quien", "label": "Quién se desplaza"},
                        {"key": "desde", "label": "Origen"}, {"key": "hasta", "label": "Destino"}, {"key": "medio", "label": "Medio"},
                        {"key": "presencia", "label": "Descrito en", "type": "presencia"}, {"key": "certeza", "label": "Certeza"},
                        *([{"key": "dist", "label": "Distancia aprox. (km)", "type": "num"}] if any(r["dist"] is not None for r in rows) else []),
                        {"key": "ev", "label": "Evidencias", "type": "evidencia"}], rows, origin="modelo")
                else:
                    s42.set_status("no_disponible", "Las noticias no describen desplazamientos con origen y destino identificables.")
                    s42.notice("no_disponible", "Las noticias no describen desplazamientos con origen y destino identificables.")
            else:
                self.llm_failed(s42, out, "La identificación de recorridos")

        # 4.3 escala
        s43 = sec["4.3"]
        if s43.status != "no_aplicable":
            levels = {n: {} for n in (1, 2)}
            for p in places:
                lvl = S(p.get("nivel_precision")) or (p["_geo"] or {}).get("nivel") or "sin determinar"
                for n in (1, 2):
                    if p["_c"][n - 1]:
                        levels[n][lvl] = levels[n].get(lvl, 0) + 1
            cats = [l for l in LEVELS + ["sin determinar"] if levels[1].get(l) or levels[2].get(l)]
            if cats:
                s43.add("bars", "Precisión geográfica de las referencias", categories=cats,
                        series=[{"key": f"n{n}", "name": ctx.label(n), "values": [levels[n].get(c, 0) for c in cats]} for n in (1, 2)],
                        unit="lugares", origin="mixto" if ok else "heuristico",
                        description="Número de lugares distintos según el nivel de precisión con que el texto los nombra.")
            if ok:
                s43.compare("Escala geográfica", [
                    {"label": "Escala", "n1": S(out.get("escala_n1")), "n2": S(out.get("escala_n2"))},
                    {"label": "Lugares distintos", "n1": sum(1 for p in places if p["_c"][0]), "n2": sum(1 for p in places if p["_c"][1])},
                    {"label": "Justificación", "n1": S(out.get("justificacion_escala")), "n2": ""}], origin="mixto")
                dp = L(out.get("diferencias_precision"))
                if dp:
                    s43.table("Diferencias en la precisión geográfica", [{"key": "lugar", "label": "Lugar"}, {"key": "n1", "label": "Noticia 1"},
                                                                          {"key": "n2", "label": "Noticia 2"}],
                              [{"lugar": S(d.get("lugar")), "n1": S(d.get("n1")), "n2": S(d.get("n2"))} for d in dp if isinstance(d, dict)], origin="modelo")
                rel = L(out.get("relaciones_entre_lugares"))
                if rel:
                    s43.text("\n".join(f"• {S(r)}" for r in rel), title="Relaciones entre lugares")

        # 4.4 representación espacial
        s44 = sec["4.4"]
        if s44.status != "no_aplicable" and places:
            top = sorted(places, key=lambda p: -(p["_c"][0] + p["_c"][1]))[:12]
            s44.add("bars", "Lugares que reciben mayor atención", categories=[p["nombre"] for p in top], orientation="h",
                    series=[{"key": "n1", "name": ctx.label(1), "values": [p["_c"][0] for p in top]},
                            {"key": "n2", "name": ctx.label(2), "values": [p["_c"][1] for p in top]}],
                    unit="menciones", origin="programatico", description="Menciones literales de cada lugar (y sus variantes) en titular, subtítulo, cuerpo y pies de foto.")
            if ok:
                s44.table("Matriz de representación espacial", [
                    {"key": "nombre", "label": "Lugar"}, {"key": "c1", "label": "Centralidad N1"}, {"key": "c2", "label": "Centralidad N2"},
                    {"key": "presencia", "label": "Presencia", "type": "presencia"}, {"key": "roles", "label": "Función"}],
                    [{"nombre": p["nombre"], "c1": S(p.get("centralidad_n1"), "—"), "c2": S(p.get("centralidad_n2"), "—"),
                      "presencia": p["_origin"], "roles": ", ".join(S(r) for r in L(p.get("roles")))} for p in places], origin="mixto")
            s44.add("territory", "Espacios que construye cada noticia", split=True, nodes=nodes, routes=[], mode="escalas", origin="mixto" if ok else "heuristico",
                    description="Vistas individuales: lugares mencionados por cada noticia, ordenados por escala territorial.")

        synthesis, origin = synth_from(out)
        if not synthesis:
            synthesis = heuristic_synthesis(
                [f"Lugares compartidos: {sum(1 for p in places if p['_origin'] == 'shared')}; exclusivos N1: {sum(1 for p in places if p['_origin'] == 'n1')}; "
                 f"exclusivos N2: {sum(1 for p in places if p['_origin'] == 'n2')}."], [],
                ["Sin modelo, los lugares se detectan por mayúsculas y nomenclátor, sin función ni precisión textual."])
            origin = "programatico"
        for p in places:
            p.pop("_c", None)
        return list(sec.values()), synthesis, origin, verif_merge(out)


PHASE = Fase4()
