"""Fase 6. Análisis de datos y evidencia cuantitativa."""
from __future__ import annotations

from collections import defaultdict

from ...llm.prompts import EVIDENCES, SYNTHESIS, s_arr, s_enum, s_num, s_obj, s_str
from ...nlp.text import stem
from ..base import Context, Phase, heuristic_synthesis, verif_merge
from ..helpers import D, L, S, ev_cell, one_ev, synth_from

QUANT_TYPES = ("cantidad", "porcentaje", "moneda", "medida", "duracion", "edad", "cantidad_indeterminada")
SCHEMA = s_obj({
    "datos": s_arr(s_obj({
        "ref": s_str("Identificador del dato detectado por el sistema, p. ej. N1-D3"),
        "es_dato": {"type": "boolean", "description": "false si no es un dato informativo (p. ej. «sus dos hijos» como detalle narrativo) o es un duplicado"},
        "variable": s_str("Qué mide (p. ej. «personas heridas»)"),
        "variable_id": s_str("Clave común para la MISMA variable en ambas noticias (p. ej. heridos)"),
        "valor": s_num("Valor numérico normalizado"), "unidad": s_str(), "periodo": s_str(),
        "fuente_atribuida": s_str("Quién aporta la cifra según el texto, o «no atribuida»"),
        "funcion": s_str("Función narrativa del dato")}, ["ref", "es_dato", "variable", "variable_id"])),
    "comparaciones": s_arr(s_obj({"variable_id": s_str(), "variable": s_str(),
                                  "relacion": s_enum(["coincide", "difiere", "exclusiva_n1", "exclusiva_n2", "no_comparable"]),
                                  "explicacion": s_str()}, ["variable_id", "variable", "relacion", "explicacion"])),
    "contextualizacion": s_arr(s_obj({"ref": s_str(), "procedencia": s_str(), "periodo": s_str(), "denominador": s_str(),
                                      "contexto": s_str(), "comparacion_previa": s_str()}, ["ref", "procedencia"])),
    "indicadores": s_arr(s_obj({"id": s_str("id del indicador específico"),
                                "n1": s_obj({"estado": s_enum(["presente", "ausente", "no_determinable"]), "valor": s_str(), "p": s_str(), "cita": s_str()}, ["estado"]),
                                "n2": s_obj({"estado": s_enum(["presente", "ausente", "no_determinable"]), "valor": s_str(), "p": s_str(), "cita": s_str()}, ["estado"])},
                               ["id", "n1", "n2"])),
    "sintesis": SYNTHESIS,
}, ["datos", "comparaciones", "indicadores", "sintesis"])
INSTRUCTIONS = """Fase 6 — Datos y evidencia cuantitativa.
Se te entrega el inventario de expresiones numéricas detectadas por el sistema (con identificadores N1-Dx y N2-Dx).
1) Clasifica cada dato: qué variable mide, unidad, periodo, fuente a la que se atribuye y función narrativa.
   Usa la MISMA variable_id para la misma magnitud en ambas noticias. Marca es_dato=false si no es informativo.
2) Compara las variables: coincidencias, diferencias, exclusivas y no comparables (distinta unidad, periodo o
   denominador). Explica las diferencias sin decidir cuál es la cifra correcta.
3) Contextualiza los datos relevantes (procedencia, periodo, denominador, contexto estadístico, comparación previa).
4) Para cada indicador específico del acontecimiento, indica si está presente, ausente o no determinable en cada
   noticia, con su valor y evidencia. No calcules porcentajes ni diferencias: lo hace el sistema. Elabora la síntesis."""


def _num_rows(ctx):
    rows = []
    for n in (1, 2):
        for d in ctx.f[n]["cifras"]:
            if d["tipo"] in QUANT_TYPES:
                rows.append({"ref": f"N{n}-{d['id']}", "n": n, **d})
    return rows


