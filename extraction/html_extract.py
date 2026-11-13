"""Extracción del contenido periodístico principal a partir del DOM.

Algoritmo en tres pasos:
1. Limpieza: se eliminan scripts, navegación, publicidad, módulos de
   recomendaciones, comentarios, botones sociales, ventanas de suscripción, etc.
2. Localización del cuerpo: primero contenedores semánticos conocidos
   (``itemprop=articleBody``, ``.article-body``, ``<article>``...) y, si no hay,
   una puntuación de densidad de texto al estilo *Readability* (párrafos,
   comas, longitud y densidad de enlaces).
3. Recorrido ordenado del cuerpo para producir bloques: párrafos, subtítulos,
   figuras con pie y crédito, vídeos, publicaciones insertadas, gráficos, mapas.
"""
from __future__ import annotations

import copy
import re
from urllib.parse import urljoin, urlsplit

from lxml import html as lxml_html

from .structured import classify_embed, clean_text

STRUCTURAL_REMOVE = {"script", "style", "noscript", "template", "svg", "form", "button", "input", "select",
                     "textarea", "link", "meta", "nav", "footer", "aside", "dialog", "canvas", "object", "embed"}
REMOVE_ROLES = {"navigation", "banner", "contentinfo", "complementary", "dialog", "search", "alertdialog", "menu", "menubar"}

NEG = re.compile(
    r"(^|[\s_\-])(ads?|adv|advert\w*|anuncio\w*|publicidad|banner\w*|promo\w*|sponsor\w*|patrocin\w*|newsletter\w*|"
    r"subscri\w*|suscri\w*|modal\w*|popup\w*|overlay|cookie\w*|consent\w*|share\w*|sharing|compart\w*|social\w*|"
    r"redes|comment\w*|comentario\w*|disqus|related|relacionad\w*|recomend\w*|recommend\w*|outbrain|taboola|"
    r"trending|tendencia\w*|mas-?leid\w*|most-?read|lee-?tambien|leer-?mas|te-?puede\w*|widget\w*|sidebar|"
    r"footer|menu\w*|nav|navbar|navigation|breadcrumb\w*|tags?|etiquetas?|signup|registro|login|gpt|dfp|teads|"
    r"native|outstream|sticky|toolbar|byline-social|author-bio|bio|newsletter-box|paywall-?(prompt|message|banner|modal))"
    r"([\s_\-]|$)", re.I)
STRONG_NEG = re.compile(r"(comment|comentario|related|relacionad|recomend|recommend|outbrain|taboola|newsletter|"
                        r"footer|menu|navbar|sidebar|trending|mas-?leid|most-?read|cookie|consent)", re.I)
POSITIVE = re.compile(r"(article|articulo|body|content|contenido|entry|main|post|story|text|texto|cuerpo|nota|"
                      r"noticia|detail|detalle|news)", re.I)
EMBED_CLASSES = re.compile(r"(twitter-tweet|twitter-video|instagram-media|tiktok-embed|fb-post|fb-video|"
                           r"threads-embed|reddit-card|bluesky-embed)", re.I)
BAD_IMG = re.compile(r"(logo|icon|avatar|sprite|pixel|blank|spacer|placeholder|1x1|tracking|gravatar|emoji|badge|"
                     r"loader|loading|lazy\.gif|transparent)", re.I)
BOILER = re.compile(
    r"^\s*(lee|leer|lea|mira|ver|te puede interesar|también te puede interesar|lee también|lea también|lee más|"
    r"más información|publicidad|advertisement|anuncio|síguenos|sigue a|suscríbete|únete|comparte|compartir|"
    r"descarga|escucha|recomendado|relacionad[oa]s?|noticias relacionadas|tags?|etiquetas|temas|para más|"
    r"haz clic|click aquí|clic aquí|whatsapp|telegram|google news|fuente: (?=.{0,40}$))\b", re.I)
CREDIT_LINE = re.compile(r"^\s*\(?(foto|fotos|fotografía|imagen|imágenes|vídeo|video|crédito|créditos|infografía)s?\s*[:|/]", re.I)
DATE_TEXT = re.compile(
    r"(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
    r"(?:\s+(?:de|del)\s+(\d{4}))?(?:[^\d]{1,12}(\d{1,2}):(\d{2}))?", re.I)
