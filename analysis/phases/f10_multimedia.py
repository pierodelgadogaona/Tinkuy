"""Fase 10. Análisis visual, multimedia e intertextual."""
from __future__ import annotations

import io
import re
from collections import Counter
from urllib.parse import urlsplit

from ...config import settings
from ...extraction.fetcher import fetch
from ...llm.prompts import EVIDENCES, SYNTHESIS, s_arr, s_enum, s_obj, s_str
from ..base import Context, Phase, heuristic_synthesis, verif_merge
from ..helpers import D, L, S, ev_cell, synth_from

KIND_LABELS = {"figure": "Fotografías e imágenes", "video": "Vídeos", "red_social": "Publicaciones de redes sociales",
               "grafico": "Gráficos o infografías", "mapa": "Mapas", "audio": "Audios", "documento": "Documentos", "tabla": "Tablas",
               "insercion": "Otras inserciones"}
IMG = s_obj({"protagonistas": s_str(), "escenario": s_str(), "encuadre": s_str("Plano y encuadre"), "composicion": s_str(), "perspectiva": s_str(),
             "iluminacion": s_str(), "colores": s_str(), "relacion_titular": s_str(), "relacion_texto": s_str(),
             "funcion_narrativa": s_str(), "funcion_informativa": s_str(), "funcion_emocional": s_str(),
             "basado_en": s_enum(["imagen", "pie_de_foto", "metadatos"], "Fuente de tu descripción"),
             "advertencias": s_str("Limitaciones: p. ej. imagen no disponible, de archivo o de marcador de posición")},
            ["protagonistas", "escenario", "funcion_narrativa", "basado_en"])
SCHEMA = s_obj({
    "imagen_principal_n1": IMG, "imagen_principal_n2": IMG,
    "secundarias": s_arr(s_obj({"ref": s_str("N1-F2..."), "contenido": s_str(), "protagonistas": s_str(), "escenario": s_str(),
                                "funcion": s_str(), "relacion_texto": s_str(), "basado_en": s_enum(["imagen", "pie_de_foto", "metadatos"])},
                               ["ref", "contenido", "funcion", "basado_en"])),
    "otros": s_arr(s_obj({"ref": s_str("N2-M1..."), "descripcion": s_str(), "funcion": s_str()}, ["ref", "descripcion", "funcion"])),
    "intertextualidad": s_arr(s_obj({"n": {"type": "integer", "enum": [1, 2]}, "p": s_str(), "cita": s_str(), "referencia": s_str("A qué se remite"),
                                     "tipo": s_enum(["medio", "agencia", "comunicado", "documento", "red_social", "enlace", "fuente_externa", "otro"]),
                                     "emisor": s_str("Quién emite el material referido")},
                                    ["n", "p", "cita", "referencia", "tipo", "emisor"])),
    "sintesis": SYNTHESIS,
}, ["imagen_principal_n1", "imagen_principal_n2", "secundarias", "otros", "intertextualidad", "sintesis"])
INSTRUCTIONS = """Fase 10 — Análisis visual, multimedia e intertextual.
Se te entrega el inventario multimedia extraído (imágenes con pie, crédito y dimensiones; vídeos; inserciones; enlaces)
y, cuando fue posible descargarlas, las propias imágenes.
1) Analiza la imagen principal de cada noticia: protagonistas, escenario, encuadre, composición, perspectiva,
   iluminación, colores, relación con el titular y el texto, y funciones narrativa, informativa y emocional.
   Indica si tu descripción se basa en la imagen o solo en el pie de foto. No atribuyas emociones internas a las
   personas por su apariencia. Si la imagen es un marcador de posición o no está disponible, dilo.
2) Describe brevemente las imágenes secundarias y otros recursos multimedia y su función.
3) Identifica referencias intertextuales: otros medios, agencias, comunicados, documentos, redes sociales y
   materiales de terceros, con su emisor. Elabora la síntesis."""


