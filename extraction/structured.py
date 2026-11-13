"""Metadatos estructurados: JSON-LD (schema.org), metaetiquetas y Arc XP (Fusion)."""
from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import urljoin, urlsplit

from lxml import html as lxml_html

ARTICLE_TYPES = {
    "newsarticle", "article", "reportagenewsarticle", "analysisnewsarticle", "blogposting",
    "opinionnewsarticle", "liveblogposting", "backgroundnewsarticle",
    "reviewnewsarticle", "socialmediaposting", "report", "techarticle", "scholarlyarticle",
}

WS = re.compile(r"[\s ​  ]+")


def clean_text(s: str | None) -> str:
    if not s:
        return ""
    s = unescape(str(s)).replace("­", "")
    return WS.sub(" ", s).strip()


def strip_tags(fragment: str) -> str:
    if not fragment:
        return ""
    try:
        node = lxml_html.fragment_fromstring(fragment, create_parent="div")
        return clean_text(node.text_content())
    except Exception:
        return clean_text(re.sub(r"<[^>]+>", " ", fragment))


# --------------------------------------------------------------------------- JSON-LD

def _iter_objects(data):
    if isinstance(data, list):
        for d in data:
            yield from _iter_objects(d)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _iter_objects(data["@graph"])
        for key in ("mainEntity", "mainEntityOfPage"):
            v = data.get(key)
            if isinstance(v, (dict, list)):
                yield from _iter_objects(v)


def _types(obj) -> set[str]:
    t = obj.get("@type")
    if isinstance(t, str):
        return {t.lower()}
    if isinstance(t, list):
        return {str(x).lower() for x in t}
    return set()


def _names(v) -> list[str]:
    out = []
    if isinstance(v, str):
        out.append(clean_text(v))
    elif isinstance(v, dict):
        n = v.get("name") or v.get("alternateName")
        if n:
            out.append(clean_text(n))
    elif isinstance(v, list):
        for x in v:
            out.extend(_names(x))
    return [x for x in out if x]


def _image_urls(v, base: str) -> list[dict]:
    out = []
    if isinstance(v, str):
        out.append({"src": urljoin(base, v)})
    elif isinstance(v, dict):
        u = v.get("url") or v.get("contentUrl") or v.get("@id")
        if u:
            out.append({
                "src": urljoin(base, str(u)),
                "width": v.get("width"), "height": v.get("height"),
                "caption": clean_text(v.get("caption") or v.get("description")),
                "credit": ", ".join(_names(v.get("author") or v.get("creator") or v.get("copyrightHolder"))),
            })
    elif isinstance(v, list):
        for x in v:
            out.extend(_image_urls(x, base))
    return out


def parse_jsonld(doc, base_url: str) -> dict:
    """Devuelve el objeto de tipo artículo más completo, normalizado."""
    best, best_score = None, -1
    for script in doc.xpath('//script[@type="application/ld+json" or @type="application/json+ld"]'):
        raw = (script.text or "").strip()
        if not raw:
            continue
        raw = re.sub(r"^\s*<!\[CDATA\[|\]\]>\s*$", "", raw)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            try:
                data = json.loads(re.sub(r",\s*([}\]])", r"\1", raw.replace("\n", " ")))
            except Exception:
                continue
        for obj in _iter_objects(data):
            if not (_types(obj) & ARTICLE_TYPES):
                continue
            score = sum(1 for k in ("headline", "datePublished", "author", "articleBody", "description") if obj.get(k))
            score += len(str(obj.get("articleBody") or "")) / 1000
            if score > best_score:
                best, best_score = obj, score
    if not best:
        return {}
    pub = best.get("publisher")
    free = best.get("isAccessibleForFree")
    if isinstance(free, str):
        free = free.strip().lower() not in {"false", "0", "no"}
    body = best.get("articleBody")
    if isinstance(body, list):
        body = "\n\n".join(str(b) for b in body)
    return {
        "headline": clean_text(best.get("headline") or best.get("name")),
        "alternative": clean_text(best.get("alternativeHeadline")),
        "description": clean_text(best.get("description")),
        "date_published": best.get("datePublished") or best.get("dateCreated"),
        "date_modified": best.get("dateModified"),
        "authors": _names(best.get("author") or best.get("creator")),
        "publisher": (_names(pub) or [""])[0],
        "section": clean_text(", ".join(best["articleSection"]) if isinstance(best.get("articleSection"), list)
                              else best.get("articleSection")),
        "images": _image_urls(best.get("image"), base_url),
        "body": body if isinstance(body, str) else "",
        "free": free,
        "language": best.get("inLanguage") if isinstance(best.get("inLanguage"), str) else "",
        "keywords": best.get("keywords") if isinstance(best.get("keywords"), (str, list)) else "",
        "type": sorted(_types(best))[0] if _types(best) else "",
        "url": best.get("url") if isinstance(best.get("url"), str) else "",
    }