class Fase6(Phase):
    number = 6
    title = "Análisis de datos y evidencia cuantitativa"
    description = "Qué cifras aporta cada noticia, si coinciden y cómo las contextualiza."
    sections = [("6.1", "Inventario de datos cuantitativos", "¿Qué cifras ofrece cada noticia?"),
                ("6.2", "Comparación de cifras", "¿Coinciden las cifras sobre las mismas variables?"),
                ("6.3", "Contextualización de los datos", "¿De dónde proceden las cifras y cómo se contextualizan?"),
                ("6.4", "Visualización cuantitativa", "¿Cómo se comparan visualmente las cifras comparables?"),
                ("6.5", "Indicadores específicos del acontecimiento", "¿Qué informa cada noticia sobre los indicadores propios de este caso?")]

    def analyze(self, ctx: Context):
        sec = self.make_sections(self.sections)
        for sid in ("6.1", "6.2", "6.3", "6.4"):
            p = ctx.plan_status(sid)
            if p.get("estado") == "no_aplicable":
                sec[sid].set_status("no_aplicable", p.get("motivo", ""))
                sec[sid].notice("no_aplicable", p.get("motivo", ""))
        inv = _num_rows(ctx)
        indicators = ctx.profile.get("indicadores") or []
        listing = "\n".join(f"{r['ref']} [{r['p']}] «{r['texto']}» (tipo detectado: {r['tipo']}; valor: {r['valor']}) — contexto: {r['contexto'][:200]}"
                            for r in inv) or "(no se detectaron expresiones numéricas)"
        ind_txt = "\n".join(f"- {i['id']}: {i['nombre']} ({i.get('tipo', '')}{', ' + i['unidad'] if i.get('unidad') else ''})" for i in indicators) or "(ninguno)"
        out = None
        if inv or indicators:
            out = ctx.ask("fase6", INSTRUCTIONS, SCHEMA, extra=f"INVENTARIO NUMÉRICO DETECTADO POR EL SISTEMA\n{listing}\n\nINDICADORES ESPECÍFICOS\n{ind_txt}",
                          description="Registra la fase 6.", max_tokens=9000)
        ok = out is not None and "__error__" not in out
        cls = {S(d.get("ref")).upper(): d for d in L(out.get("datos"))} if ok else {}

        # 6.1 inventario
        s61 = sec["6.1"]
        if s61.status != "no_aplicable":
            rows = []
            for r in inv:
                c = cls.get(r["ref"].upper(), {})
                if ok and c and c.get("es_dato") is False:
                    continue
                rows.append({"ref": r["ref"], "n": r["n"], "p": r["p"], "texto": r["texto"], "tipo": r["tipo"].replace("_", " "),
                             "valor": r["valor"] if r["valor"] is not None else "—", "variable": S(c.get("variable"), "—" if ok else "Requiere modelo"),
                             "unidad": S(c.get("unidad")) or r["unidad"] or "—", "fuente": S(c.get("fuente_atribuida"), "—"),
                             "ev": one_ev(r["n"], r["p"], r["texto"].split(" ")[0] if r["texto"] else "")})
            s61.table("Tabla de datos cuantitativos", [
                {"key": "ref", "label": "Ref."}, {"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "p", "label": "Unidad", "type": "ref"},
                {"key": "texto", "label": "Expresión"}, {"key": "variable", "label": "Variable"}, {"key": "valor", "label": "Valor", "type": "num"},
                {"key": "unidad", "label": "Unidad de medida"}, {"key": "tipo", "label": "Tipo detectado"}, {"key": "fuente", "label": "Fuente atribuida"}],
                rows, origin="mixto" if ok else "heuristico",
                description="Las expresiones numéricas (en cifras y en letras) se detectan por código; el modelo identifica qué mide cada una y descarta las no informativas.")
            cnt = {n: sum(1 for r in rows if r["n"] == n) for n in (1, 2)}
            s61.add("bars", "Número de datos cuantitativos", categories=["Datos"], series=[
                {"key": "n1", "name": ctx.label(1), "values": [cnt[1]]}, {"key": "n2", "name": ctx.label(2), "values": [cnt[2]]}],
                unit="datos", origin="mixto" if ok else "heuristico")

        # 6.2 comparación
        s62 = sec["6.2"]
        groups = defaultdict(lambda: {1: [], 2: []})
        if ok:
            for r in inv:
                c = cls.get(r["ref"].upper())
                if c and c.get("es_dato") is not False and S(c.get("variable_id")):
                    v = c.get("valor") if isinstance(c.get("valor"), (int, float)) else r["valor"]
                    groups[S(c["variable_id"]).lower()][r["n"]].append({**r, "valor_n": v, "variable": S(c.get("variable")), "unidad_n": S(c.get("unidad")) or r["unidad"]})
        else:
            # Sin modelo: solo se agrupan cifras seguidas exactamente de la misma expresión (misma secuencia de raíces),
            # p. ej. «dos muertos» / «tres muertos». «46 pasajeros» y «21 pasajeros resultaron heridos» NO se emparejan.
            for r in inv:
                if r["tipo"] in ("cantidad", "porcentaje", "moneda") and r["unidad"]:
                    key = " ".join(stem(w) for w in r["unidad"].lower().split()[:3])
                    groups[key][r["n"]].append({**r, "valor_n": r["valor"], "variable": r["unidad"], "unidad_n": r["unidad"]})
        comp = {S(c.get("variable_id")).lower(): c for c in L(out.get("comparaciones"))} if ok else {}
        crow = []
        comparable = []
        for key, g in groups.items():
            v1 = [x["valor_n"] for x in g[1] if isinstance(x["valor_n"], (int, float))]
            v2 = [x["valor_n"] for x in g[2] if isinstance(x["valor_n"], (int, float))]
            c = comp.get(key, {})
            var = S(c.get("variable")) or (g[1] or g[2])[0]["variable"]
            if v1 and v2:
                a, b = max(v1), max(v2)
                diff = b - a
                relc = "coincide" if a == b else "difiere"
                diff_txt = "—" if a == b else f"{'+' if diff > 0 else ''}{round(diff, 2)} ({'+' if diff > 0 else ''}{round(100 * diff / a, 1) if a else '∞'} % respecto de N1)"
                u1, u2 = g[1][0]["unidad_n"], g[2][0]["unidad_n"]
                same_unit = stem((u1 or "x").split()[0].lower()) == stem((u2 or "x").split()[0].lower()) if ok else True
                if S(c.get("relacion")) == "no_comparable" or not same_unit:
                    relc = "no_comparable"
                elif relc in ("coincide", "difiere"):
                    comparable.append({"var": var, "a": a, "b": b, "unit": u1 or u2})
            else:
                a = max(v1) if v1 else None
                b = max(v2) if v2 else None
                relc, diff_txt = ("exclusiva_n1" if g[1] else "exclusiva_n2"), "—"
            crow.append({"var": var, "n1": " · ".join(x["texto"] for x in g[1]) or "Ausente", "n2": " · ".join(x["texto"] for x in g[2]) or "Ausente",
                         "rel": {"coincide": "Coincide", "difiere": "Difiere", "exclusiva_n1": "Solo en N1", "exclusiva_n2": "Solo en N2",
                                 "no_comparable": "No comparable"}[relc],
                         "dif": diff_txt, "exp": S(c.get("explicacion"), "—" if ok else "Agrupación heurística por la palabra que sigue a la cifra"),
                         "ev": ev_cell([{"n": x["n"], "p": x["p"], "cita": x["texto"].split(" ")[0], "verificacion": "literal"} for x in g[1] + g[2]])})
        if s62.status != "no_aplicable":
            if crow:
                s62.table("Comparación de cifras por variable", [
                    {"key": "var", "label": "Variable"}, {"key": "n1", "label": "Noticia 1"}, {"key": "n2", "label": "Noticia 2"},
                    {"key": "rel", "label": "Relación"}, {"key": "dif", "label": "Diferencia (N2 − N1)"}, {"key": "exp", "label": "Explicación"}],
                    crow, origin="mixto" if ok else "heuristico",
                    description="Las diferencias absolutas y relativas se calculan por código. Una diferencia no indica cuál cifra es correcta: "
                                "puede deberse a la fecha de publicación, a la fuente o al momento del recuento.")
            else:
                s62.set_status("insuficiente", "No hay variables cuantitativas que puedan emparejarse.")
                s62.notice("insuficiente", "No hay variables cuantitativas que puedan emparejarse entre las noticias.")

        # 6.3 contextualización
        s63 = sec["6.3"]
        if s63.status != "no_aplicable":
            if ok and L(out.get("contextualizacion")):
                s63.table("Matriz de contextualización", [
                    {"key": "ref", "label": "Ref."}, {"key": "texto", "label": "Dato"}, {"key": "proc", "label": "Procedencia"},
                    {"key": "per", "label": "Periodo"}, {"key": "den", "label": "Denominador"}, {"key": "ctx", "label": "Contexto estadístico"},
                    {"key": "prev", "label": "Comparación previa"}],
                    [{"ref": S(c.get("ref")), "texto": next((r["texto"] for r in inv if r["ref"].upper() == S(c.get("ref")).upper()), "—"),
                      "proc": S(c.get("procedencia"), "—"), "per": S(c.get("periodo"), "—"), "den": S(c.get("denominador"), "—"),
                      "ctx": S(c.get("contexto"), "—"), "prev": S(c.get("comparacion_previa"), "—")}
                     for c in L(out.get("contextualizacion")) if isinstance(c, dict)], origin="modelo")
            elif not self.llm_failed(s63, out, "La contextualización de los datos"):
                s63.notice("no_disponible", "El modelo no identificó datos que requieran contextualización adicional.")

        # 6.4 visualización
        s64 = sec["6.4"]
        if s64.status != "no_aplicable":
            if comparable:
                by_unit = defaultdict(list)
                for c in comparable:
                    by_unit[c["unit"]].append(c)
                for unit, items in by_unit.items():
                    s64.add("bars", f"Cifras comparables ({unit})", categories=[c["var"] for c in items], orientation="h",
                            series=[{"key": "n1", "name": ctx.label(1), "values": [c["a"] for c in items]},
                                    {"key": "n2", "name": ctx.label(2), "values": [c["b"] for c in items]}],
                            unit=unit, origin="mixto" if ok else "heuristico",
                            description="Barras agrupadas en un único eje que parte de cero; solo se incluyen variables con la misma unidad en ambas noticias.")
            else:
                s64.set_status("insuficiente", "No hay cifras comparables entre ambas noticias.")
                s64.notice("insuficiente", "No se construye ningún gráfico: las noticias no ofrecen cifras sobre la misma variable con la misma unidad. "
                                           "Forzar una comparación numérica distorsionaría los datos.")

        # 6.5 indicadores específicos
        s65 = sec["6.5"]
        if indicators:
            res = {S(i.get("id")): i for i in L(out.get("indicadores"))} if ok else {}
            rows = []
            lbl = {"presente": "Presente", "ausente": "Ausente", "no_determinable": "No determinable"}
            for i in indicators:
                r = res.get(i["id"], {})
                cells = {}
                for n in (1, 2):
                    x = D(r.get(f"n{n}"))
                    if not ok:
                        cells[n] = {"text": "Requiere modelo", "estado": ""}
                    else:
                        cells[n] = {"text": (S(x.get("valor")) or lbl.get(x.get("estado"), "—")), "estado": S(x.get("estado")),
                                    "ev": [x] if x.get("cita") else []}
                both_absent = ok and all(cells[n]["estado"] == "ausente" for n in (1, 2))
                rows.append({"ind": i["nombre"], "tipo": i.get("tipo", ""), "n1": cells[1], "n2": cells[2],
                             "comp": ("Ausente en ambas" if both_absent else
                                      "Presente solo en N1" if cells[1]["estado"] == "presente" and cells[2]["estado"] != "presente" else
                                      "Presente solo en N2" if cells[2]["estado"] == "presente" and cells[1]["estado"] != "presente" else
                                      "Presente en ambas" if cells[1]["estado"] == cells[2]["estado"] == "presente" else
                                      "No determinable" if ok else "—"),
                             "origen": "modelo" if i.get("origen") == "modelo" else "catálogo"})
            s65.table("Matriz de indicadores específicos", [
                {"key": "ind", "label": "Indicador"}, {"key": "tipo", "label": "Tipo"}, {"key": "n1", "label": "Noticia 1", "type": "estado_valor"},
                {"key": "n2", "label": "Noticia 2", "type": "estado_valor"}, {"key": "comp", "label": "Comparabilidad"}, {"key": "origen", "label": "Propuesto por"}],
                rows, origin="mixto" if ok else "heuristico",
                description="Indicadores adaptados a la naturaleza del acontecimiento. Se distingue entre ausente en ambas, presente en una sola y no determinable.")
        else:
            s65.set_status("no_aplicable", "No se definieron indicadores específicos para este acontecimiento.")
            s65.notice("no_aplicable", "No se definieron indicadores específicos para este acontecimiento.")

        synthesis, origin = synth_from(out)
        if not synthesis:
            synthesis = heuristic_synthesis([f"Datos detectados: {sum(1 for r in inv if r['n'] == 1)} en N1 y {sum(1 for r in inv if r['n'] == 2)} en N2."], [],
                                            ["Sin modelo, la correspondencia entre variables es una agrupación heurística."])
            origin = "programatico"
        return list(sec.values()), synthesis, origin, verif_merge(out)


PHASE = Fase6()
