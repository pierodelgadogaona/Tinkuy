"""Color representativo de cada medio.

El color se intenta obtener de la propia identidad gráfica del medio, en este orden:

1. color declarado por la web en su ``<head>``: ``<link rel="mask-icon" color>``, ``msapplication-TileColor``
   y ``<meta name="theme-color">`` (se ignoran los blancos, que no aportan información);
2. ``theme_color`` del manifiesto de la web app (``<link rel="manifest">``);
3. color dominante del logotipo o icono de la web (apple-touch-icon, icono más grande o ``/favicon.ico``);
4. tabla de referencia con la identidad gráfica de medios conocidos (solo si la web no aporta nada);
5. como último recurso, un color asignado de forma determinista a partir del nombre del medio (se marca como tal).

Cada resultado indica su procedencia (``fuente``) para que la interfaz pueda explicarla. La interfaz se
encarga de adaptar el color a un fondo negro y de diferenciar los dos medios entre sí (ver ``frontend/src/lib/colors.js``).
"""
from __future__ import annotations

import colorsys
import hashlib
import io
import json
import re
from urllib.parse import urljoin, urlsplit

from .config import settings

_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})([0-9a-fA-F]{2})?$")
_RGB = re.compile(r"rgba?\(\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})")
NAMED = {"black": "#000000", "white": "#ffffff", "red": "#ff0000", "blue": "#0000ff", "green": "#008000", "orange": "#ffa500",
         "yellow": "#ffff00", "navy": "#000080", "maroon": "#800000", "purple": "#800080", "teal": "#008080", "gray": "#808080"}

# Identidad gráfica de medios conocidos. Solo se usa si la propia web no declara un color ni se puede leer su logotipo.
# clave: dominio (sin «www.»); valor: (color en hexadecimal, descripción de la referencia).
# Colores comprobados en la propia web del medio (meta theme-color) en noviembre de 2026.
_REF_NOTE = "identidad del medio: color de tema que declara su web (referencia verificada en nov. 2026)"
REFERENCE: dict[str, tuple[str, str]] = {
    "larepublica.pe": ("#e00109", _REF_NOTE),
    "elcomercio.pe": ("#f7c600", _REF_NOTE),
    "rpp.pe": ("#0060ab", _REF_NOTE),
    "gestion.pe": ("#444444", _REF_NOTE),
}

# Colores de ejemplo que generan por defecto las herramientas de favicons: no son la identidad del medio.
GENERIC_DEFAULTS = {"#da532c", "#2b5797", "#00aba9", "#603cba", "#ffc40d", "#2d89ef", "#9f00a7", "#b91d47", "#7e3878", "#00a300"}