# --------------------------------------------------------------------------- metaetiquetas

def parse_meta(doc) -> dict:
    meta: dict[str, str] = {}
    for m in doc.xpath("//meta"):
        key = (m.get("property") or m.get("name") or m.get("itemprop") or "").strip().lower()
        val = m.get("content")
        if key and val and key not in meta:
            meta[key] = clean_text(val)
    title = doc.xpath("string(//title)")
    canonical = doc.xpath('string(//link[@rel="canonical"]/@href)')
    times = []
    for t in doc.xpath("//time[@datetime]"):
        times.append({"datetime": t.get("datetime"), "itemprop": (t.get("itemprop") or "").lower(),
                      "cls": (t.get("class") or "").lower(), "text": clean_text(t.text_content())})
    return {"meta": meta, "title": clean_text(title), "canonical": canonical, "times": times,
            "lang": (doc.xpath("string(/html/@lang)") or "").strip()}


# --------------------------------------------------------------------------- Arc XP (Fusion)

def _raw_json_after(text: str, marker: str):
    idx = text.find(marker)
    if idx < 0:
        return None
    start = text.find("{", idx)
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj
    except json.JSONDecodeError:
        return None


EMBED_PROVIDERS = [
    (r"youtube\.com|youtu\.be", "video", "YouTube"),
    (r"vimeo\.com", "video", "Vimeo"),
    (r"dailymotion\.com", "video", "Dailymotion"),
    (r"jwplayer|jwplatform|brightcove|kaltura|mdstrm|mediastream|ooyala", "video", "Reproductor de vídeo"),
    (r"(twitter|x)\.com", "red_social", "X (Twitter)"),
    (r"instagram\.com", "red_social", "Instagram"),
    (r"facebook\.com|fb\.watch", "red_social", "Facebook"),
    (r"tiktok\.com", "red_social", "TikTok"),
    (r"threads\.net", "red_social", "Threads"),
    (r"t\.me|telegram", "red_social", "Telegram"),
    (r"datawrapper|flourish|infogram|tableau|public\.flourish", "grafico", "Gráfico interactivo"),
    (r"google\.[a-z.]+/maps|maps\.google|openstreetmap|mapbox|arcgis", "mapa", "Mapa"),
    (r"soundcloud|spotify|ivoox|anchor\.fm", "audio", "Audio"),
    (r"scribd|documentcloud|drive\.google|docs\.google|\.pdf($|\?)", "documento", "Documento"),
]


def classify_embed(url: str) -> tuple[str, str]:
    u = (url or "").lower()
    for pat, kind, provider in EMBED_PROVIDERS:
        if re.search(pat, u):
            return kind, provider
    host = urlsplit(u).netloc
    return "insercion", host or "Contenido insertado"


