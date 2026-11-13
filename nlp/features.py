"""Cálculos programáticos sobre cada noticia.

Todo lo que aquí se calcula es exacto respecto de las reglas declaradas (conteos,
promedios, porcentajes, coincidencias léxicas). Las clasificaciones heurísticas
(p. ej. «construcciones con se», entidades) se marcan como aproximadas.
"""
from __future__ import annotations

import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from . import lexicons as L
from .text import (alpha_tokens, count_words, declarative_forms, norm_key, normalize, split_sentences, stem,
                   strip_accents, syllables, words)

DECL_FORMS = declarative_forms(L.DECLARATIVE_INFINITIVES, L.IRREGULAR_DECLARATIVE_FORMS, L.AMBIGUOUS_DECLARATIVE)
_STOP_KEYS = {strip_accents(w) for w in L.STOPWORDS}


def _phrase_regex(phrases):
    items = sorted(set(phrases), key=len, reverse=True)
    return re.compile(r"(?<![\wáéíóúñü])(" + "|".join(re.escape(p) for p in items) + r")(?![\wáéíóúñü])", re.I)


_CONN_RE = {cat: _phrase_regex(lst) for cat, lst in L.CONNECTORS.items()}
_MOD_RE = {cat: _phrase_regex(lst) for cat, lst in L.MODALITY.items()}
_INT_RE = _phrase_regex(L.INTENSIFIERS)
_ATT_RE = _phrase_regex(L.ATTENUATORS)
_EMO_RE = _phrase_regex(L.EMOTION_WORDS)
_SENS_RE = _phrase_regex(L.SENSATIONAL_WORDS)
_INST_RE = _phrase_regex(L.INSTITUTIONAL_FORMULAS)
_LEGAL_RE = _phrase_regex(L.LEGAL_TERMS)
_COLLOQ_RE = _phrase_regex(L.COLLOQUIAL)
_COMM_RE = _phrase_regex(L.COMMUNIQUE_MARKERS)
_AGENCY_RE = re.compile(r"(?<![\w])(" + "|".join(re.escape(a) for a in sorted(L.AGENCIES, key=len, reverse=True)) + r")(?![\w])")
_DECL_RE = _phrase_regex(list(DECL_FORMS.keys()))


# --------------------------------------------------------------------------- unidades de texto

def body(article) -> list[dict]:
    return [b for b in article.get("blocks", []) if b["type"] == "paragraph"]


def headings(article) -> list[dict]:
    return [b for b in article.get("blocks", []) if b["type"] == "heading"]


def units(article, include_meta: bool = True) -> list[tuple[str, str]]:
    out = []
    m = article.get("meta", {})
    if include_meta and m.get("titular"):
        out.append(("T", m["titular"]))
    if include_meta and m.get("subtitulo"):
        out.append(("S", m["subtitulo"]))
    for b in article.get("blocks", []):
        if b["type"] in ("paragraph", "heading"):
            out.append((b["id"], b["text"]))
        elif b["type"] == "figure" and b.get("caption") and include_meta:
            out.append((b["id"], b["caption"]))
    return out


def content_tokens(text: str) -> list[str]:
    return [t.lower() for t in alpha_tokens(text) if len(t) >= 3 and strip_accents(t.lower()) not in _STOP_KEYS]


# --------------------------------------------------------------------------- métricas

def metrics(article) -> dict:
    paras = body(article)
    pw = [count_words(p["text"]) for p in paras]
    sents = []
    sent_by_p = {}
    for p in paras:
        ss = split_sentences(p["text"])
        sent_by_p[p["id"]] = len(ss)
        sents.extend(ss)
    sw = [count_words(s) for s in sents]
    total = sum(pw)
    m = article.get("meta", {})
    return {
        "palabras": total,
        "parrafos": len(paras),
        "oraciones": len(sents),
        "subtitulos": len(headings(article)),
        "media_palabras_parrafo": round(total / len(paras), 1) if paras else 0,
        "media_palabras_oracion": round(sum(sw) / len(sw), 1) if sw else 0,
        "mediana_palabras_oracion": statistics.median(sw) if sw else 0,
        "desv_palabras_parrafo": round(statistics.pstdev(pw), 1) if len(pw) > 1 else 0,
        "parrafo_mas_largo": max(pw) if pw else 0,
        "parrafo_mas_corto": min(pw) if pw else 0,
        "oracion_mas_larga": max(sw) if sw else 0,
        "oraciones_largas_30": sum(1 for x in sw if x > 30),
        "palabras_titular": count_words(m.get("titular", "")),
        "palabras_subtitulo": count_words(m.get("subtitulo", "")),
        "palabras_por_parrafo": [{"id": p["id"], "palabras": w, "oraciones": sent_by_p[p["id"]]} for p, w in zip(paras, pw)],
        "longitudes_oracion": sw,
    }


