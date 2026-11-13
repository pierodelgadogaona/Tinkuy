"""Verificación de evidencias textuales.

Toda cita que el modelo de lenguaje aporta como evidencia se busca en el texto
extraído. Resultados posibles:
* ``literal``: el fragmento aparece tal cual en la unidad indicada.
* ``corregida``: aparece literalmente, pero en otra unidad (se corrige la referencia).
* ``aproximada``: coincide en más del 88 % con un pasaje (diferencias menores de copia).
* ``no_localizada``: no aparece; se muestra con advertencia y no sustenta conclusiones.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from ..nlp.features import units
from ..nlp.text import norm_key

UNIT_RE = re.compile(r"^(?:n?([12])\s*[-·:/ ]\s*)?([TSPHFM])\s*(\d*)$", re.I)


def normalize_ref(p) -> str:
    if p is None:
        return ""
    if isinstance(p, int):
        return f"P{p}"
    s = str(p).strip().upper().replace("PÁRRAFO", "P").replace("PARRAFO", "P").replace(" ", "")
    s = s.replace("TITULAR", "T").replace("TÍTULO", "T").replace("SUBTÍTULO", "S").replace("SUBTITULO", "S")
    m = UNIT_RE.match(s)
    if m:
        letter, num = m.group(2), m.group(3)
        return letter + num
    m = re.search(r"([TSPHFM])(\d+)", s)
    return f"{m.group(1)}{m.group(2)}" if m else s


def _clean(s: str) -> str:
    s = norm_key(s)
    s = re.sub(r"\[\s*(?:\.\.\.|…)\s*\]|\(\s*(?:\.\.\.|…)\s*\)", "…", s)
    return s.strip(' ."\'')


class Verifier:
    def __init__(self, articles: list[dict]):
        self.units: dict[int, dict[str, str]] = {}
        self.keys: dict[int, dict[str, str]] = {}
        for a in articles:
            n = a["n"]
            self.units[n] = {pid: text for pid, text in units(a, include_meta=True)}
            self.keys[n] = {pid: norm_key(t) for pid, t in self.units[n].items()}
        self.stats = {"total": 0, "literal": 0, "corregida": 0, "aproximada": 0, "no_localizada": 0, "sin_cita": 0}

    def text_of(self, n: int, pid: str) -> str:
        return self.units.get(n, {}).get(pid, "")

    def _find(self, n: int, frag: str):
        segs = [s.strip() for s in re.split(r"…|\.\.\.", frag) if len(s.strip()) >= 6]
        if not segs:
            return None
        for pid, k in self.keys.get(n, {}).items():
            if all(seg in k for seg in segs):
                return pid
        return None

    def _fuzzy(self, n: int, frag: str, prefer: str):
        best, best_pid = 0.0, None
        order = sorted(self.keys.get(n, {}).items(), key=lambda kv: kv[0] != prefer)
        L = len(frag)
        for pid, k in order:
            if not k:
                continue
            if L >= len(k):
                r = SequenceMatcher(None, frag, k).ratio()
                if r > best:
                    best, best_pid = r, pid
                continue
            step = max(1, L // 6)
            for i in range(0, len(k) - L + 1, step):
                r = SequenceMatcher(None, frag, k[i:i + L]).ratio()
                if r > best:
                    best, best_pid = r, pid
        return (best_pid, best) if best >= 0.88 else (None, best)

    def verify(self, ev: dict) -> dict:
        self.stats["total"] += 1
        try:
            n = int(str(ev.get("n", ev.get("noticia", 1))).strip().replace("N", "").replace("n", "") or 1)
        except ValueError:
            n = 1
        ev["n"] = n if n in (1, 2) else 1
        ev["p"] = normalize_ref(ev.get("p") or ev.get("unidad") or ev.get("parrafo"))
        cita = (ev.get("cita") or "").strip()
        if not cita:
            ev["verificacion"] = "sin_cita"
            self.stats["sin_cita"] += 1
            return ev
        frag = _clean(cita)
        unit_key = self.keys.get(ev["n"], {}).get(ev["p"], "")
        if unit_key and all(seg.strip() in unit_key for seg in re.split(r"…|\.\.\.", frag) if len(seg.strip()) >= 6):
            ev["verificacion"] = "literal"
            self.stats["literal"] += 1
            return ev
        pid = self._find(ev["n"], frag)
        if pid:
            ev["p_original"], ev["p"] = ev["p"], pid
            ev["verificacion"] = "corregida"
            self.stats["corregida"] += 1
            return ev
        other = 2 if ev["n"] == 1 else 1
        pid = self._find(other, frag)
        if pid:
            ev["n_original"], ev["n"], ev["p_original"], ev["p"] = ev["n"], other, ev["p"], pid
            ev["verificacion"] = "corregida"
            self.stats["corregida"] += 1
            return ev
        pid, ratio = self._fuzzy(ev["n"], frag, ev["p"])
        if pid:
            if pid != ev["p"]:
                ev["p_original"], ev["p"] = ev["p"], pid
            ev["verificacion"] = "aproximada"
            ev["similitud"] = round(ratio, 2)
            self.stats["aproximada"] += 1
            return ev
        ev["verificacion"] = "no_localizada"
        self.stats["no_localizada"] += 1
        return ev

    def walk(self, obj):
        """Verifica en su lugar cualquier diccionario con clave «cita» dentro de una estructura."""
        if isinstance(obj, dict):
            for key in ("n1", "n2"):  # evidencias anidadas bajo n1/n2 heredan el número de noticia
                sub = obj.get(key)
                if isinstance(sub, dict) and "cita" in sub and "n" not in sub:
                    sub["n"] = int(key[1])
            if "cita" in obj and ("p" in obj or "n" in obj or "unidad" in obj):
                self.verify(obj)
            for v in obj.values():
                self.walk(v)
        elif isinstance(obj, list):
            for v in obj:
                self.walk(v)
        return obj