def parse_color(value) -> str | None:
    """Normaliza un color CSS (#rgb, #rrggbb, rgb(), nombre básico) a ``#rrggbb``."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lower()
    if v in NAMED:
        return NAMED[v]
    m = _HEX.match(v)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return "#" + h.lower()
    m = _RGB.match(v)
    if m:
        r, g, b = (max(0, min(255, int(x))) for x in m.groups())
        return f"#{r:02x}{g:02x}{b:02x}"
    return None


def _rgb(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def _is_white(c: str) -> bool:
    r, g, b = _rgb(c)
    return min(r, g, b) >= 238


def domain_of(url: str) -> str:
    host = urlsplit(url or "").netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


# --------------------------------------------------------------------------- pistas en el HTML

def collect_hints(doc, base_url: str) -> dict:
    """Extrae del ``<head>`` los datos de identidad visual. ``doc`` es el árbol lxml de la página."""
    hints: dict = {}

    def metas(name):
        out = []
        for m in doc.xpath("//meta[@name or @property]"):
            if (m.get("name") or m.get("property") or "").strip().lower() == name:
                out.append(m)
        return out

    themes = metas("theme-color")
    # si hay varios (claro/oscuro), se prefiere el que no está condicionado a un esquema de color
    themes.sort(key=lambda m: 1 if (m.get("media") or "").strip() else 0)
    for m in themes:
        c = parse_color(m.get("content"))
        if c:
            hints["theme_color"] = c
            break
    for m in metas("msapplication-tilecolor"):
        c = parse_color(m.get("content"))
        if c:
            hints["tile_color"] = c
            break
    for link in doc.xpath("//link[@rel]"):
        rel = (link.get("rel") or "").lower().split()
        if "mask-icon" in rel:
            c = parse_color(link.get("color"))
            if c:
                hints["mask_icon_color"] = c
        if "manifest" in rel and link.get("href"):
            hints["manifest"] = urljoin(base_url, link.get("href"))
    icons = []
    for link in doc.xpath("//link[@rel]"):
        rel = (link.get("rel") or "").lower().split()
        if not link.get("href") or not ({"icon", "apple-touch-icon", "apple-touch-icon-precomposed"} & set(rel)):
            continue
        sizes = re.findall(r"(\d+)x\d+", link.get("sizes") or "")
        size = max((int(s) for s in sizes), default=0)
        href = urljoin(base_url, link.get("href"))
        if href.startswith("data:") or href.lower().split("?")[0].endswith(".svg"):
            continue
        icons.append({"href": href, "size": size or (180 if "apple-touch-icon" in rel else 0), "apple": "apple-touch-icon" in rel})
    icons.sort(key=lambda i: (-i["size"], not i["apple"]))
    if icons:
        hints["icons"] = icons[:3]
    return hints


# --------------------------------------------------------------------------- lectura de imágenes y del manifiesto

def dominant_color(data: bytes) -> str | None:
    """Color dominante de un logotipo: ignora transparencias, blancos y grises claros, y prefiere los colores saturados."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGBA")
        img.thumbnail((96, 96))
    except Exception:
        return None
    buckets: dict[tuple[int, int, int], int] = {}
    for r, g, b, a in img.getdata():
        if a < 200:
            continue
        if min(r, g, b) >= 232:      # fondo blanco
            continue
        key = (r // 24, g // 24, b // 24)
        buckets[key] = buckets.get(key, 0) + 1
    if not buckets:
        return None
    best, best_score = None, -1.0
    for (rq, gq, bq), n in buckets.items():
        r, g, b = rq * 24 + 12, gq * 24 + 12, bq * 24 + 12
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        # los colores saturados pesan más que los neutros (negros y grises) del mismo tamaño
        score = n * (0.25 + 1.75 * s) * (1.0 if 0.12 < l < 0.9 else 0.6)
        if score > best_score:
            best, best_score = (r, g, b), score
    return "#%02x%02x%02x" % best if best else None


def _fetch_bytes(url: str, max_bytes: int, accept: str):
    from .extraction.fetcher import fetch
    try:
        r = fetch(url, accept=accept, max_bytes=max_bytes, timeout=6.0, max_redirects=3)
    except Exception:
        return None
    return r.body if r.ok else None


def _manifest_color(url: str) -> str | None:
    body = _fetch_bytes(url, 120_000, "application/manifest+json,application/json,*/*;q=0.5")
    if not body:
        return None
    try:
        return parse_color(json.loads(body.decode("utf-8", "ignore")).get("theme_color"))
    except Exception:
        return None


# --------------------------------------------------------------------------- resolución

def _fallback_color(medio: str) -> str:
    h = int(hashlib.sha1((medio or "medio").strip().lower().encode()).hexdigest()[:6], 16) % 360
    r, g, b = colorsys.hls_to_rgb(h / 360, 0.55, 0.55)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def reference_for(domain: str):
    d = domain
    while d:
        if d in REFERENCE:
            return REFERENCE[d]
        d = d.split(".", 1)[1] if "." in d else ""
    return None


def resolve(article: dict, online: bool = True) -> dict:
    """Devuelve ``{"color", "fuente", "origen"}``. ``origen`` ∈ pagina | logotipo | referencia | asignado."""
    meta = article.get("meta") or {}
    hints = article.get("brand_hints") or {}
    page_url = article.get("final_url") or article.get("url") or meta.get("url") or ""
    domain = domain_of(page_url)
    parts = urlsplit(page_url)
    origin_url = f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""
    for key, label in (("mask_icon_color", "color de icono declarado por la web (mask-icon)"),
                       ("theme_color", "color de tema declarado por la web (theme-color)"),
                       ("tile_color", "color de mosaico declarado por la web (msapplication-TileColor)")):
        c = hints.get(key)
        if c and not _is_white(c) and c not in GENERIC_DEFAULTS:
            return {"color": c, "fuente": label, "origen": "pagina"}
    if online:
        if hints.get("manifest"):
            c = _manifest_color(hints["manifest"])
            if c and not _is_white(c) and c not in GENERIC_DEFAULTS:
                return {"color": c, "fuente": "color de tema del manifiesto de la web", "origen": "pagina"}
        icons = list(hints.get("icons") or [])
        if origin_url:
            icons.append({"href": f"{origin_url}/favicon.ico"})
        for icon in icons[:3]:
            data = _fetch_bytes(icon["href"], 400_000, "image/*,*/*;q=0.5")
            c = dominant_color(data) if data else None
            if c:
                return {"color": c, "fuente": "color dominante del logotipo o icono de la web", "origen": "logotipo"}
    ref = reference_for(domain)
    if ref:
        return {"color": ref[0], "fuente": ref[1], "origen": "referencia"}
    return {"color": _fallback_color(meta.get("medio") or domain), "fuente": "color asignado (no se pudo obtener de la identidad del medio)",
            "origen": "asignado"}


def ensure(article: dict) -> dict:
    """Garantiza ``article['brand']`` sin red (para proyectos anteriores que no lo tienen). No modifica el almacenamiento."""
    if not article.get("brand"):
        article["brand"] = resolve(article, online=False)
    return article["brand"]