def readability(article) -> dict:
    text = " ".join(p["text"] for p in body(article))
    toks = alpha_tokens(text)
    n_words = len(toks)
    sents = split_sentences(text)
    n_sent = max(1, len(sents))
    syl = [syllables(t) for t in toks]
    n_syl = sum(syl)
    if n_words == 0:
        return {"disponible": False}
    p100 = n_syl / n_words * 100
    f100 = n_sent / n_words * 100
    fh = 206.84 - 0.60 * p100 - 1.02 * f100
    sp = 206.835 - 62.3 * (n_syl / n_words) - (n_words / n_sent)
    if sp < 40:
        inflesz = "muy difícil"
    elif sp < 55:
        inflesz = "algo difícil"
    elif sp < 65:
        inflesz = "normal"
    elif sp < 80:
        inflesz = "bastante fácil"
    else:
        inflesz = "muy fácil"
    content = content_tokens(text)
    stems = [stem(t) for t in content]
    lower = [t.lower() for t in toks]
    window = 50
    if len(lower) > window:
        ttrs = [len(set(lower[i:i + window])) / window for i in range(0, len(lower) - window + 1)]
        mattr = sum(ttrs) / len(ttrs)
    else:
        mattr = len(set(lower)) / max(1, len(lower))
    return {
        "disponible": True,
        "silabas": n_syl,
        "silabas_por_palabra": round(n_syl / n_words, 2),
        "palabras_polisilabas_pct": round(100 * sum(1 for s in syl if s >= 4) / n_words, 1),
        "fernandez_huerta": round(fh, 1),
        "szigriszt_pazos": round(sp, 1),
        "inflesz": inflesz,
        "densidad_lexica_pct": round(100 * len(content) / n_words, 1),
        "mattr": round(mattr, 3),
        "raices_distintas": len(set(stems)),
    }


# --------------------------------------------------------------------------- frecuencias

def frequencies(article, top: int = 80) -> list[dict]:
    counts: Counter = Counter()
    forms: dict[str, Counter] = defaultdict(Counter)
    paras_by: dict[str, set] = defaultdict(set)
    for pid, text in units(article, include_meta=True):
        for t in content_tokens(text):
            if t.isdigit():
                continue
            s = stem(t)
            counts[s] += 1
            forms[s][t] += 1
            paras_by[s].add(pid)
    out = []
    for s, n in counts.most_common(top):
        out.append({"raiz": s, "forma": forms[s].most_common(1)[0][0], "n": n, "formas": dict(forms[s]),
                    "unidades": sorted(paras_by[s], key=_unit_order)})
    return out


def _unit_order(u: str):
    if u in ("T", "S"):
        return (0, 0 if u == "T" else 1)
    m = re.match(r"([A-Z])(\d+)", u)
    return (1, int(m.group(2))) if m else (2, 0)


def bigrams(article, top: int = 20) -> list[dict]:
    c: Counter = Counter()
    for _pid, text in units(article):
        toks = [t.lower() for t in alpha_tokens(text)]
        for a, b in zip(toks, toks[1:]):
            if strip_accents(a) in _STOP_KEYS or strip_accents(b) in _STOP_KEYS or len(a) < 3 or len(b) < 3:
                continue
            c[f"{a} {b}"] += 1
    return [{"bigrama": k, "n": v} for k, v in c.most_common(top) if v >= 2]


def distinctive_terms(freq1: list[dict], freq2: list[dict], n1: int, n2: int, top: int = 12) -> dict:
    """Log-odds ponderado con prior de Dirichlet informativo (Monroe, Colaresi y Quinn, 2008).

    El prior es el corpus combinado; z > 0 indica término característico de la noticia 1.
    """
    c1 = {f["raiz"]: f for f in freq1}
    c2 = {f["raiz"]: f for f in freq2}
    vocab = set(c1) | set(c2)
    tot1 = sum(f["n"] for f in freq1) or 1
    tot2 = sum(f["n"] for f in freq2) or 1
    alpha0 = tot1 + tot2
    rows = []
    for w in vocab:
        y1 = c1.get(w, {}).get("n", 0)
        y2 = c2.get(w, {}).get("n", 0)
        if y1 + y2 < 2:
            continue
        a = y1 + y2  # prior proporcional al uso combinado
        d = (math.log((y1 + a) / (tot1 + alpha0 - y1 - a)) - math.log((y2 + a) / (tot2 + alpha0 - y2 - a)))
        var = 1 / (y1 + a) + 1 / (y2 + a)
        z = d / math.sqrt(var)
        forma = (c1.get(w) or c2.get(w))["forma"]
        rows.append({"raiz": w, "forma": forma, "n1": y1, "n2": y2, "z": round(z, 2)})
    rows.sort(key=lambda r: r["z"], reverse=True)
    pos = [r for r in rows if r["z"] > 0.5][:top]
    neg = [r for r in sorted(rows, key=lambda r: r["z"]) if r["z"] < -0.5][:top]
    shared = sorted([r for r in rows if r["n1"] > 0 and r["n2"] > 0], key=lambda r: -(r["n1"] + r["n2"]))[:top]
    return {"noticia1": pos, "noticia2": neg, "compartidos": shared}


# --------------------------------------------------------------------------- conectores y cohesión

