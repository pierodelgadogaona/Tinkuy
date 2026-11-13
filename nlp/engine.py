"""Motor morfosintáctico opcional (spaCy).

Si spaCy y un modelo español están instalados (``pip install spacy`` y
``python -m spacy download es_core_news_md``), se calculan distribuciones de
categorías gramaticales, tiempos verbales, voz y un índice sintáctico de agencia.
Si no, la aplicación usa sus reglas heurísticas y lo declara en cada análisis.
"""
from __future__ import annotations

import os
import threading
from collections import Counter

_nlp = None
_tried = False
_lock = threading.Lock()
_model_name = ""


def load():
    global _nlp, _tried, _model_name
    with _lock:
        if _tried:
            return _nlp
        _tried = True
        try:
            import spacy  # type: ignore
        except Exception:
            return None
        for name in [os.getenv("TINKUY_SPACY_MODEL", ""), "es_core_news_md", "es_core_news_sm", "es_core_news_lg"]:
            if not name:
                continue
            try:
                _nlp = spacy.load(name)
                _model_name = name
                break
            except Exception:
                continue
        return _nlp


def status() -> dict:
    nlp = load()
    if nlp is None:
        return {"motor": "heurístico", "detalle": "spaCy no está instalado: se usan reglas morfológicas explícitas "
                                                 "(terminaciones verbales, léxicos cerrados). Los recuentos gramaticales generales no se calculan."}
    return {"motor": f"spaCy ({_model_name})", "detalle": "Etiquetado morfosintáctico y dependencias con spaCy."}


POS_LABELS = {"NOUN": "sustantivos", "PROPN": "nombres propios", "VERB": "verbos", "AUX": "auxiliares",
              "ADJ": "adjetivos", "ADV": "adverbios", "PRON": "pronombres", "DET": "determinantes", "ADP": "preposiciones",
              "CCONJ": "conjunciones coordinantes", "SCONJ": "conjunciones subordinantes", "NUM": "numerales"}


def analyze(texts: list[str], actor_aliases: dict[str, list[str]] | None = None) -> dict | None:
    nlp = load()
    if nlp is None:
        return None
    text = "\n".join(texts)
    doc = nlp(text)
    pos = Counter(t.pos_ for t in doc if not t.is_punct and not t.is_space)
    tense = Counter()
    mood = Counter()
    passive = 0
    subordinate = 0
    for t in doc:
        if t.pos_ in ("VERB", "AUX"):
            for v in t.morph.get("Tense"):
                tense[v] += 1
            for v in t.morph.get("Mood"):
                mood[v] += 1
        if t.dep_ in ("nsubj:pass", "aux:pass", "expl:pass"):
            passive += 1
        if t.dep_ in ("advcl", "ccomp", "acl", "csubj", "acl:relcl"):
            subordinate += 1
    adjectives = Counter(t.lemma_.lower() for t in doc if t.pos_ == "ADJ")
    agency = {}
    if actor_aliases:
        for actor_id, aliases in actor_aliases.items():
            keys = [a.lower() for a in aliases if a]
            ag = pa = 0
            for ent in doc.noun_chunks:
                low = ent.text.lower()
                if not any(k in low for k in keys):
                    continue
                root = ent.root
                if root.dep_ == "nsubj" and root.head.pos_ in ("VERB", "AUX"):
                    ag += 1
                elif root.dep_ in ("obj", "iobj", "nsubj:pass", "obl"):
                    pa += 1
            agency[actor_id] = {"agente": ag, "paciente": pa}
    total = sum(pos.values()) or 1
    return {
        "modelo": _model_name,
        "pos": {POS_LABELS.get(k, k): v for k, v in pos.most_common() if k in POS_LABELS},
        "pos_pct": {POS_LABELS.get(k, k): round(100 * v / total, 1) for k, v in pos.items() if k in POS_LABELS},
        "tiempos": dict(tense), "modos": dict(mood), "pasivas": passive, "subordinadas": subordinate,
        "adjetivos": dict(adjectives.most_common(30)), "agencia": agency,
        "entidades": [(e.text, e.label_) for e in doc.ents][:200],
    }
