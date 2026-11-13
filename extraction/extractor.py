"""Orquestador de la lectura de noticias.

Estrategias (en orden):
1. Descarga directa + extracción del cuerpo en el DOM.
2. Metadatos estructurados: Arc XP (``Fusion.globalContent``) y ``articleBody`` de JSON-LD.
3. Navegador automatizado si el contenido es insuficiente, dinámico o bloqueado.
4. Si todo falla, se informa exactamente qué sucedió y se ofrece introducir el texto.

Nunca se completa un artículo con información inventada: el estado de lectura
se calcula a partir de lo realmente recuperado.
"""
from __future__ import annotations

import copy
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit

from dateutil import parser as dateparser

from ..config import settings
from ..security.urlguard import UrlRejected, check_url
from . import browser
from .fetcher import fetch
from .html_extract import (DATE_TEXT, dom_metadata, extract_dom, page_signals, parse_html, section_from_url)
from .structured import clean_text, parse_arc, parse_jsonld, parse_meta
from .. import branding

MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
          "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}

STATUS_LABELS = {
    "completa": "Leída correctamente",
    "parcial": "Leída parcialmente",
    "suscripcion": "Requiere suscripción",
    "inaccesible": "Página inaccesible",
    "no_existe": "La página no existe",
    "insuficiente": "Contenido insuficiente para el análisis",
    "error": "Error de extracción",
    "invalida": "Enlace no válido",
    "manual": "Texto introducido manualmente",
}
MIN_WORDS_COMPLETE = 150
MIN_WORDS_ANALYSIS = 60


def _words(s: str) -> int:
    return len(re.findall(r"\w+", s or ""))


def parse_date(value) -> str | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000 if value > 1e11 else value).isoformat(timespec="minutes")
        except Exception:
            return None
    s = str(value).strip()
    try:
        d = dateparser.isoparse(s)
        if d.tzinfo is not None and d.utcoffset() == timedelta(0):
            # Muchas plataformas publican en UTC: se expresa en la zona horaria de trabajo (TINKUY_TZ)
            try:
                d = d.astimezone(ZoneInfo(settings.timezone))
            except Exception:
                pass
        return d.isoformat(timespec="minutes")
    except Exception:
        pass
    m = DATE_TEXT.search(s)
    if m:
        day, month, year, hh, mm = m.groups()
        try:
            d = datetime(int(year) if year else datetime.now().year, MONTHS[month.lower()], int(day),
                         int(hh) if hh else 0, int(mm) if mm else 0)
            return d.isoformat(timespec="minutes")
        except Exception:
            return None
    try:
        return dateparser.parse(s, dayfirst=True).isoformat(timespec="minutes")
    except Exception:
        return None