def connectors(article) -> dict:
    by_cat = {}
    occ = []
    total_words = sum(count_words(p["text"]) for p in body(article)) or 1
    for cat, rx in _CONN_RE.items():
        n = 0
        for p in body(article):
            for m in rx.finditer(p["text"]):
                n += 1
                occ.append({"p": p["id"], "conector": m.group(1).lower(), "categoria": cat,
                            "ambiguo": m.group(1).lower() in L.AMBIGUOUS_CONNECTORS})
        by_cat[cat] = n
    initial = []
    for p in body(article):
        head = p["text"][:40]
        for cat, rx in _CONN_RE.items():
            m = rx.match(head.lstrip("«“\"¿¡ "))
            if m:
                initial.append({"p": p["id"], "conector": m.group(1), "categoria": cat})
                break
    return {"por_categoria": by_cat, "por_100_palabras": {k: round(100 * v / total_words, 2) for k, v in by_cat.items()},
            "total": sum(by_cat.values()), "ocurrencias": occ, "iniciales": initial}


def cohesion(article) -> dict:
    paras = body(article)
    sets = [{stem(t) for t in content_tokens(p["text"]) if len(t) >= 4} for p in paras]
    initial = {i["p"] for i in connectors(article)["iniciales"]}
    trans = []
    for i in range(1, len(paras)):
        a, b = sets[i - 1], sets[i]
        inter = a & b
        j = len(inter) / len(a | b) if (a | b) else 0
        trans.append({"de": paras[i - 1]["id"], "a": paras[i]["id"], "jaccard": round(j, 3), "compartidas": len(inter),
                      "conector_inicial": paras[i]["id"] in initial,
                      "posible_cambio_abrupto": len(inter) == 0 and paras[i]["id"] not in initial})
    vals = [t["jaccard"] for t in trans]
    return {"transiciones": trans, "media_jaccard": round(sum(vals) / len(vals), 3) if vals else None,
            "cambios_candidatos": [t for t in trans if t["posible_cambio_abrupto"]]}


# --------------------------------------------------------------------------- modalidad y rasgos verbales

def _finditer_all(rx, article, include_meta=False):
    for pid, text in units(article, include_meta=include_meta):
        if pid.startswith("H"):
            continue
        for m in rx.finditer(text):
            yield pid, m, text


def _sentence_of(text: str, pos: int) -> str:
    for s in split_sentences(text):
        idx = text.find(s[:30])
        if idx <= pos < idx + len(s) + 1:
            return s
    return text[max(0, pos - 120): pos + 120]


def modality(article) -> dict:
    out = {}
    occ = []
    for cat, rx in _MOD_RE.items():
        n = 0
        for pid, m, text in _finditer_all(rx, article):
            n += 1
            occ.append({"p": pid, "marcador": m.group(1).lower(), "categoria": cat})
        out[cat] = n
    # afirmaciones categóricas aproximadas: oraciones del cuerpo sin marcador modal ni atribución
    cat_sent = 0
    total = 0
    any_mod = re.compile("|".join(r.pattern for r in _MOD_RE.values()), re.I)
    for p in body(article):
        for s in split_sentences(p["text"]):
            total += 1
            if not any_mod.search(s) and not _DECL_RE.search(s) and not re.search(r"[«“\"]", s):
                cat_sent += 1
    return {"por_categoria": out, "ocurrencias": occ, "oraciones_sin_marcas": cat_sent, "oraciones": total}


_PASSIVE_AUX = r"(?:fue|fueron|ha sido|han sido|había sido|habían sido|será|serán|sería|serían|es|son|era|eran|siendo|sido)"
_PART = r"(?:\w+(?:ado|ada|ados|adas|ido|ida|idos|idas)|" + "|".join(sorted(L.IRREGULAR_PARTICIPLES)) + r")"
_PASSIVE_RE = re.compile(r"\b" + _PASSIVE_AUX + r"\s+(?:\w+mente\s+)?(" + _PART + r")\b", re.I)
_SE_RE = re.compile(r"\bse\s+(?!(?:le|les|lo|la|los|las|me|te|nos)\b)(\w+(?:a|an|e|en|ó|aron|ieron|ará|arán|erá|erán|irá|irán|aba|aban|ía|ían))\b", re.I)
_MENTE_RE = re.compile(r"\b(\w{4,}mente)\b", re.I)
_PRET_RE = re.compile(r"\b(\w{3,}(?:ó|aron|ieron|yeron))\b", re.I)
_FUT_RE = re.compile(r"\b(\w{2,}(?:rá|rán))\b|\b(?:va|van|iba|iban) a (\w+(?:ar|er|ir))\b", re.I)
_COND_RE = re.compile(r"\b(\w{1,}(?:aría|arían|ería|erían|iría|irían|dría|drían|ríamos)|habría|habrían|sabría|sabrían|cabría|querría|querrían)\b")
_IMPF_RE = re.compile(r"\b(\w{2,}(?:aba|aban)|había|habían|tenía|tenían|podía|podían|quería|querían|decía|decían|sabía|"
                      r"venía|venían|iba|iban|era|eran|estaba|estaban)\b", re.I)
_COMPOUND_PAST = re.compile(r"\b(?:ha|han|había|habían|hubo)\s+(" + _PART + r")\b", re.I)
_INDIRECT_RE = re.compile(r"\b(\w+)\s+(?:\w+\s+){0,3}?que\b", re.I)
_NOT_PRET = {"cuantó", "pató"}