PAYWALL_TEXT = re.compile(
    r"(suscr[ií]bete (para|y) (seguir|continuar)|contenido (exclusivo )?para suscriptores|exclusivo para suscriptores|"
    r"hazte suscriptor|inicia sesi[oó]n para (seguir|continuar|leer)|para (seguir|continuar) leyendo|"
    r"este (art[ií]culo|contenido) es exclusivo|ya eres suscriptor|accede a todo el contenido|"
    r"reg[ií]strate (gratis )?para (seguir|continuar|leer)|subscribe to (continue|read)|"
    r"has alcanzado el l[ií]mite de art[ií]culos)", re.I)
PAYWALL_CLASS = re.compile(r"(paywall|regwall|premium-content|content-locked|locked-content|subscriber-only|"
                           r"tp-modal|piano-|meter-|metered|suscriptores-only)", re.I)
CHALLENGE = re.compile(
    r"(just a moment\.\.\.|attention required! \| cloudflare|cf-browser-verification|challenge-platform|"
    r"checking your browser|datadome|px-captcha|pardon our interruption|request unsuccessful\. incapsula|"
    r"access denied|please enable js and disable any ad blocker|verify you are human|verifica que eres humano)",
    re.I)


def _attrs(el) -> str:
    return f"{el.get('class') or ''} {el.get('id') or ''}"


def _text(el) -> str:
    return clean_text(el.text_content())


def _words(s: str) -> int:
    return len(re.findall(r"\w+", s or ""))


def link_density(el) -> float:
    total = len(_text(el)) or 1
    links = sum(len(_text(a)) for a in el.iter("a"))
    return min(1.0, links / total)


def page_signals(doc) -> dict:
    """Señales de muro de pago o desafío antibots sobre el documento original."""
    raw_title = clean_text(doc.xpath("string(//title)"))
    body_txt = clean_text(doc.xpath("string(//body)"))[:20000]
    classes = " ".join((e.get("class") or "") + " " + (e.get("id") or "") for e in doc.iter() if isinstance(e.tag, str))
    challenge = bool(CHALLENGE.search(raw_title)) or (len(body_txt) < 2500 and bool(CHALLENGE.search(body_txt)))
    return {
        "paywall_text": bool(PAYWALL_TEXT.search(body_txt)),
        "paywall_class": bool(PAYWALL_CLASS.search(classes)),
        "challenge": challenge,
        "p_count": len(doc.xpath("//p")),
        "script_count": len(doc.xpath("//script")),
        "body_chars": len(body_txt),
    }


def clean_document(doc):
    doc = copy.deepcopy(doc)
    for el in list(doc.iter()):
        if not isinstance(el.tag, str) and el.getparent() is not None:  # comentarios, instrucciones
            try:
                el.drop_tree()
            except Exception:
                el.getparent().remove(el)
    for el in list(doc.iter()):
        if not isinstance(el.tag, str) or el.getparent() is None:
            continue
        tag = el.tag.lower()
        role = (el.get("role") or "").lower()
        if tag in STRUCTURAL_REMOVE or role in REMOVE_ROLES or el.get("aria-modal") == "true":
            el.drop_tree()
            continue
        if tag in ("iframe", "blockquote", "figure", "video", "picture", "img", "p", "h1", "h2", "h3", "h4"):
            continue
        attrs = _attrs(el)
        if attrs.strip() and NEG.search(attrs):
            if not STRONG_NEG.search(attrs):
                long_ps = [p for p in el.iter("p") if len(_text(p)) >= 80]
                if len(long_ps) >= 3:
                    continue  # protege un cuerpo con clases ambiguas
            el.drop_tree()
    return doc


CANDIDATE_XPATH = (
    '//*[@itemprop="articleBody"] | //*[@data-type="article-body"] | //*[@data-testid="article-body"] | '
    '//*[contains(@class,"article-body") or contains(@class,"article__body") or contains(@class,"articleBody") '
    'or contains(@class,"story-body") or contains(@class,"story__body") or contains(@class,"story-contents") '
    'or contains(@class,"entry-content") or contains(@class,"post-content") or contains(@class,"content-body") '
    'or contains(@class,"article-content") or contains(@class,"article__content") or contains(@class,"news-body") '
    'or contains(@class,"nota-body") or contains(@class,"body-nota") or contains(@class,"cuerpo") '
    'or contains(@class,"c-detail__body") or contains(@class,"td-post-content") or contains(@class,"rich-text") '
    'or contains(@id,"cuerpo") or contains(@id,"article-body")] | //article | //main'
)


