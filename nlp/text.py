"""Utilidades de texto en español: tokenización, oraciones, sílabas, raíces (Snowball)."""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

WORD_RE = re.compile(r"\w+(?:[.,:'’\-]\w+)*", re.UNICODE)
ALPHA_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", re.UNICODE)

ABBREVIATIONS = [
    "Sr", "Sra", "Srta", "Dr", "Dra", "Lic", "Ing", "Arq", "Av", "Jr", "Mg", "Mons", "Pdte", "Gral", "Crnel", "Cmdte",
    "Cap", "Tte", "Sgto", "My", "Sto", "Sta", "St", "Prof", "Ud", "Uds", "Vd", "Cía", "Cia", "Dpto", "Depto", "aprox",
    "núm", "Núm", "nro", "Nro", "No", "pág", "págs", "etc", "vs", "Ltda", "Mz", "Lt", "Urb", "AA.HH", "Prov", "Reg",
]
_ABBR_RE = re.compile(r"\b(" + "|".join(re.escape(a) for a in ABBREVIATIONS) + r")\.", re.UNICODE)
_AMPM_RE = re.compile(r"\b([ap])\.\s?m\.", re.I)
_INITIAL_RE = re.compile(r"\b([A-ZÁÉÍÓÚÑ])\.(?=\s?[A-ZÁÉÍÓÚÑ])")
_MULTI_ABBR = re.compile(r"\b(EE\.\s?UU|S\.\s?A\.\s?C|S\.\s?A|Ud|S/)\.", re.UNICODE)
_SENT_SPLIT = re.compile(r"(?<=[.!?…])[\"»”’)\]]*\s+(?=[«“\"¿¡(\[]?[A-ZÁÉÍÓÚÑ0-9])")
PH = "⁣"  # separador invisible usado como marcador temporal


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "")
    s = s.replace(" ", " ").replace("​", "")
    return re.sub(r"\s+", " ", s).strip()


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm_key(s: str) -> str:
    """Forma comparable: minúsculas, sin tildes, comillas unificadas y espacios colapsados."""
    s = normalize(s).lower()
    s = re.sub(r"[«»“”\"‘’'`´]", '"', s)
    s = re.sub(r"[–—]", "-", s)
    return strip_accents(s)


def words(text: str) -> list[str]:
    return WORD_RE.findall(text or "")


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def alpha_tokens(text: str) -> list[str]:
    return ALPHA_RE.findall(text or "")


def split_sentences(text: str) -> list[str]:
    t = normalize(text)
    if not t:
        return []
    t = _AMPM_RE.sub(lambda m: f"{m.group(1)}{PH} m{PH}", t)
    t = _MULTI_ABBR.sub(lambda m: m.group(1).replace(".", PH) + PH, t)
    t = _ABBR_RE.sub(lambda m: m.group(1) + PH, t)
    t = _INITIAL_RE.sub(lambda m: m.group(1) + PH, t)
    t = re.sub(r"(\d)\.(\d)", lambda m: m.group(1) + PH + m.group(2), t)
    parts = [p.replace(PH, ".").strip() for p in _SENT_SPLIT.split(t)]
    return [p for p in parts if p]


# --------------------------------------------------------------------------- sílabas

_STRONG = set("aeoáéó")
_WEAK = set("iuü")
_WEAK_ACC = set("íú")
_VOWELS = _STRONG | _WEAK | _WEAK_ACC


@lru_cache(maxsize=50000)
def syllables(word: str) -> int:
    w = word.lower()
    w = re.sub(r"[^a-záéíóúüñ]", "", w)
    if not w:
        return 0
    w = re.sub(r"(?<=[qg])u(?=[eéií])", "", w)  # «que», «gui»: u muda
    if w.endswith("y") and len(w) > 1 and w[-2] in _VOWELS:
        w = w[:-1] + "i"  # «hoy», «rey»
    count, prev = 0, ""
    for ch in w:
        if ch in _VOWELS:
            if not prev:
                count += 1
            else:
                if (prev in _STRONG and ch in _STRONG) or prev in _WEAK_ACC or ch in _WEAK_ACC:
                    count += 1  # hiato
                elif prev in _WEAK and ch in _WEAK and prev == ch:
                    count += 1
            prev = ch
        else:
            prev = ""
    return max(1, count)