def _similar(a: str, b: str) -> float:
    wa, wb = set(re.findall(r"\w{3,}", a.lower())), set(re.findall(r"\w{3,}", b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _split_body(text: str) -> tuple[list[str], bool]:
    """Divide un ``articleBody`` en párrafos. Devuelve (párrafos, división_aproximada)."""
    text = (text or "").replace("\r", "")
    parts = [clean_text(p) for p in re.split(r"\n\s*\n|\n", text) if clean_text(p)]
    if len(parts) >= 3:
        return parts, False
    sents = re.split(r"(?<=[.!?»”])\s+(?=[A-ZÁÉÍÓÚÑ¿¡«“])", clean_text(text))
    chunks, cur = [], []
    for s in sents:
        cur.append(s)
        if _words(" ".join(cur)) >= 70:
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    return chunks, True


def _same_image(a: str, b: str) -> bool:
    def stem(u):
        p = urlsplit(u or "").path.rsplit("/", 1)[-1].lower()
        p = re.sub(r"[-_]\d{2,4}x\d{2,4}", "", p)
        return re.sub(r"\.(jpe?g|png|webp|gif|avif)$", "", p)
    return bool(a and b) and stem(a) == stem(b) and len(stem(a)) > 3


def analyze_html(html: str, base_url: str) -> dict:
    doc = parse_html(html, base_url)
    signals = page_signals(doc)
    jsonld = parse_jsonld(doc, base_url)
    metas = parse_meta(doc)
    arc = parse_arc(html, base_url)
    domm = dom_metadata(doc, base_url)
    dom = extract_dom(doc, base_url)

    candidates = [("dom", dom["words"], dom["blocks"], "")]
    if arc.get("blocks"):
        aw = sum(_words(b["text"]) for b in arc["blocks"] if b["type"] == "paragraph")
        candidates.append(("arc", aw, arc["blocks"], ""))
    if jsonld.get("body"):
        paras, approx = _split_body(jsonld["body"])
        jw = sum(_words(p) for p in paras)
        note = ("El cuerpo procede del campo articleBody (JSON-LD); la división en párrafos es aproximada."
                if approx else "El cuerpo procede del campo articleBody (JSON-LD).")
        candidates.append(("jsonld", jw, [{"type": "paragraph", "text": p, "links": []} for p in paras], note))
    best = max(candidates, key=lambda c: c[1])
    chosen = best
    if dom["words"] >= 0.8 * best[1] and dom["words"] > 0:
        chosen = candidates[0]
    method, words, blocks, note = chosen
    if method == "jsonld":
        # conserva las figuras localizadas en el DOM (al final, posición desconocida)
        figs = [b for b in dom["blocks"] if b["type"] != "paragraph" and b["type"] != "heading"]
        for f in figs:
            f["posicion_aproximada"] = True
        blocks = blocks + figs

    m = metas["meta"]
    sources: dict[str, str] = {}

    def pick(field, options):
        for label, val in options:
            if val:
                sources[field] = label
                return val
        return None

    struct_head = arc.get("headline") or jsonld.get("headline") or m.get("og:title") or m.get("twitter:title")
    dom_head = domm.get("headline")
    if dom_head and (not struct_head or _similar(dom_head, struct_head) >= 0.5 or _words(dom_head) >= 6):
        headline = dom_head
        sources["titular"] = "DOM (h1)"
    else:
        headline = pick("titular", [("Arc XP", arc.get("headline")), ("JSON-LD", jsonld.get("headline")),
                                    ("og:title", m.get("og:title")), ("título de la página", metas["title"])])
    subtitle = pick("subtitulo", [("Arc XP", arc.get("subheadline")), ("DOM", domm.get("subtitle")),
                                  ("JSON-LD", jsonld.get("description")), ("Arc XP", arc.get("description")),
                                  ("og:description", m.get("og:description")), ("description", m.get("description"))])
    if subtitle and headline and _similar(subtitle, headline) > 0.9:
        subtitle = None
    medium = pick("medio", [("og:site_name", m.get("og:site_name")), ("JSON-LD", jsonld.get("publisher")),
                            ("application-name", m.get("application-name"))])
    if not medium:
        medium = urlsplit(base_url).netloc.replace("www.", "")
        sources["medio"] = "dominio"

    time_pub = next((t["datetime"] for t in metas["times"] if "published" in t["itemprop"] or "pub" in t["cls"]), None)
    time_any = metas["times"][0]["datetime"] if metas["times"] else None
    pub_raw = pick("fecha_publicacion", [
        ("JSON-LD", jsonld.get("date_published")), ("Arc XP", arc.get("date_published")),
        ("article:published_time", m.get("article:published_time")), ("datePublished", m.get("datepublished")),
        ("pubdate", m.get("pubdate") or m.get("date") or m.get("parsely-pub-date") or m.get("dc.date")),
        ("<time>", time_pub or time_any), ("texto de la página", domm.get("date_text"))])
    mod_raw = pick("fecha_actualizacion", [
        ("JSON-LD", jsonld.get("date_modified")), ("Arc XP", arc.get("date_modified")),
        ("article:modified_time", m.get("article:modified_time")), ("dateModified", m.get("datemodified")),
        ("og:updated_time", m.get("og:updated_time")),
        ("<time>", next((t["datetime"] for t in metas["times"] if "modif" in t["itemprop"] or "updat" in t["cls"]), None))])
    authors = pick("autoria", [("Arc XP", arc.get("authors")), ("JSON-LD", jsonld.get("authors")),
                               ("DOM", domm.get("authors")),
                               ("metaetiqueta", [m["author"]] if m.get("author") and "http" not in m["author"] else None),
                               ("article:author", [m["article:author"]] if m.get("article:author") and "http" not in m.get("article:author", "") else None)]) or []
    section = pick("seccion", [("JSON-LD", jsonld.get("section")), ("Arc XP", arc.get("section")),
                               ("article:section", m.get("article:section")), ("migas de pan", domm.get("section"))])
    if not section:
        s = section_from_url(base_url)
        if s:
            section = s
            sources["seccion"] = "inferida de la URL"

    main_image = arc.get("main_image")
    if main_image:
        sources["imagen_principal"] = "Arc XP"
    elif jsonld.get("images"):
        main_image = jsonld["images"][0]
        sources["imagen_principal"] = "JSON-LD"
    elif m.get("og:image"):
        main_image = {"src": m["og:image"], "width": m.get("og:image:width"), "height": m.get("og:image:height"),
                      "caption": "", "credit": "", "alt": m.get("og:image:alt", "")}
        sources["imagen_principal"] = "og:image"
    if main_image and not main_image.get("caption"):
        # la imagen de cabecera suele estar fuera del cuerpo: se busca su <figure> en la página
        from .html_extract import BlockBuilder
        for fig in doc.xpath("//figure"):
            img = fig.find(".//img")
            if img is None:
                continue
            bb = BlockBuilder(base_url)
            bb.figure(copy.deepcopy(fig))
            if bb.blocks and _same_image(bb.blocks[0].get("src"), main_image.get("src")):
                for k in ("caption", "credit", "alt", "width", "height"):
                    if bb.blocks[0].get(k) and not main_image.get(k):
                        main_image[k] = bb.blocks[0][k]
                break

    return {
        "method": method, "note": note, "words": words, "blocks": blocks, "signals": signals,
        "meta": {
            "medio": medium, "titular": headline or "", "subtitulo": subtitle or "",
            "fecha_publicacion": parse_date(pub_raw), "fecha_publicacion_original": str(pub_raw or ""),
            "fecha_actualizacion": parse_date(mod_raw), "autoria": authors, "seccion": section or "",
            "idioma": jsonld.get("language") or metas.get("lang") or "", "url_canonica": metas.get("canonical") or "",
            "tipo_schema": jsonld.get("type") or "", "acceso_libre": jsonld.get("free"),
            "palabras_clave": jsonld.get("keywords") if isinstance(jsonld.get("keywords"), str) else
            ", ".join(jsonld.get("keywords") or []) if isinstance(jsonld.get("keywords"), list) else "",
        },
        "sources": sources, "main_image": main_image,
        "brand_hints": branding.collect_hints(doc, base_url),
    }


def finalize_blocks(blocks: list[dict], main_image: dict | None) -> tuple[list[dict], dict | None]:
    out = []
    if main_image and main_image.get("src"):
        match = next((b for b in blocks if b["type"] == "figure" and _same_image(b.get("src"), main_image["src"])), None)
        if match is not None:
            match["principal"] = True
            for k in ("caption", "credit"):
                if not match.get(k) and main_image.get(k):
                    match[k] = main_image[k]
        else:
            blocks = [{"type": "figure", "principal": True, "ubicacion": "cabecera", **{k: main_image.get(k) for k in
                       ("src", "caption", "credit", "alt", "width", "height")}}] + blocks
    counters = {"P": 0, "H": 0, "F": 0, "M": 0}
    last_p = None
    for b in blocks:
        b.pop("_order", None)
        t = b["type"]
        prefix = {"paragraph": "P", "heading": "H", "figure": "F"}.get(t, "M")
        counters[prefix] += 1
        b["id"] = f"{prefix}{counters[prefix]}"
        if t == "paragraph":
            last_p = b["id"]
            b["palabras"] = _words(b["text"])
        else:
            b["despues_de"] = last_p
        out.append(b)
    main = next((b for b in out if b.get("principal")), None)
    return out, main


def _status(words: int, signals: dict, free) -> tuple[str, str]:
    paywalled = signals.get("paywall_text") or (free is False and words < 400)
    if words >= MIN_WORDS_COMPLETE and not paywalled:
        detail = "Contenido principal recuperado."
        if free is False:
            detail += " El medio declara el artículo como contenido de pago, pero el texto completo estaba disponible en la página."
        return "completa", detail
    if paywalled and words >= MIN_WORDS_ANALYSIS:
        return "parcial", ("Solo se ha recuperado una parte del texto: la página muestra un muro de suscripción. "
                           "Los análisis afectados se marcarán como incompletos.")
    if paywalled:
        return "suscripcion", ("El artículo está protegido por un muro de suscripción y no se ha podido leer su contenido. "
                               "Puedes pegar el texto completo si tienes acceso legítimo a él.")
    if words >= MIN_WORDS_ANALYSIS:
        return "parcial", (f"Se recuperaron {words} palabras; es posible que el artículo esté incompleto "
                           "(nota breve o extracción parcial).")
    return "insuficiente", (f"Solo se recuperaron {words} palabras de texto periodístico: no son suficientes para un análisis fiable.")


def extract_article(url: str, n: int) -> dict:
    article = {"n": n, "url": (url or "").strip(), "final_url": "", "attempts": [], "status": "error",
               "status_label": "", "status_detail": "", "method": "", "meta": {}, "meta_sources": {},
               "meta_edits": {}, "blocks": [], "main_image": None, "extracted_at": datetime.now().isoformat(timespec="seconds")}
    try:
        chk = check_url(url, allow_private=settings.allow_private_hosts, resolve=False)
        article["url"] = chk.url
    except UrlRejected as e:
        article.update(status="invalida", status_detail=e.message)
        article["status_label"] = STATUS_LABELS["invalida"]
        return article

    results = []
    fr = fetch(article["url"])
    article["final_url"] = fr.final_url or article["url"]
    if fr.ok:
        if "html" not in (fr.content_type or "html").lower() and "xml" not in (fr.content_type or "").lower():
            article["attempts"].append({"estrategia": "Descarga directa", "resultado": f"El enlace no es una página HTML ({fr.content_type})."})
        else:
            try:
                r = analyze_html(fr.text(), fr.final_url)
                r["via"] = "descarga directa"
                results.append(r)
                article["attempts"].append({"estrategia": "Descarga directa + extracción del contenido principal",
                                            "resultado": f"{r['words']} palabras recuperadas (método: {r['method']}).",
                                            "palabras": r["words"]})
            except Exception as e:
                article["attempts"].append({"estrategia": "Descarga directa", "resultado": f"Error al interpretar la página: {e}"})
    else:
        article["attempts"].append({"estrategia": "Descarga directa", "resultado": fr.error, "codigo": fr.error_code})
        if fr.error_code in ("dns", "destino", "esquema", "credenciales", "puerto", "invalida"):
            article.update(status="invalida", status_detail=fr.error, status_label=STATUS_LABELS["invalida"])
            return article
        if fr.error_code in ("http_404", "http_410"):
            article.update(status="no_existe", status_detail=fr.error, status_label=STATUS_LABELS["no_existe"])
            return article

    best = max(results, key=lambda r: r["words"]) if results else None
    needs_browser = (best is None or best["words"] < MIN_WORDS_COMPLETE or best["signals"]["challenge"]
                     or (best["signals"]["p_count"] < 3 and best["signals"]["script_count"] > 10))
    if needs_browser and not (best and best["signals"]["paywall_text"] and best["words"] >= MIN_WORDS_ANALYSIS):
        ok, why = browser.browser_available()
        if ok:
            br = browser.render(article["url"])
            if br.get("ok") and br.get("html"):
                try:
                    r = analyze_html(br["html"], br["final_url"])
                    r["via"] = "navegador"
                    results.append(r)
                    article["attempts"].append({"estrategia": "Navegador automatizado (páginas dinámicas)",
                                                "resultado": f"{r['words']} palabras recuperadas (método: {r['method']}).",
                                                "palabras": r["words"]})
                except Exception as e:
                    article["attempts"].append({"estrategia": "Navegador automatizado", "resultado": f"Error al interpretar la página: {e}"})
            else:
                article["attempts"].append({"estrategia": "Navegador automatizado", "resultado": br.get("error", "Sin respuesta.")})
        else:
            article["attempts"].append({"estrategia": "Navegador automatizado", "resultado": f"No disponible: {why}"})

    if not results:
        last = article["attempts"][-1]["resultado"] if article["attempts"] else "Sin respuesta."
        code = fr.error_code
        status = "inaccesible" if code.startswith("http_4") or code in ("tls", "red", "tiempo") else "error"
        if code == "http_402":
            status = "suscripcion"
        article.update(status=status, status_label=STATUS_LABELS[status],
                       status_detail=f"No se pudo recuperar el contenido. {fr.error or last}")
        return article

    best = max(results, key=lambda r: (not r["signals"]["challenge"], r["words"]))
    if best["signals"]["challenge"] and best["words"] < MIN_WORDS_ANALYSIS:
        article.update(status="inaccesible", status_label=STATUS_LABELS["inaccesible"],
                       status_detail="El medio muestra una verificación antibots; no se intenta superarla. "
                                     "Puedes pegar el texto del artículo manualmente.")
        article["meta"] = best["meta"]
        return article

    blocks, main = finalize_blocks(best["blocks"], best.get("main_image"))
    status, detail = _status(best["words"], best["signals"], best["meta"].get("acceso_libre"))
    if best.get("note"):
        detail += " " + best["note"]
    article.update(status=status, status_label=STATUS_LABELS[status], status_detail=detail,
                   method=f"{best['via']} · {best['method']}", meta=best["meta"], meta_sources=best["sources"],
                   blocks=blocks, main_image=main, brand_hints=best.get("brand_hints") or {})
    article["meta"]["url"] = article["url"]
    try:
        article["brand"] = branding.resolve(article)
    except Exception:  # el color es accesorio: nunca debe impedir la lectura
        pass
    return article


def manual_article(n: int, text: str, *, url: str = "", titular: str = "", medio: str = "", fecha: str = "",
                   autoria: str = "", seccion: str = "", subtitulo: str = "") -> dict:
    """Artículo introducido a mano. Las líneas que empiezan por «## » se tratan como subtítulos."""
    raw = (text or "").replace("\r", "")
    chunks = [c.strip() for c in re.split(r"\n\s*\n", raw) if c.strip()]
    if len(chunks) <= 1:
        chunks = [c.strip() for c in raw.split("\n") if c.strip()]
    blocks = []
    for c in chunks:
        if c.startswith("## "):
            blocks.append({"type": "heading", "text": clean_text(c[3:]), "level": 2})
        else:
            blocks.append({"type": "paragraph", "text": clean_text(c), "links": []})
    if not titular and blocks and blocks[0]["type"] == "paragraph" and _words(blocks[0]["text"]) <= 25 and len(blocks) > 1:
        titular = blocks.pop(0)["text"]
    blocks, main = finalize_blocks(blocks, None)
    words = sum(b.get("palabras", 0) for b in blocks)
    status = "manual" if words >= MIN_WORDS_ANALYSIS else "insuficiente"
    medio_val = medio or (urlsplit(url).netloc.replace("www.", "") if url else "")
    return {
        "n": n, "url": url, "final_url": url, "status": status, "status_label": STATUS_LABELS[status],
        "status_detail": ("Texto proporcionado por la persona usuaria; no se ha verificado contra la página original."
                          if status == "manual" else f"El texto introducido tiene {words} palabras: es insuficiente para el análisis."),
        "method": "texto manual", "attempts": [{"estrategia": "Texto introducido manualmente", "resultado": f"{words} palabras."}],
        "meta": {"medio": medio_val, "titular": titular, "subtitulo": subtitulo, "fecha_publicacion": parse_date(fecha) if fecha else None,
                 "fecha_publicacion_original": fecha, "fecha_actualizacion": None,
                 "autoria": [a.strip() for a in autoria.split(",") if a.strip()], "seccion": seccion, "url": url},
        "meta_sources": {k: "manual" for k in ("medio", "titular", "fecha_publicacion", "autoria", "seccion")},
        "meta_edits": {}, "blocks": blocks, "main_image": main,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
    }


ANALYZABLE = {"completa", "parcial", "manual"}


def is_analyzable(article: dict) -> bool:
    return article.get("status") in ANALYZABLE


def paragraphs(article: dict) -> list[dict]:
    return [b for b in article.get("blocks", []) if b["type"] == "paragraph"]