def _p_words(el) -> int:
    return sum(_words(_text(p)) for p in el.iter("p") if _words(_text(p)) >= 5)


def find_container(doc):
    candidates = []
    for el in doc.xpath(CANDIDATE_XPATH):
        w = _p_words(el)
        if w >= 60:
            candidates.append((w, el))
    if candidates:
        # El contenedor más específico con casi todo el texto: se prefiere el más profundo
        # cuyo número de palabras sea >= 85 % del máximo.
        max_w = max(w for w, _ in candidates)
        good = [(w, el) for w, el in candidates if w >= 0.85 * max_w]
        good.sort(key=lambda t: len(list(t[1].iterancestors())), reverse=True)
        return good[0][1], "selector"
    # Puntuación tipo Readability
    scores: dict = {}
    for p in doc.iter("p", "pre", "td", "div"):
        if p.tag == "div" and any(isinstance(c.tag, str) and c.tag in ("p", "div", "section", "article") for c in p):
            continue
        txt = _text(p)
        if len(txt) < 25:
            continue
        parent = p.getparent()
        grand = parent.getparent() if parent is not None else None
        content = 1 + txt.count(",") + min(len(txt) // 100, 3)
        for node, w in ((parent, 1.0), (grand, 0.5)):
            if node is None or not isinstance(node.tag, str):
                continue
            if node not in scores:
                base = 0
                a = _attrs(node)
                if POSITIVE.search(a):
                    base += 25
                if NEG.search(a):
                    base -= 25
                base += {"div": 5, "article": 10, "section": 3, "main": 5, "td": 3}.get(node.tag, 0)
                scores[node] = base
            scores[node] += content * w
    if not scores:
        body = doc.find(".//body")
        return (body if body is not None else doc), "documento"
    best = max(scores, key=lambda n: scores[n] * (1 - link_density(n)))
    return best, "densidad"


# --------------------------------------------------------------------------- bloques

def _best_src(img) -> str:
    for attr in ("data-src", "data-lazy-src", "data-original", "data-url", "data-full", "src"):
        v = img.get(attr)
        if v and not v.startswith("data:"):
            return v.strip()
    for attr in ("data-srcset", "srcset"):
        v = img.get(attr)
        if v:
            best, best_w = "", -1
            for part in v.split(","):
                bits = part.strip().split()
                if not bits:
                    continue
                w = 0
                if len(bits) > 1 and bits[1].endswith("w"):
                    try:
                        w = int(bits[1][:-1])
                    except ValueError:
                        w = 0
                if w >= best_w:
                    best, best_w = bits[0], w
            if best:
                return best
    return img.get("src") or ""


def _int(v):
    try:
        return int(str(v).replace("px", "").strip())
    except (TypeError, ValueError):
        return None


def _split_credit(caption: str) -> tuple[str, str]:
    m = re.search(r"[\(\[\|/–—-]?\s*\(?(foto|fotos|fotografía|imagen|crédito|créditos|archivo)s?\s*[:/]\s*([^)\]]{2,80})[\)\]]?\s*$",
                  caption, re.I)
    if m:
        return caption[: m.start()].strip(" .|-–—"), m.group(2).strip()
    m = re.search(r"\(([A-ZÁÉÍÓÚ][\w .áéíóúñ/&-]{1,40})\)\s*$", caption)
    if m and any(k in m.group(1).lower() for k in ("efe", "afp", "reuters", "ap", "andina", "archivo", "difusión", "difusion", "gec", "europa press", "/")):
        return caption[: m.start()].strip(), m.group(1).strip()
    return caption, ""


class BlockBuilder:
    def __init__(self, base_url: str):
        self.base = base_url
        self.blocks: list[dict] = []
        self.seen_src: set[str] = set()
        self.seen_text: set[str] = set()

    def last_paragraph_id(self):
        for b in reversed(self.blocks):
            if b["type"] == "paragraph":
                return b.get("_order")
        return None

    def add(self, block: dict):
        block["_order"] = len(self.blocks)
        self.blocks.append(block)

    def paragraph(self, el, subtype: str = ""):
        txt = _text(el)
        if not txt:
            return
        words = _words(txt)
        ld = link_density(el)
        if words < 25 and BOILER.search(txt):
            return
        if ld > 0.7 and words < 30:
            return  # enlace recomendado, no texto informativo
        if CREDIT_LINE.search(txt) and words <= 14:
            fig = next((b for b in reversed(self.blocks[-2:]) if b["type"] == "figure"), None)
            if fig is not None and not fig.get("credit"):
                fig["credit"] = re.sub(CREDIT_LINE, "", txt).strip(" :)")
            return
        if txt.isupper() and words < 12:
            return  # rótulos tipo «LEE TAMBIÉN»
        key = txt[:160].lower()
        if key in self.seen_text:
            return
        self.seen_text.add(key)
        links = []
        for a in el.iter("a"):
            href = a.get("href")
            if href and not href.startswith(("javascript:", "#", "mailto:")):
                links.append({"href": urljoin(self.base, href), "text": _text(a)})
        b = {"type": "paragraph", "text": txt, "links": links}
        if subtype:
            b["subtype"] = subtype
        self.add(b)

    def heading(self, el):
        txt = _text(el)
        if 2 <= len(txt) <= 220 and not BOILER.search(txt):
            self.add({"type": "heading", "text": txt, "level": int(el.tag[1]) if el.tag[1:].isdigit() else 2})

    def figure(self, el):
        imgs = [i for i in el.iter("img")]
        cap_el = el.find(".//figcaption")
        caption, credit = "", ""
        if cap_el is not None:
            cred_nodes = [n for n in cap_el.iter() if isinstance(n.tag, str) and
                          re.search(r"(credit|credito|crédito|autor|author|copyright|fuente|source|photographer)", _attrs(n), re.I)]
            if cred_nodes:
                credit = _text(cred_nodes[0])
                for n in cred_nodes:
                    n.drop_tree()
            caption = _text(cap_el)
            if not credit:
                caption, credit = _split_credit(caption)
        credit = re.sub(r"^\(?\s*(foto|fotos|fotografía|imagen|crédito|créditos)\s*[:/]\s*", "", credit or "", flags=re.I).strip(" )")
        if not imgs:
            ifr = el.find(".//iframe")
            if ifr is not None:
                self.iframe(ifr, caption=caption)
            elif el.find(".//video") is not None:
                self.video(el.find(".//video"), caption=caption)
            return
        img = imgs[0]
        src = _best_src(img)
        if not src or BAD_IMG.search(src):
            return
        src = urljoin(self.base, src)
        if src in self.seen_src:
            return
        self.seen_src.add(src)
        w, h = _int(img.get("width")), _int(img.get("height"))
        kind = "figure"
        if re.search(r"(infograf|infographic|grafico|gráfico|chart|mapa|map)", _attrs(el) + " " + caption, re.I):
            kind = "figure"  # se clasifica en la fase 10 a partir del pie
        self.add({"type": kind, "src": src, "alt": clean_text(img.get("alt")), "caption": caption, "credit": credit,
                  "width": w, "height": h})

    def image(self, img):
        src = _best_src(img)
        if not src or BAD_IMG.search(src):
            return
        w, h = _int(img.get("width")), _int(img.get("height"))
        if (w and w < 120) or (h and h < 90):
            return
        src = urljoin(self.base, src)
        if src in self.seen_src:
            return
        self.seen_src.add(src)
        self.add({"type": "figure", "src": src, "alt": clean_text(img.get("alt")), "caption": "", "credit": "",
                  "width": w, "height": h})

    def iframe(self, el, caption: str = ""):
        src = el.get("src") or el.get("data-src") or ""
        if not src or src.startswith("about:"):
            return
        src = urljoin(self.base, src)
        kind, provider = classify_embed(src)
        if re.search(r"(doubleclick|googlesyndication|adservice|ads\.|/ads/|taboola|outbrain)", src, re.I):
            return
        self.add({"type": kind, "src": src, "provider": provider, "title": clean_text(el.get("title")),
                  "caption": caption, "width": _int(el.get("width")), "height": _int(el.get("height"))})

    def video(self, el, caption: str = ""):
        src = el.get("src") or ""
        if not src:
            s = el.find(".//source")
            src = s.get("src") if s is not None else ""
        self.add({"type": "video", "src": urljoin(self.base, src) if src else "", "provider": "Vídeo del medio",
                  "title": clean_text(el.get("title")), "caption": caption,
                  "poster": urljoin(self.base, el.get("poster")) if el.get("poster") else ""})

    def blockquote(self, el):
        attrs = _attrs(el)
        if EMBED_CLASSES.search(attrs):
            href = ""
            for a in el.iter("a"):
                h = a.get("href") or ""
                if re.search(r"(twitter|x)\.com/.+/status|instagram\.com/(p|reel)|tiktok\.com/|facebook\.com/", h):
                    href = h
            href = href or el.get("cite") or el.get("data-instgrm-permalink") or ""
            kind, provider = classify_embed(href or attrs)
            self.add({"type": "red_social", "src": href, "provider": provider, "title": _text(el)[:300]})
            return
        if el.find(".//p") is not None:
            for p in el.iter("p"):
                self.paragraph(p, subtype="cita")
        else:
            self.paragraph(el, subtype="cita")

    def walk(self, el):
        for child in el:
            tag = child.tag
            if not isinstance(tag, str):
                continue
            tag = tag.lower()
            if tag == "p":
                if child.find(".//img") is not None and _words(_text(child)) < 4:
                    for img in child.iter("img"):
                        self.image(img)
                    continue
                if child.find(".//iframe") is not None and _words(_text(child)) < 4:
                    for ifr in child.iter("iframe"):
                        self.iframe(ifr)
                    continue
                self.paragraph(child)
            elif tag in ("h2", "h3", "h4", "h5", "h6"):
                self.heading(child)
            elif tag == "h1":
                continue
            elif tag == "figure":
                self.figure(child)
            elif tag == "picture":
                img = child.find(".//img")
                if img is not None:
                    self.image(img)
            elif tag == "img":
                self.image(child)
            elif tag == "blockquote":
                self.blockquote(child)
            elif tag in ("ul", "ol"):
                items = [li for li in child.iterchildren("li")]
                if items and link_density(child) < 0.5:
                    for li in items:
                        if _words(_text(li)) >= 3:
                            self.paragraph(li, subtype="lista")
            elif tag == "iframe":
                self.iframe(child)
            elif tag == "video":
                self.video(child)
            elif tag == "table":
                rows = [[_text(c) for c in r.iter("td", "th")] for r in child.iter("tr")]
                self.add({"type": "tabla", "src": "", "provider": "Tabla en el cuerpo", "title": "",
                          "rows": rows[:30]})
            elif tag in ("pre",):
                self.paragraph(child)
            else:
                has_blocks = any(isinstance(d.tag, str) and d.tag.lower() in
                                 ("p", "h2", "h3", "h4", "figure", "img", "blockquote", "ul", "ol", "iframe", "video", "table", "div", "section")
                                 for d in child.iterdescendants())
                if has_blocks:
                    # texto suelto dentro de un div con <br>
                    direct = clean_text((child.text or "") + " ".join((c.tail or "") for c in child if isinstance(c.tag, str) and c.tag == "br"))
                    if _words(direct) >= 12:
                        self.add({"type": "paragraph", "text": direct, "links": []})
                    self.walk(child)
                else:
                    txt = _text(child)
                    if _words(txt) >= 12 and tag in ("div", "section", "span", "article", "main"):
                        self.paragraph(child)


def extract_dom(doc, base_url: str) -> dict:
    cleaned = clean_document(doc)
    container, method = find_container(cleaned)
    containers = [container]
    # Hermanos con cuerpo de texto (artículos partidos en varios contenedores)
    parent = container.getparent()
    if parent is not None and method != "documento":
        siblings = [s for s in parent if isinstance(s.tag, str)]
        idx = siblings.index(container) if container in siblings else -1
        for s in siblings[idx + 1:]:
            if s.tag in ("div", "section") and _p_words(s) >= 25 and link_density(s) < 0.25 and not NEG.search(_attrs(s)):
                containers.append(s)
            elif _p_words(s) == 0 and s.find(".//figure") is None:
                continue
            else:
                break
    bb = BlockBuilder(base_url)
    for c in containers:
        if c.tag == "p":
            bb.paragraph(c)
        else:
            bb.walk(c)
    words = sum(_words(b["text"]) for b in bb.blocks if b["type"] == "paragraph")
    return {"blocks": bb.blocks, "words": words, "method": method}


# --------------------------------------------------------------------------- metadatos del DOM

SUBTITLE_CLASS = re.compile(r"(subtitle|subtitulo|sub-title|sumario|bajada|epigraph|epigrafe|entradilla|standfirst|"
                            r"deck|dek|summary|excerpt|lead|sub-headline|subheadline|article-subheadline|"
                            r"story-summary|c-detail__subtitle|copete|volanta)", re.I)
AUTHOR_CLASS = re.compile(r"(author|autor|byline|firma|writer|redactor|periodista)", re.I)
SECTION_CLASS = re.compile(r"(breadcrumb|migas|section-name|seccion|kicker|category|categoria)", re.I)


def dom_metadata(doc, base_url: str) -> dict:
    out: dict = {}
    h1s = [h for h in doc.xpath("//h1") if _words(_text(h)) >= 3]
    if h1s:
        out["headline"] = _text(h1s[0])
        h1 = h1s[0]
        # subtítulo: hermano siguiente o elemento con clase característica cercano
        cand = None
        nxt = h1.getnext()
        hops = 0
        while nxt is not None and hops < 4:
            if isinstance(nxt.tag, str):
                if SUBTITLE_CLASS.search(_attrs(nxt)) or nxt.tag in ("h2",):
                    cand = nxt
                    break
            nxt = nxt.getnext()
            hops += 1
        if cand is None:
            for el in doc.xpath("//*[@class]"):
                if el.tag in ("h2", "p", "div", "span", "h3") and SUBTITLE_CLASS.search(el.get("class") or "") \
                        and 6 <= _words(_text(el)) <= 80 and not AUTHOR_CLASS.search(el.get("class") or ""):
                    cand = el
                    break
        if cand is not None and 4 <= _words(_text(cand)) <= 90:
            out["subtitle"] = _text(cand)
    authors = []
    for el in doc.xpath('//*[@rel="author"] | //*[@itemprop="author"] | //*[@class]'):
        if el.get("rel") == "author" or el.get("itemprop") == "author" or AUTHOR_CLASS.search(el.get("class") or ""):
            t = _text(el)
            t = re.sub(r"^(por|by|escrito por|redacción:?)\s+", "", t, flags=re.I).strip()
            if 2 <= len(t) <= 80 and _words(t) <= 8 and not re.search(r"\d{4}|actualizado|publicado", t, re.I):
                if t not in authors:
                    authors.append(t)
        if len(authors) >= 3:
            break
    if authors:
        out["authors"] = authors
    crumbs = []
    for el in doc.xpath("//*[@class]"):
        if re.search(r"breadcrumb|migas", el.get("class") or "", re.I):
            crumbs = [_text(a) for a in el.iter("a") if _text(a)]
            break
    crumbs = [c for c in crumbs if c.lower() not in ("inicio", "home", "portada")]
    if crumbs:
        out["section"] = crumbs[-1]
        out["section_source"] = "migas de pan"
    # fechas en texto
    for el in doc.xpath("//*[@class]"):
        if re.search(r"(date|fecha|time|publicado|published)", el.get("class") or "", re.I):
            m = DATE_TEXT.search(_text(el))
            if m:
                out.setdefault("date_text", _text(el)[:120])
                break
    return out


def section_from_url(url: str) -> str:
    path = urlsplit(url).path.strip("/").split("/")
    if len(path) >= 2 and re.fullmatch(r"[a-záéíóúñ\-]{3,30}", path[0], re.I) and not path[0].isdigit():
        return path[0].replace("-", " ").capitalize()
    return ""


def parse_html(text: str, base_url: str):
    try:
        doc = lxml_html.fromstring(text)
    except Exception:
        doc = lxml_html.fromstring(text.encode("utf-8", "replace"))
    try:
        doc.make_links_absolute(base_url, resolve_base_href=True)
    except Exception:
        pass
    return doc