def _image_info(src: str) -> dict:
    """Descarga segura de una imagen para medirla (y opcionalmente enviarla al modelo)."""
    if not src or src.startswith("data:"):
        return {"ok": False, "motivo": "Sin URL"}
    r = fetch(src, accept="image/avif,image/webp,image/jpeg,image/png,image/*;q=0.8", max_bytes=settings.max_image_bytes, timeout=15)
    if not r.ok:
        return {"ok": False, "motivo": r.error}
    ctype = (r.content_type or "").split(";")[0].strip().lower()
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(r.body))
        w, h = im.size
        im = im.convert("RGB")
        im.thumbnail((1024, 1024))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=80)
        return {"ok": True, "width": w, "height": h, "formato": (ctype or "image").replace("image/", ""), "bytes": len(r.body),
                "jpeg": buf.getvalue()}
    except Exception as e:
        return {"ok": False, "motivo": f"No se pudo interpretar la imagen ({type(e).__name__})."}


class Fase10(Phase):
    number = 10
    title = "Análisis visual, multimedia e intertextual"
    description = "Qué recursos visuales acompañan cada texto, qué función cumplen y con qué otras fuentes dialogan."
    sections = [("10.1", "Inventario multimedia", "¿Qué recursos multimedia incluye cada noticia?"),
                ("10.2", "Imagen principal", "¿Qué muestra y qué función cumple la imagen principal?"),
                ("10.3", "Imágenes secundarias", "¿Qué aportan las imágenes secundarias?"),
                ("10.4", "Otros recursos multimedia", "¿Qué vídeos, gráficos o inserciones se incluyen?"),
                ("10.5", "Intertextualidad y circulación de información", "¿Con qué otros textos, medios y fuentes dialoga cada noticia?")]

    def analyze(self, ctx: Context):
        sec = self.make_sections(self.sections)
        media = {n: [b for b in ctx.articles[n - 1]["blocks"] if b["type"] not in ("paragraph", "heading")] for n in (1, 2)}
        figs = {n: [b for b in media[n] if b["type"] == "figure"] for n in (1, 2)}
        vision = ctx.options.get("vision", settings.vision_enabled)
        infos, images = {}, []
        for n in (1, 2):
            for f in figs[n][:5]:
                info = _image_info(f.get("src", ""))
                infos[(n, f["id"])] = info
                if vision and info.get("ok") and len(images) < 6 and (f.get("principal") or len([i for i in images if i["label"].startswith(f"N{n}")]) < 2):
                    images.append({"media_type": "image/jpeg", "data": info["jpeg"], "label": f"N{n}-{f['id']} ({'principal' if f.get('principal') else 'secundaria'})"})
        inv_lines = []
        for n in (1, 2):
            for b in media[n]:
                info = infos.get((n, b["id"]), {})
                dims = f"{info['width']}×{info['height']} px" if info.get("ok") else (f"{b.get('width')}×{b.get('height')} px (declarado)" if b.get("width") else "dimensiones no disponibles")
                inv_lines.append(f"N{n}-{b['id']} ({b['type']}{', principal' if b.get('principal') else ''}) pie: {b.get('caption') or '—'} | crédito: {b.get('credit') or '—'} | {dims} | "
                                 f"{b.get('provider') or ''} {b.get('title') or ''} | ubicación: {b.get('ubicacion') or ('tras ' + str(b.get('despues_de')) if b.get('despues_de') else 'antes del cuerpo')}")
        links = {n: [(l, b["id"]) for b in ctx.articles[n - 1]["blocks"] if b["type"] == "paragraph" for l in b.get("links", [])] for n in (1, 2)}
        for n in (1, 2):
            for l, pid in links[n]:
                inv_lines.append(f"Enlace N{n} [{pid}]: «{l.get('text')}» → {l.get('href')}")
        out = ctx.ask("fase10", INSTRUCTIONS, SCHEMA, extra="INVENTARIO MULTIMEDIA Y ENLACES\n" + ("\n".join(inv_lines) or "(sin recursos)"),
                      images=images or None, description="Registra la fase 10.", max_tokens=9000)
        ok = out is not None and "__error__" not in out

        # 10.1 inventario
        s = sec["10.1"]
        cnt = {n: Counter(b["type"] for b in media[n]) for n in (1, 2)}
        kinds = [k for k in KIND_LABELS if cnt[1][k] or cnt[2][k]]
        rows = []
        for n in (1, 2):
            for b in media[n]:
                info = infos.get((n, b["id"]), {})
                rows.append({"n": n, "id": b["id"], "tipo": KIND_LABELS.get(b["type"], b["type"]) + (" · principal" if b.get("principal") else ""),
                             "desc": b.get("caption") or b.get("title") or b.get("provider") or "—", "cred": b.get("credit") or "No consta",
                             "dims": f"{info['width']}×{info['height']}" if info.get("ok") else (f"{b.get('width')}×{b.get('height')} (declarado)" if b.get("width") else "—"),
                             "pos": b.get("ubicacion") or (f"tras {b['despues_de']}" if b.get("despues_de") else "antes del cuerpo"),
                             "src": {"link": b.get("src")} if b.get("src") else "—"})
        if rows:
            s.table("Inventario multimedia", [{"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "id", "label": "Ref."},
                                              {"key": "tipo", "label": "Tipo"}, {"key": "desc", "label": "Pie o descripción"},
                                              {"key": "cred", "label": "Crédito"}, {"key": "dims", "label": "Dimensiones (px)"},
                                              {"key": "pos", "label": "Ubicación"}, {"key": "src", "label": "Recurso"}], rows, origin="programatico",
                    description="Recursos extraídos de la página. Las dimensiones se miden descargando la imagen (o se toman de los atributos HTML).")
            s.add("bars", "Recursos multimedia por tipo", categories=[KIND_LABELS[k] for k in kinds],
                  series=[{"key": f"n{n}", "name": ctx.label(n), "values": [cnt[n][k] for k in kinds]} for n in (1, 2)], unit="recursos", origin="programatico")
        else:
            s.set_status("no_disponible", "Ninguna de las noticias incluye recursos multimedia extraíbles.")
            s.notice("no_disponible", "Ninguna de las noticias incluye recursos multimedia extraíbles.")

        # 10.2 principal
        s = sec["10.2"]
        mains = {n: next((b for b in figs[n] if b.get("principal")), None) for n in (1, 2)}
        if not mains[1] and not mains[2]:
            s.set_status("no_disponible", "Ninguna noticia tiene imagen principal.")
            s.notice("no_disponible", "Ninguna noticia tiene imagen principal identificable.")
        else:
            cards = []
            for n in (1, 2):
                b = mains[n]
                if not b:
                    cards.append({"n": n, "title": ctx.label(n), "empty": "Información no disponible: la noticia no tiene imagen principal.", "fields": []})
                    continue
                info = infos.get((n, b["id"]), {})
                fields = [{"label": "Pie de foto", "value": b.get("caption") or "No consta"},
                          {"label": "Autoría / crédito", "value": b.get("credit") or "No consta"},
                          {"label": "Procedencia", "value": urlsplit(b.get("src", "")).netloc or "—"},
                          {"label": "Ubicación", "value": b.get("ubicacion") or "en el cuerpo"},
                          {"label": "Dimensiones", "value": f"{info['width']} × {info['height']} px" if info.get("ok") else (f"{b.get('width')} × {b.get('height')} px (declarado)" if b.get("width") else "No disponibles")}]
                if ok:
                    x = D(out.get(f"imagen_principal_n{n}"))
                    for k, lbl in (("protagonistas", "Protagonistas"), ("escenario", "Escenario"), ("encuadre", "Encuadre"), ("composicion", "Composición"),
                                   ("perspectiva", "Perspectiva"), ("iluminacion", "Iluminación"), ("colores", "Colores"), ("relacion_titular", "Relación con el titular"),
                                   ("relacion_texto", "Relación con el texto"), ("funcion_narrativa", "Función narrativa"), ("funcion_informativa", "Función informativa"),
                                   ("funcion_emocional", "Función emocional")):
                        if x.get(k):
                            fields.append({"label": lbl, "value": S(x.get(k)), "origin": "modelo"})
                    basis = {"imagen": "la propia imagen", "pie_de_foto": "el pie de foto (imagen no analizada)", "metadatos": "los metadatos"}.get(S(x.get("basado_en")), S(x.get("basado_en")))
                    fields.append({"label": "Descripción basada en", "value": basis, "origin": "modelo"})
                    if x.get("advertencias"):
                        fields.append({"label": "Advertencias", "value": S(x.get("advertencias")), "origin": "modelo"})
                cards.append({"n": n, "title": ctx.label(n), "image": b.get("src"), "fields": fields,
                              "image_note": "" if info.get("ok") else f"Imagen no descargable: {info.get('motivo', '')}"})
            s.add("cards", "Fichas visuales de las imágenes principales", items=cards, layout="images", origin="mixto" if ok else "programatico",
                  description=("Metadatos extraídos por código; la lectura visual la realiza el modelo" + (" con la imagen." if images else " a partir del pie de foto (análisis de imagen no disponible).")) if ok
                  else "Metadatos extraídos por código (pie, crédito, procedencia, ubicación y dimensiones medidas).")
            if not ok:
                self.no_llm(s, "La lectura visual (encuadre, composición, funciones)")

        # 10.3 secundarias
        s = sec["10.3"]
        sec_imgs = {n: [b for b in figs[n] if not b.get("principal")] for n in (1, 2)}
        if not sec_imgs[1] and not sec_imgs[2]:
            s.set_status("no_disponible", "No hay imágenes secundarias.")
            s.notice("no_disponible", "Ninguna noticia incluye imágenes secundarias.")
        else:
            desc = {S(x.get("ref")).upper(): x for x in L(out.get("secundarias"))} if ok else {}
            items = []
            for n in (1, 2):
                for b in sec_imgs[n]:
                    x = desc.get(f"N{n}-{b['id']}".upper(), {})
                    items.append({"n": n, "src": b.get("src"), "caption": b.get("caption") or "Sin pie de foto", "credit": b.get("credit") or "No consta",
                                  "ficha": [{"label": "Contenido", "value": S(x.get("contenido"))}, {"label": "Función", "value": S(x.get("funcion"))},
                                            {"label": "Relación con el texto", "value": S(x.get("relacion_texto"))},
                                            {"label": "Basado en", "value": S(x.get("basado_en"))}] if x else []})
            s.add("gallery", "Galería comparativa", items=items, origin="mixto" if ok else "programatico",
                  description="Imágenes secundarias de cada noticia con su pie, crédito y función.")

        # 10.4 otros
        s = sec["10.4"]
        others = {n: [b for b in media[n] if b["type"] != "figure"] for n in (1, 2)}
        if not others[1] and not others[2]:
            s.set_status("no_disponible", "No hay otros recursos multimedia.")
            s.notice("no_disponible", "Ninguna noticia incluye vídeos, gráficos, mapas ni publicaciones insertadas.")
        else:
            desc = {S(x.get("ref")).upper(): x for x in L(out.get("otros"))} if ok else {}
            rows = []
            for n in (1, 2):
                for b in others[n]:
                    x = desc.get(f"N{n}-{b['id']}".upper(), {})
                    rows.append({"n": n, "tipo": KIND_LABELS.get(b["type"], b["type"]), "prov": b.get("provider") or "—",
                                 "tit": b.get("title") or b.get("caption") or "—", "desc": S(x.get("descripcion"), "—"), "fun": S(x.get("funcion"), "—"),
                                 "src": {"link": b.get("src")} if b.get("src") else "—"})
            s.table("Inventario descriptivo", [{"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "tipo", "label": "Tipo"},
                                               {"key": "prov", "label": "Plataforma"}, {"key": "tit", "label": "Título"},
                                               {"key": "desc", "label": "Descripción"}, {"key": "fun", "label": "Función"}, {"key": "src", "label": "Enlace"}],
                    rows, origin="mixto" if ok else "programatico",
                    description="El contenido de vídeos y publicaciones insertadas no se reproduce ni se analiza: solo sus metadatos.")

        # 10.5 intertextualidad
        s = sec["10.5"]
        rows, nodes, edges, seen = [], [{"id": "N1", "label": ctx.label(1), "type": "noticia", "origin": "n1"},
                                         {"id": "N2", "label": ctx.label(2), "type": "noticia", "origin": "n2"}], [], {}

        def node(label, kind):
            k = label.lower().strip()
            if k not in seen:
                seen[k] = f"X{len(seen) + 1}"
                nodes.append({"id": seen[k], "label": label, "type": kind, "origin": "shared"})
            return seen[k]
        for n in (1, 2):
            own = urlsplit(ctx.articles[n - 1].get("final_url") or ctx.articles[n - 1].get("url") or "").netloc.replace("www.", "")
            for l, pid in links[n]:
                dom = urlsplit(l.get("href", "")).netloc.replace("www.", "")
                internal = bool(own) and dom.endswith(own)
                rows.append({"n": n, "p": pid, "ref": l.get("text") or l.get("href"), "tipo": "Enlace interno" if internal else "Enlace externo",
                             "emisor": dom or "—", "src": {"link": l.get("href")}, "origen": "programatico"})
                if not internal and dom:
                    edges.append({"source": f"N{n}", "target": node(dom, "dominio"), "label": "enlaza", "origin": f"n{n}"})
            for a in ctx.f[n]["lexico"]["agencias"]:
                rows.append({"n": n, "p": a["p"], "ref": a["agencia"], "tipo": "Agencia", "emisor": a["agencia"], "src": "—", "origen": "programatico"})
                edges.append({"source": node(a["agencia"], "agencia"), "target": f"N{n}", "label": "aporta información", "origin": f"n{n}"})
            for b in others[n]:
                if b["type"] == "red_social":
                    rows.append({"n": n, "p": b["id"], "ref": b.get("title") or b.get("src"), "tipo": "Publicación insertada", "emisor": b.get("provider"),
                                 "src": {"link": b.get("src")} if b.get("src") else "—", "origen": "programatico"})
                    edges.append({"source": node(b.get("provider") or "Red social", "red_social"), "target": f"N{n}", "label": "insertada", "origin": f"n{n}"})
        if ok:
            for x in L(out.get("intertextualidad")):
                if not isinstance(x, dict):
                    continue
                n = x.get("n") if x.get("n") in (1, 2) else 1
                rows.append({"n": n, "p": S(x.get("p")), "ref": S(x.get("referencia")), "tipo": S(x.get("tipo")).replace("_", " ").capitalize(),
                             "emisor": S(x.get("emisor"), "—"), "src": ev_cell([x]), "origen": "modelo"})
                if x.get("emisor"):
                    edges.append({"source": node(S(x.get("emisor")), S(x.get("tipo"))), "target": f"N{n}", "label": S(x.get("tipo")).replace("_", " "),
                                  "origin": f"n{n}", "ev": [x]})
        # nodos compartidos: emisores citados por ambas
        for nd in nodes:
            if nd["type"] != "noticia":
                ns = {e["target"] if e["source"] == nd["id"] else e["source"] for e in edges if nd["id"] in (e["source"], e["target"])}
                nd["origin"] = "shared" if {"N1", "N2"} <= ns else ("n1" if "N1" in ns else "n2")
        if rows:
            s.table("Tabla de referencias", [{"key": "n", "label": "Noticia", "type": "noticia"}, {"key": "p", "label": "Unidad", "type": "ref"},
                                             {"key": "ref", "label": "Referencia"}, {"key": "tipo", "label": "Tipo"}, {"key": "emisor", "label": "Emisor"},
                                             {"key": "src", "label": "Enlace o evidencia"}], rows, origin="mixto" if ok else "programatico")
            if len(nodes) > 2:
                s.add("graph", "Grafo de circulación de la información", nodes=nodes, edges=edges, directed=True, origin="mixto" if ok else "programatico",
                      description="Cómo llega la información a cada noticia: enlaces, agencias, comunicados, documentos y publicaciones insertadas.")
        else:
            s.set_status("no_disponible", "No se identificaron referencias externas.")
            s.notice("no_disponible", "No se identificaron enlaces ni referencias a otros medios, agencias o documentos.")

        synthesis, origin = synth_from(out)
        if not synthesis:
            synthesis = heuristic_synthesis([f"Recursos multimedia: {len(media[1])} en N1 y {len(media[2])} en N2."], [],
                                            ["Sin modelo no se analizan las imágenes ni las funciones de los recursos."])
            origin = "programatico"
        return list(sec.values()), synthesis, origin, verif_merge(out)


PHASE = Fase10()