def verbal(article) -> dict:
    res = defaultdict(list)
    for pid, text in units(article, include_meta=False):
        if pid.startswith("H"):
            continue
        for m in _PASSIVE_RE.finditer(text):
            part = m.group(1).lower()
            if part not in L.NON_PARTICIPLE_ADO:
                res["pasiva_perifrastica"].append({"p": pid, "forma": m.group(0)})
        for m in _SE_RE.finditer(text):
            res["construccion_se"].append({"p": pid, "forma": m.group(0)})
        for m in _MENTE_RE.finditer(text):
            res["adverbios_mente"].append({"p": pid, "forma": m.group(1).lower()})
        for m in _PRET_RE.finditer(text):
            w = m.group(1).lower()
            if w not in _NOT_PRET and not w[0].isupper():
                res["preterito"].append({"p": pid, "forma": w})
        for m in _COMPOUND_PAST.finditer(text):
            if m.group(1).lower() not in L.NON_PARTICIPLE_ADO:
                res["preterito_compuesto"].append({"p": pid, "forma": m.group(0)})
        for m in _IMPF_RE.finditer(text):
            res["imperfecto"].append({"p": pid, "forma": m.group(0).lower()})
        for m in _FUT_RE.finditer(text):
            res["futuro"].append({"p": pid, "forma": m.group(0).lower()})
        for m in _COND_RE.finditer(text):
            if m.group(1)[0].isupper() and m.start() > 0 and text[m.start() - 2: m.start()].strip() not in ("", ".", "«", "“"):
                continue  # nombre propio (p. ej. «María»)
            w = m.group(1).lower()
            if w in L.NON_CONDITIONAL_RIA:
                continue
            if w.endswith(("ería", "erían")) and w not in L.CONDITIONAL_ERIA:
                continue
            res["condicional"].append({"p": pid, "forma": w})
        for m in _DECL_RE.finditer(text):
            res["verbos_declarativos"].append({"p": pid, "forma": m.group(1).lower(), "infinitivo": DECL_FORMS.get(m.group(1).lower(), "")})
    # discurso indirecto: verbo declarativo seguido de «que» a corta distancia
    indirect = 0
    for pid, text in units(article, include_meta=False):
        for m in re.finditer(r"\b(\w+)\b((?:\s+\w+){0,3})\s+que\b", text):
            if m.group(1).lower() in DECL_FORMS:
                indirect += 1
    counts = {k: len(v) for k, v in res.items()}
    for k in ("pasiva_perifrastica", "construccion_se", "adverbios_mente", "preterito", "preterito_compuesto",
              "imperfecto", "futuro", "condicional", "verbos_declarativos"):
        counts.setdefault(k, 0)
    decl_lemmas = Counter(x["infinitivo"] for x in res["verbos_declarativos"])
    return {"conteos": counts, "ejemplos": {k: v[:12] for k, v in res.items()}, "discurso_indirecto": indirect,
            "declarativos_por_verbo": dict(decl_lemmas.most_common(20)),
            "adverbios_lista": dict(Counter(x["forma"] for x in res["adverbios_mente"]).most_common(20))}


# --------------------------------------------------------------------------- marcadores léxicos

def lexical_markers(article) -> dict:
    def collect(rx, include_meta=True):
        occ = [{"p": pid, "forma": m.group(1).lower()} for pid, m, _t in _finditer_all(rx, article, include_meta)]
        return {"n": len(occ), "ocurrencias": occ, "formas": dict(Counter(o["forma"] for o in occ).most_common(25))}
    full = " ".join(t for _p, t in units(article))
    n_words = count_words(" ".join(p["text"] for p in body(article))) or 1
    exclam = len(re.findall(r"!", full))
    questions = [(pid, q) for pid, t in units(article) for q in re.findall(r"¿[^?]{3,}\?", t)]
    caps = [w for w in re.findall(r"\b[A-ZÁÉÍÓÚÑ]{4,}\b", full) if w not in {"SUTRAN", "SAMU", "SOAT", "MINSA", "ESSALUD", "INEI", "SUNAT"}]
    superl = re.findall(r"\b\w+ísim[oa]s?\b", full, re.I)
    out = {
        "emotivas": collect(_EMO_RE), "sensacionalistas": collect(_SENS_RE),
        "intensificadores": collect(_INT_RE, False), "atenuadores": collect(_ATT_RE, False),
        "formulas_institucionales": collect(_INST_RE, False), "lenguaje_juridico": collect(_LEGAL_RE, False),
        "coloquialismos": collect(_COLLOQ_RE), "marcas_documentales": collect(_COMM_RE, False),
        "exclamaciones": exclam, "preguntas": [{"p": p, "texto": q} for p, q in questions],
        "mayusculas_enfaticas": caps[:20], "superlativos": superl[:20], "palabras": n_words,
    }
    for k in ("emotivas", "sensacionalistas", "intensificadores", "atenuadores", "formulas_institucionales",
              "lenguaje_juridico", "coloquialismos"):
        out[k]["por_1000"] = round(1000 * out[k]["n"] / n_words, 1)
    ag = []
    for pid, text in units(article):
        for m in _AGENCY_RE.finditer(text):
            ag.append({"p": pid, "agencia": L.AGENCIES[m.group(1)]})
    out["agencias"] = ag
    return out


# --------------------------------------------------------------------------- citas