# --------------------------------------------------------------------------- Snowball español

_V = "aeiouáéíóúü"


def _rv(w: str) -> int:
    if len(w) < 2:
        return len(w)
    if w[1] not in _V:
        for i in range(2, len(w)):
            if w[i] in _V:
                return i + 1
        return len(w)
    if w[0] in _V and w[1] in _V:
        for i in range(2, len(w)):
            if w[i] not in _V:
                return i + 1
        return len(w)
    return 3


def _r1(w: str) -> int:
    for i in range(1, len(w)):
        if w[i] not in _V and w[i - 1] in _V:
            return i + 1
    return len(w)


def _r2(w: str) -> int:
    r1 = _r1(w)
    for i in range(r1 + 1, len(w)):
        if w[i] not in _V and w[i - 1] in _V:
            return i + 1
    return len(w)


_STEP0 = sorted("me se sela selo selas selos la le lo las les los nos".split(), key=len, reverse=True)
_STEP1 = [
    (sorted("anza anzas ico ica icos icas ismo ismos able ables ible ibles ista istas oso osa osos osas amiento amientos imiento imientos".split(), key=len, reverse=True), "del"),
    (sorted("adora ador ación adoras adores aciones ante antes ancia ancias".split(), key=len, reverse=True), "ic"),
    (["logías", "logía"], "log"),
    (["uciones", "ución"], "u"),
    (["encias", "encia"], "ente"),
    (["amente"], "amente"),
    (["mente"], "mente"),
    (["idades", "idad"], "idad"),
    (["ivas", "ivos", "iva", "ivo"], "iv"),
]
_STEP2A = sorted("ya ye yan yen yeron yendo yo yó yas yes yais yamos".split(), key=len, reverse=True)
_STEP2B_GU = ["éis", "emos", "en", "es"]
_STEP2B = sorted("""arían arías arán arás aríais aría aréis aríamos aremos ará aré erían erías erán erás eríais ería eréis
eríamos eremos erá eré irían irías irán irás iríais iría iréis iríamos iremos irá iré aba ada ida ía ara iera ad ed id ase iese
aste iste an aban ían aran ieran asen iesen aron ieron ado ido ando iendo ió ar er ir as abas adas idas ías aras ieras ases
ieses ís áis abais íais arais ierais aseis ieseis asteis isteis ados idos amos ábamos íamos imos áramos iéramos iésemos ásemos
en es éis emos""".split(), key=len, reverse=True)
_ACC = str.maketrans("áéíóú", "aeiou")