def parse_arc(page_text: str, base_url: str) -> dict:
    """Extrae el artículo de páginas construidas con Arc XP (``Fusion.globalContent``)."""
    gc = _raw_json_after(page_text, "Fusion.globalContent")
    if not isinstance(gc, dict) or not gc.get("content_elements"):
        return {}
    blocks = []

    def add_image(el):
        url = el.get("url") or (el.get("additional_properties") or {}).get("originalUrl")
        if not url:
            return
        credits = ", ".join(_names((el.get("credits") or {}).get("by") or []))
        blocks.append({"type": "figure", "src": urljoin(base_url, url), "caption": strip_tags(el.get("caption") or ""),
                       "alt": clean_text(el.get("alt_text") or el.get("subtitle") or ""), "credit": credits,
                       "width": el.get("width"), "height": el.get("height")})

    for el in gc.get("content_elements", []):
        t = el.get("type")
        if t == "text":
            content = el.get("content") or ""
            links = []
            try:
                frag = lxml_html.fragment_fromstring(content, create_parent="div")
                for a in frag.xpath(".//a[@href]"):
                    links.append({"href": urljoin(base_url, a.get("href")), "text": clean_text(a.text_content())})
            except Exception:
                pass
            txt = strip_tags(content)
            if txt:
                blocks.append({"type": "paragraph", "text": txt, "links": links})
        elif t == "header":
            txt = strip_tags(el.get("content") or "")
            if txt:
                blocks.append({"type": "heading", "text": txt, "level": el.get("level", 2)})
        elif t == "image":
            add_image(el)
        elif t == "gallery":
            for img in el.get("content_elements", []) or []:
                add_image(img)
        elif t == "video":
            blocks.append({"type": "video", "src": el.get("canonical_url") or "", "provider": "Vídeo del medio",
                           "title": clean_text((el.get("headlines") or {}).get("basic")),
                           "caption": clean_text(el.get("description", {}).get("basic") if isinstance(el.get("description"), dict) else "")})
        elif t in ("oembed_response", "social"):
            raw = el.get("raw_oembed") or {}
            url = raw.get("url") or el.get("referent", {}).get("id") or ""
            kind, prov = classify_embed(url or el.get("subtype", ""))
            blocks.append({"type": kind, "src": url, "provider": raw.get("provider_name") or prov,
                           "title": clean_text(raw.get("title") or raw.get("author_name") or "")})
        elif t == "raw_html":
            content = el.get("content") or ""
            srcs = re.findall(r'(?:src|href)=["\']([^"\']+)["\']', content)
            if srcs:
                kind, prov = classify_embed(srcs[0])
                blocks.append({"type": kind, "src": srcs[0], "provider": prov, "title": ""})
        elif t == "list":
            for item in el.get("items", []) or []:
                txt = strip_tags(item.get("content") or "")
                if txt:
                    blocks.append({"type": "paragraph", "subtype": "lista", "text": txt, "links": []})
        elif t == "quote":
            parts = [strip_tags(c.get("content") or "") for c in el.get("content_elements", []) or []]
            txt = " ".join(p for p in parts if p)
            if txt:
                blocks.append({"type": "paragraph", "subtype": "cita", "text": txt, "links": []})
        elif t == "table":
            blocks.append({"type": "tabla", "src": "", "provider": "Tabla del medio", "title": ""})
        # interstitial_link, correction, etc.: no forman parte del cuerpo informativo

    promo = (gc.get("promo_items") or {}).get("basic") or {}
    main_image = None
    if promo.get("type") == "image" and promo.get("url"):
        main_image = {"src": urljoin(base_url, promo["url"]), "caption": strip_tags(promo.get("caption") or ""),
                      "credit": ", ".join(_names((promo.get("credits") or {}).get("by") or [])),
                      "width": promo.get("width"), "height": promo.get("height"), "alt": clean_text(promo.get("alt_text") or "")}
    tax = gc.get("taxonomy") or {}
    section = ((tax.get("primary_section") or {}).get("name")) or ""
    return {
        "headline": clean_text((gc.get("headlines") or {}).get("basic")),
        "subheadline": clean_text((gc.get("subheadlines") or {}).get("basic")),
        "description": clean_text((gc.get("description") or {}).get("basic")),
        "authors": _names((gc.get("credits") or {}).get("by") or []),
        "date_published": gc.get("first_publish_date") or gc.get("publish_date") or gc.get("display_date"),
        "date_display": gc.get("display_date"),
        "date_modified": gc.get("last_updated_date"),
        "section": clean_text(section),
        "blocks": blocks,
        "main_image": main_image,
    }