_QUOTE_RES = [re.compile(r"«([^»]{3,}?)»"), re.compile(r"“([^”]{3,}?)”"), re.compile(r'"([^"]{3,}?)"')]
_SPEAKER_AFTER = re.compile(r"^[,.]?\s*(?:—|-)?\s*(\w+)\s+((?:el|la|los|las)\s+)?((?:[A-ZÁÉÍÓÚÑ][\wáéíóúñ.]+\s?){1,4})")


def quotes(article) -> dict:
    items = []
    for pid, text in units(article, include_meta=True):
        for rx in _QUOTE_RES:
            for m in rx.finditer(text):
                q = normalize(m.group(1))
                wc = count_words(q)
                after = text[m.end(): m.end() + 120]
                before = text[max(0, m.start() - 160): m.start()]
                verb = ""
                speaker = ""
                ma = re.match(r"^[,.]?\s*(?:—|-)?\s*(\w+)", after)
                if ma and ma.group(1).lower() in DECL_FORMS:
                    verb = ma.group(1).lower()
                    sm = re.match(r"^[,.]?\s*(?:—|-)?\s*\w+\s+(?:[\wáéíóúñ ]{0,40}?\s)??((?:[A-ZÁÉÍÓÚÑ][\wáéíóúñ.]+\s?){1,4})", after)
                    if sm:
                        speaker = sm.group(1).strip(" ,.")
                if not verb:
                    mb = re.search(r"(\w+)\s*:?\s*$", before)
                    if mb and mb.group(1).lower() in DECL_FORMS:
                        verb = mb.group(1).lower()
                items.append({"p": pid, "texto": q, "palabras": wc, "verbo": verb, "hablante_heuristico": speaker,
                              "es_titular": pid in ("T", "S"), "breve": wc < 4})
    for i, q in enumerate(items, 1):
        q["id"] = f"C{i}"
    body_words = sum(count_words(p["text"]) for p in body(article)) or 1
    quoted = sum(q["palabras"] for q in items if q["p"] not in ("T", "S") and not q["breve"])
    return {"citas": items, "palabras_citadas": quoted, "pct_texto_citado": round(100 * quoted / body_words, 1),
            "n_directas": sum(1 for q in items if not q["breve"]), "n_expresiones_breves": sum(1 for q in items if q["breve"])}


def attribution(article) -> dict:
    total, attributed = 0, 0
    rx_attr = _MOD_RE["atribucion"]
    for p in body(article):
        for s in split_sentences(p["text"]):
            total += 1
            if rx_attr.search(s) or _DECL_RE.search(s) or re.search(r"[«“\"]", s):
                attributed += 1
    return {"oraciones": total, "con_atribucion": attributed,
            "pct": round(100 * attributed / total, 1) if total else 0}


# --------------------------------------------------------------------------- cifras

_NUM = r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d{1,3}(?:,\d{3})+|\d+(?:[.,]\d+)?)"
_NUM_RE = re.compile(r"(?<![\w/:.,])(?P<cur>S/\.?\s?|US\$\s?|\$\s?|€\s?)?" + _NUM +
                     r"(?P<mult>\s(?:mil millones|mil|millones|millón|billones))?(?P<pct>\s?%|\spor\sciento)?(?![\w:])")
_MONTHS = "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"
_WORDNUM_RE = re.compile(r"\b(" + "|".join(sorted((k for k in L.NUMBER_WORDS if k not in ("un", "uno", "una")), key=len, reverse=True)) +
                         r")\b(?:\s(mil|millones))?(?:\s(?:de\s)?)?", re.I)


def _trim_stop(u: str) -> str:
    toks = u.split()
    while toks and strip_accents(toks[-1].lower()) in _STOP_KEYS:
        toks.pop()
    return " ".join(toks)