@lru_cache(maxsize=100000)
def stem(word: str) -> str:
    w = word.lower()
    if len(w) <= 3:
        return w.translate(_ACC)
    rv, r1, r2 = _rv(w), _r1(w), _r2(w)
    # paso 0: pronombres enclíticos
    for suf in _STEP0:
        if w.endswith(suf):
            base = w[: -len(suf)]
            for pre in ("iéndo", "ándo", "ár", "ér", "ír"):
                if base.endswith(pre) and len(base) - len(pre) >= rv:
                    w = base[: -len(pre)] + pre.translate(_ACC)
                    break
            else:
                for pre in ("ando", "iendo", "ar", "er", "ir"):
                    if base.endswith(pre) and len(base) - len(pre) >= rv:
                        w = base
                        break
                else:
                    if base.endswith("uyendo") and len(base) - 5 >= rv:
                        w = base
            break
    rv, r1, r2 = _rv(w), _r1(w), _r2(w)
    done1 = False
    for sufs, action in _STEP1:
        suf = next((s for s in sufs if w.endswith(s)), None)
        if not suf:
            continue
        pos = len(w) - len(suf)
        if action == "del" and pos >= r2:
            w = w[:pos]; done1 = True
        elif action == "ic" and pos >= r2:
            w = w[:pos]; done1 = True
            if w.endswith("ic") and len(w) - 2 >= r2:
                w = w[:-2]
        elif action == "log" and pos >= r2:
            w = w[:pos] + "log"; done1 = True
        elif action == "u" and pos >= r2:
            w = w[:pos] + "u"; done1 = True
        elif action == "ente" and pos >= r2:
            w = w[:pos] + "ente"; done1 = True
        elif action == "amente" and pos >= r1:
            w = w[:pos]; done1 = True
            if w.endswith("iv") and len(w) - 2 >= r2:
                w = w[:-2]
                if w.endswith("at") and len(w) - 2 >= r2:
                    w = w[:-2]
            else:
                for pre in ("os", "ic", "ad"):
                    if w.endswith(pre) and len(w) - 2 >= r2:
                        w = w[:-2]
                        break
        elif action == "mente" and pos >= r2:
            w = w[:pos]; done1 = True
            for pre in ("ante", "able", "ible"):
                if w.endswith(pre) and len(w) - len(pre) >= r2:
                    w = w[: -len(pre)]
                    break
        elif action == "idad" and pos >= r2:
            w = w[:pos]; done1 = True
            for pre in ("abil", "ic", "iv"):
                if w.endswith(pre) and len(w) - len(pre) >= r2:
                    w = w[: -len(pre)]
                    break
        elif action == "iv" and pos >= r2:
            w = w[:pos]; done1 = True
            if w.endswith("at") and len(w) - 2 >= r2:
                w = w[:-2]
        break
    if not done1:
        rv = _rv(w)
        done2a = False
        for suf in _STEP2A:
            if w.endswith(suf) and len(w) - len(suf) >= rv and w[: -len(suf)].endswith("u"):
                w = w[: -len(suf)]
                done2a = True
                break
        if not done2a:
            for suf in _STEP2B:
                if w.endswith(suf) and len(w) - len(suf) >= rv:
                    w = w[: -len(suf)]
                    if suf in _STEP2B_GU and w.endswith("gu"):
                        w = w[:-1]
                    break
    rv = _rv(w)
    for suf in ("os", "a", "o", "á", "í", "ó"):
        if w.endswith(suf) and len(w) - len(suf) >= rv:
            w = w[: -len(suf)]
            break
    else:
        for suf in ("e", "é"):
            if w.endswith(suf) and len(w) - 1 >= rv:
                w = w[:-1]
                if w.endswith("gu") and len(w) - 1 >= rv:
                    w = w[:-1]
                break
    return w.translate(_ACC)


# --------------------------------------------------------------------------- conjugación declarativa

def declarative_forms(infinitives: list[str], irregular: dict[str, list[str]], ambiguous: set[str]) -> dict[str, str]:
    """Genera formas frecuentes en prensa (3.ª persona) -> infinitivo."""
    forms: dict[str, str] = {}
    for inf in infinitives:
        if inf in irregular:
            for f in irregular[inf]:
                forms[f] = inf
            continue
        stemv, end = inf[:-2], inf[-2:]
        if end == "ar":
            cands = [stemv + "ó", stemv + "aron", stemv + "a", stemv + "an", stemv + "aba", stemv + "aban",
                     stemv + "ado", stemv + "ará", stemv + "arán", stemv + "aría", stemv + "arían"]
        else:
            cands = [stemv + "ió", stemv + "ieron", stemv + "e", stemv + "en", stemv + "ía", stemv + "ían",
                     stemv + "ido", stemv + inf[-2] + "rá", stemv + inf[-2] + "rán", stemv + inf[-2] + "ría"]
        for c in cands:
            # ortografía: añadir -> añadió; explicar -> explicó (sin cambios); agregar -> agregó
            forms[c] = inf
    for a in ambiguous:
        forms.pop(a, None)
    return forms