def _to_float(s: str) -> float | None:
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):
        return float(s.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", s):
        return float(s.replace(",", ""))
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def numbers(article) -> list[dict]:
    items = []
    for pid, text in units(article, include_meta=True):
        if pid.startswith("H"):
            continue
        spans = []
        for m in _NUM_RE.finditer(text):
            s, e = m.span()
            raw = m.group(0).strip()
            val = _to_float(m.group(2))
            after = text[e: e + 40]
            before = text[max(0, s - 30): s]
            kind, unit = "cantidad", ""
            if re.match(r"\s*:\d{2}", text[e:e + 3]) or re.match(r"\s*(a\. ?m\.|p\. ?m\.|horas?\b|h\b)", after, re.I) and val is not None and val <= 24:
                kind, unit = "hora", "hora"
            elif re.match(r"\s+de\s+(" + _MONTHS + r")", after, re.I):
                kind, unit = "fecha", "día"
            elif val and 1900 <= val <= 2100 and float(val).is_integer() and not m.group("cur") and not m.group("pct") \
                    and not re.match(r"\s+(personas|heridos|soles|dólares|kil|metros|casos)", after, re.I):
                kind, unit = "año", "año"
            elif re.search(r"(kil[oó]metro|km)\s*$", before, re.I):
                kind, unit = "ubicacion", "km (punto kilométrico)"
            elif m.group("pct"):
                kind, unit = "porcentaje", "%"
            elif m.group("cur"):
                kind = "moneda"
                cur = m.group("cur").strip()
                unit = {"S/": "S/", "S/.": "S/", "US$": "USD", "$": "USD", "€": "EUR"}.get(cur, cur)
            else:
                for pat, k, u in L.UNIT_PATTERNS:
                    if re.match(r"\s*(?:" + pat + r")", after, re.I):
                        kind, unit = k, u
                        break
                if kind == "duracion_o_edad":
                    kind = "edad" if re.search(r"\bde\s*$", before) else "duracion"
                if kind == "cantidad":
                    nm = re.match(r"\s+(?:de\s+)?((?:\w+\s?){1,3})", after)
                    unit = _trim_stop(nm.group(1)) if nm else ""
            mult = (m.group("mult") or "").strip()
            if val is not None and mult:
                val *= {"mil": 1e3, "millones": 1e6, "millón": 1e6, "mil millones": 1e9, "billones": 1e12}[mult]
            if kind == "moneda" and not m.group("cur"):
                pass
            spans.append((s, e))
            items.append({"p": pid, "texto": raw + (" " + unit if kind in ("cantidad", "medida", "duracion", "edad") and unit and unit not in raw else ""),
                          "valor": val, "unidad": unit, "tipo": kind,
                          "contexto": _sentence_of(text, s)[:300]})
        for m in _WORDNUM_RE.finditer(text):
            s, _e = m.span()
            if any(a <= s < b for a, b in spans):
                continue
            w = m.group(1).lower()
            if s > 0 and text[s - 1].isalpha():
                continue
            val = L.NUMBER_WORDS.get(w)
            if w in ("dos", "tres") and re.match(r"\s+(veces|de ellos|de ellas)", text[m.end() - 1: m.end() + 12]):
                pass
            after = text[m.end(): m.end() + 30]
            nm = re.match(r"((?:\w+\s?){1,2})", after)
            unit = _trim_stop(nm.group(1)) if nm else ""
            mult = (m.group(2) or "").lower()
            if val is not None and mult:
                val *= 1e3 if mult == "mil" else 1e6
            kind = "cantidad" if val is not None else "cantidad_indeterminada"
            for pat, k, u in L.UNIT_PATTERNS:
                if re.match(r"\s*(?:" + pat + r")", after, re.I) or re.match(pat, unit, re.I):
                    kind = "duracion" if k.startswith("duracion") else k
                    unit = u
                    break
            span_end = m.end() + (len(nm.group(1).rstrip()) if nm else 0)
            texto = _trim_stop(text[s:span_end].strip()) or m.group(1)
            items.append({"p": pid, "texto": texto, "valor": val, "unidad": unit, "tipo": kind,
                          "contexto": _sentence_of(text, s)[:300], "en_letras": True})
    for i, it in enumerate(items, 1):
        it["id"] = f"D{i}"
    return items


# --------------------------------------------------------------------------- expresiones temporales

_WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MONTH_N = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
_NUMW = {"un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "diez": 10}
_TEMPORAL_PATTERNS = [
    ("fecha", re.compile(r"\b(\d{1,2})\s+de\s+(" + _MONTHS + r")(?:\s+(?:de|del)\s+(\d{4}))?", re.I)),
    ("dia_semana", re.compile(r"\b(?:(el|este|esta|la noche del|la madrugada del|la madrugada de este|la tarde del|la mañana del|"
                              r"la noche de este|la tarde de este|la mañana de este|el pasado|el próximo)\s+)?(lunes|martes|miércoles|jueves|viernes|sábado|domingo)(\s+pasado|\s+próximo)?\b", re.I)),
    ("relativa", re.compile(r"\b(anteayer|antes de ayer|ayer|anoche|hoy|esta mañana|esta tarde|esta noche|esta madrugada|"
                            r"(?<!la )(?<!esta )(?<!por la )mañana|pasado mañana|la semana pasada|la próxima semana|el mes pasado|el próximo mes|el año pasado|"
                            r"el próximo año|este año|en lo que va del año|desde tempranas horas|hasta el cierre de esta edición|"
                            r"en las próximas horas|en los próximos días|recientemente|actualmente|en la actualidad)\b", re.I)),
    ("hace", re.compile(r"\bhace\s+(\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|diez)\s+(minutos?|horas?|días?|semanas?|meses|mes|años?)\b", re.I)),
    ("dentro", re.compile(r"\bdentro de\s+(\d+|un|una|dos|tres|cuatro|cinco|seis|diez)\s+(días?|semanas?|meses|años?)\b", re.I)),
    ("hora", re.compile(r"\b(?:a las|alrededor de las|cerca de las|hacia las|desde las|hasta las|las)\s+(\d{1,2})(?::(\d{2}))?\s*(a\. ?m\.|p\. ?m\.|horas|h)?", re.I)),
    ("año", re.compile(r"\b(?:en|desde|hasta|durante|de|del año|el año)\s+((?:19|20)\d{2})\b", re.I)),
    ("duracion", re.compile(r"\b(?:durante|por|cerca de|más de|menos de)\s+(\d+|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|diez|doce|veinte)\s+(minutos|horas|días|semanas|meses|años)\b", re.I)),
]


def _parse_pub(pub: str | None) -> datetime | None:
    if not pub:
        return None
    try:
        # hora local tal como la publica el medio (el extractor ya convierte UTC a la zona configurada)
        return datetime.fromisoformat(pub).replace(tzinfo=None)
    except ValueError:
        return None


def temporal_expressions(article) -> list[dict]:
    pub = _parse_pub((article.get("meta") or {}).get("fecha_publicacion"))
    items = []
    for pid, text in units(article, include_meta=True):
        if pid.startswith("H"):
            continue
        for kind, rx in _TEMPORAL_PATTERNS:
            for m in rx.finditer(text):
                expr = m.group(0).strip()
                norm, inferred = None, True
                if kind == "fecha":
                    day, month = int(m.group(1)), _MONTH_N[m.group(2).lower()]
                    year = int(m.group(3)) if m.group(3) else (pub.year if pub else None)
                    if year and pub and not m.group(3) and month > pub.month + 1:
                        year -= 1
                    if year:
                        try:
                            norm = datetime(year, month, day).date().isoformat()
                            inferred = not bool(m.group(3))
                        except ValueError:
                            pass
                elif kind == "dia_semana" and pub:
                    wd = _WEEKDAYS.index(m.group(2).lower())
                    pre = (m.group(1) or "").lower()
                    post = (m.group(3) or "").lower()
                    delta = (pub.weekday() - wd) % 7
                    if "pasado" in pre or "pasado" in post:
                        delta = delta or 7
                        norm = (pub - timedelta(days=delta)).date().isoformat()
                    elif "próximo" in pre or "próximo" in post:
                        ahead = (wd - pub.weekday()) % 7 or 7
                        norm = (pub + timedelta(days=ahead)).date().isoformat()
                    else:
                        norm = (pub - timedelta(days=delta)).date().isoformat()
                elif kind == "relativa" and pub:
                    w = m.group(1).lower()
                    off = {"anteayer": -2, "antes de ayer": -2, "ayer": -1, "anoche": -1, "hoy": 0, "esta mañana": 0,
                           "esta tarde": 0, "esta noche": 0, "esta madrugada": 0, "mañana": 1, "pasado mañana": 2}.get(w)
                    if off is not None:
                        norm = (pub + timedelta(days=off)).date().isoformat()
                elif kind == "hace" and pub:
                    n = m.group(1).lower()
                    n = int(n) if n.isdigit() else _NUMW.get(n, 1)
                    u = m.group(2).lower()
                    days = n if u.startswith("día") else 7 * n if u.startswith("semana") else 30 * n if u.startswith("mes") \
                        else 365 * n if u.startswith("año") else 0
                    norm = (pub - timedelta(days=days)).date().isoformat() if days else pub.date().isoformat()
                elif kind == "año":
                    norm = m.group(1)
                    inferred = False
                items.append({"p": pid, "expresion": expr, "tipo": kind, "normalizada": norm, "inferida": inferred if norm else None,
                              "contexto": _sentence_of(text, m.start())[:260]})
    # quitar duplicados solapados (p. ej. «jueves» dentro de «la madrugada de este jueves»)
    seen, out = set(), []
    for it in sorted(items, key=lambda x: (-len(x["expresion"]))):
        key = (it["p"], it["expresion"].lower())
        if any(it["p"] == o["p"] and it["expresion"].lower() in o["expresion"].lower() for o in out):
            continue
        if key not in seen:
            seen.add(key)
            out.append(it)
    out.sort(key=lambda x: _unit_order(x["p"]))
    for i, it in enumerate(out, 1):
        it["id"] = f"X{i}"
    return out


# --------------------------------------------------------------------------- entidades (heurísticas)

_CAP_TOKEN = re.compile(r"[A-ZÁÉÍÓÚÑ][\wáéíóúñüÁÉÍÓÚÑÜ.\-]*")
_CONNECT = {"de", "del", "la", "las", "los", "y", "e", "el"}


def entities(article) -> list[dict]:
    from ..geo import gazetteer
    found: dict[str, dict] = {}
    for pid, text in units(article, include_meta=True):
        for sent in split_sentences(text):
            toks = re.findall(r"[\wáéíóúñüÁÉÍÓÚÑÜ.\-/]+|[^\s\w]", sent)
            i = 0
            while i < len(toks):
                t = toks[i]
                article_start = (t in ("La", "El", "Los", "Las") and i + 1 < len(toks) and _CAP_TOKEN.fullmatch(toks[i + 1])
                                 and (i > 0 and toks[i - 1] not in ("«", "“", '"', "¿", "¡", "(") or
                                      gazetteer.lookup(t + " " + toks[i + 1])))
                if article_start or (_CAP_TOKEN.fullmatch(t) and t.lower() not in ("el", "la", "los", "las", "un", "una", "en", "de", "según", "por", "tras", "para", "con", "al")):
                    seq = [t]
                    j = i + 1
                    while j < len(toks):
                        if _CAP_TOKEN.fullmatch(toks[j]):
                            seq.append(toks[j]); j += 1
                        elif toks[j].lower() in _CONNECT and j + 1 < len(toks) and _CAP_TOKEN.fullmatch(toks[j + 1]):
                            seq.extend([toks[j], toks[j + 1]]); j += 2
                        else:
                            break
                    name = " ".join(seq).strip(".")
                    first = i == 0 or toks[i - 1] in ("«", "“", '"', "¿", "¡", "(")
                    prev = toks[i - 1].lower() if i > 0 else ""
                    i = j
                    if first and len(seq) == 1 and (name.lower() in L.STOPWORDS or len(name) < 3):
                        continue
                    if len(name) < 2 or name.lower() in L.STOPWORDS:
                        continue
                    low = name.lower()
                    # sigla institucional pegada a un nombre de persona: «PNP Luis Arévalo»
                    parts = name.split()
                    if len(parts) >= 3 and parts[0].isupper() and len(parts[0]) <= 6 and parts[1].lower() in L.GIVEN_NAMES:
                        for nm, kd in ((parts[0], "organizacion"), (" ".join(parts[1:]), "persona")):
                            e = found.setdefault(nm, {"nombre": nm, "tipo": kd, "menciones": 0, "unidades": []})
                            e["menciones"] += 1
                            if pid not in e["unidades"]:
                                e["unidades"].append(pid)
                        continue
                    first_low = parts[0].lower()
                    org_start = any(first_low.startswith(k) for k in ("policía", "ministerio", "hospital", "fiscalía", "municipalidad",
                                                                       "superintendencia", "cuerpo", "compañía", "empresa", "transportes",
                                                                       "universidad", "gobierno", "congreso", "defensoría", "dirección",
                                                                       "división", "unidad", "servicio", "instituto", "comisión", "poder"))
                    if org_start:
                        kind = "organizacion"
                    elif (gazetteer.lookup(parts[0]) and len(parts) == 2 and parts[1] in ("Sur", "Norte", "Este", "Oeste", "Centro", "Metropolitana")):
                        kind = "lugar"
                    elif gazetteer.lookup(name) or any(k in low for k in ("avenida", "av.", "jirón", "calle", "plaza", "panamericana",
                                                                          "carretera", "distrito", "puente", "playa", "río")):
                        kind = "lugar"
                    elif any(k in low for k in L.ORG_KEYWORDS) or (name.isupper() and 2 <= len(name) <= 7):
                        kind = "organizacion"
                    elif seq[0].lower() in L.GIVEN_NAMES or prev in L.TITLES_BEFORE_PERSON or (2 <= len([s for s in seq if s.lower() not in _CONNECT]) <= 4 and all(s[0].isupper() for s in seq)):
                        kind = "persona"
                    else:
                        kind = "otra"
                    if first and len(seq) == 1 and kind == "otra":
                        continue
                    e = found.setdefault(name, {"nombre": name, "tipo": kind, "menciones": 0, "unidades": []})
                    e["menciones"] += 1
                    if pid not in e["unidades"]:
                        e["unidades"].append(pid)
                else:
                    i += 1
    # fusionar nombres contenidos (p. ej. «Arévalo» dentro de «Luis Arévalo»)
    names = sorted(found, key=len, reverse=True)
    for short in sorted(found, key=len):
        for long in names:
            if short != long and re.search(r"\b" + re.escape(short) + r"\b", long) and found.get(short) and found.get(long) \
                    and found[short]["tipo"] == found[long]["tipo"] == "persona" and len(short.split()) == 1:
                found[long]["menciones"] += found[short]["menciones"]
                found[long]["unidades"] = sorted(set(found[long]["unidades"]) | set(found[short]["unidades"]), key=_unit_order)
                found[long].setdefault("alias", []).append(short)
                found.pop(short)
                break
    return sorted(found.values(), key=lambda e: -e["menciones"])


def count_mentions(article, aliases: list[str]) -> dict:
    """Cuenta menciones literales (sin distinguir mayúsculas ni tildes) de cualquiera de los alias."""
    alias_keys = sorted({norm_key(a) for a in aliases if a and len(a) >= 2}, key=len, reverse=True)
    if not alias_keys:
        return {"menciones": 0, "unidades": [], "primera": None, "en_titular": False, "en_subtitulo": False, "palabras_contexto": 0}
    rx = re.compile(r"(?<![\w])(" + "|".join(re.escape(a) for a in alias_keys) + r")(?![\w])")
    n, units_found, ctx_words = 0, [], 0
    for pid, text in units(article, include_meta=True):
        k = norm_key(text)
        hits = rx.findall(k)
        if hits:
            n += len(hits)
            units_found.append(pid)
            if pid.startswith("P"):
                ctx_words += count_words(text)
    body_ids = [u for u in units_found if u.startswith("P")]
    return {"menciones": n, "unidades": units_found, "primera": body_ids[0] if body_ids else None,
            "en_titular": "T" in units_found, "en_subtitulo": "S" in units_found, "palabras_contexto": ctx_words}


# --------------------------------------------------------------------------- todo junto

def compute(article) -> dict:
    return {
        "metricas": metrics(article),
        "legibilidad": readability(article),
        "frecuencias": frequencies(article),
        "bigramas": bigrams(article),
        "conectores": connectors(article),
        "cohesion": cohesion(article),
        "modalidad": modality(article),
        "verbal": verbal(article),
        "lexico": lexical_markers(article),
        "citas": quotes(article),
        "atribucion": attribution(article),
        "cifras": numbers(article),
        "temporales": temporal_expressions(article),
        "entidades": entities(article),
    }
