"""Orquestación de tareas en segundo plano con progreso real.

Cada tarea (lectura, correspondencia, perfil, fases, síntesis) registra su estado
(pendiente, en curso, completada, error, omitida) en el proyecto. El porcentaje que
se muestra es el número de tareas terminadas sobre el total: no se inventa.
"""
from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from .. import storage
from ..config import settings
from ..extraction.extractor import extract_article, is_analyzable
from ..nlp import features as F
from . import correspondence, profile, synthesis
from .base import Context
from .phases import REGISTRY

_locks: dict[str, threading.Lock] = {}
_running: set[str] = set()
_glock = threading.Lock()


def _plock(pid: str) -> threading.Lock:
    with _glock:
        return _locks.setdefault(pid, threading.Lock())


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_running(pid: str) -> bool:
    return pid in _running


class Progress:
    def __init__(self, pid: str, stage: str, tasks: list[tuple[str, str]]):
        self.pid = pid
        self.data = {"etapa": stage, "inicio": now(), "fin": None, "estado": "en_curso",
                     "tareas": [{"id": t, "label": l, "estado": "pendiente", "detalle": "", "inicio": None, "fin": None} for t, l in tasks]}
        self.lock = threading.Lock()

    def update(self, project: dict, tid: str, estado: str, detalle: str = ""):
        with self.lock:
            for t in self.data["tareas"]:
                if t["id"] == tid:
                    t["estado"] = estado
                    if detalle:
                        t["detalle"] = detalle
                    if estado == "en_curso":
                        t["inicio"] = now()
                    elif estado in ("completada", "error", "omitida"):
                        t["fin"] = now()
            done = sum(1 for t in self.data["tareas"] if t["estado"] in ("completada", "error", "omitida"))
            self.data["completadas"] = done
            self.data["total"] = len(self.data["tareas"])
            project["progress"] = self.data
            storage.save_project(project)

    def apply(self, project: dict, fn):
        """Modifica el proyecto bajo el mismo cerrojo que el guardado (evita condiciones de carrera)."""
        with self.lock:
            fn(project)

    def finish(self, project: dict, estado: str = "completado"):
        with self.lock:
            self.data["fin"] = now()
            self.data["estado"] = estado
            project["progress"] = self.data
            storage.save_project(project)


def compute_features(project: dict):
    project["features"] = {str(a["n"]): F.compute(a) for a in project["articles"] if is_analyzable(a)}


def _run_bg(pid: str, fn):
    def wrapper():
        with _plock(pid):
            _running.add(pid)
            try:
                fn()
            except Exception:
                p = storage.get_project(pid)
                if p:
                    p.setdefault("errors", []).append({"momento": now(), "error": traceback.format_exc()[-1500:]})
                    if p.get("progress"):
                        p["progress"]["estado"] = "error"
                    storage.save_project(p)
            finally:
                _running.discard(pid)
    threading.Thread(target=wrapper, daemon=True).start()


# --------------------------------------------------------------------------- lectura

def start_extraction(pid: str, which: list[int] | None = None):
    def job():
        p = storage.get_project(pid)
        which_ = which or [1, 2]
        prog = Progress(pid, "lectura", [(f"leer{n}", f"Leyendo la noticia {n}") for n in which_] + [("procesar", "Procesando el texto")])
        for n in which_:
            prog.update(p, f"leer{n}", "en_curso")
            url = p["inputs"].get(f"url{n}", "")
            art = extract_article(url, n)
            p = storage.get_project(pid) or p
            p["articles"][n - 1] = art
            prog.update(p, f"leer{n}", "completada" if is_analyzable(art) else "error", art.get("status_label", ""))
        prog.update(p, "procesar", "en_curso")
        compute_features(p)
        p["stage"] = "vista_previa"
        p["title"] = _title(p)
        prog.update(p, "procesar", "completada")
        prog.finish(p)
    _run_bg(pid, job)


def _title(p: dict) -> str:
    ms = [((a or {}).get("meta") or {}).get("medio") or f"Noticia {i + 1}" for i, a in enumerate(p.get("articles") or [{}, {}])]
    t = ((p.get("articles") or [{}])[0] or {}).get("meta", {}).get("titular") or ""
    if len(t) > 80:
        t = t[:80].rsplit(" ", 1)[0] + "…"
    return f"{ms[0]} · {ms[1]}" + (f" — {t}" if t else "")


# --------------------------------------------------------------------------- correspondencia

def start_correspondence(pid: str):
    def job():
        p = storage.get_project(pid)
        prog = Progress(pid, "correspondencia", [("corr", "Identificando el acontecimiento de cada noticia")])
        prog.update(p, "corr", "en_curso")
        if not p.get("features") or len(p["features"]) < 2:
            compute_features(p)
        p["correspondence"] = correspondence.run(p)
        final = p["correspondence"]["final"]
        # regla del umbral: a partir del 40 % el análisis continúa solo; por debajo, decide la persona usuaria
        p["stage"] = "configuracion" if final.get("confirmada") else "correspondencia"
        prog.update(p, "corr", "completada", f"{final['porcentaje']} % de correspondencia")
        prog.finish(p)
    _run_bg(pid, job)


# --------------------------------------------------------------------------- análisis

def start_analysis(pid: str, phases: list[int] | None = None, rerun_profile: bool = True):
    def job():
        p = storage.get_project(pid)
        targets = phases or [n for n in sorted(REGISTRY) if str(n) not in set(map(str, (p.get("options") or {}).get("fases_desactivadas") or []))]
        tasks = []
        if rerun_profile:
            tasks.append(("perfil", "Preparando el análisis: naturaleza del acontecimiento"))
        tasks += [(f"fase{n}", f"Fase {n}. {REGISTRY[n].title}") for n in targets]
        tasks += [("sintesis", "Construyendo la síntesis y el informe final")]
        prog = Progress(pid, "analisis", tasks)
        p["stage"] = "analisis"
        if rerun_profile:
            prog.update(p, "perfil", "en_curso")
            p["profile"] = profile.run(p)
            prog.update(p, "perfil", "completada", ", ".join(t.get("etiqueta") or S_(t.get("tipo")) for t in p["profile"]["tipos"]) or "sin categoría")
        p.setdefault("phases", {})

        def run_phase(n):
            prog.update(p, f"fase{n}", "en_curso")
            ctx = Context(p)
            res = REGISTRY[n].run(ctx)
            prog.apply(p, lambda proj: proj["phases"].__setitem__(str(n), res))
            estado = {"ok": "completada", "parcial": "completada", "error": "error"}.get(res["estado"], "completada")
            det = "; ".join(res.get("errores", [])[:2]) if res.get("errores") else ""
            prog.update(p, f"fase{n}", estado, det)

        with ThreadPoolExecutor(max_workers=max(1, settings.llm_concurrency)) as ex:
            list(ex.map(run_phase, targets))
        prog.update(p, "sintesis", "en_curso")
        p["synthesis"] = synthesis.run(p)
        p["stage"] = "informe"
        p["analizado"] = now()
        prog.update(p, "sintesis", "completada")
        prog.finish(p)
    _run_bg(pid, job)


def S_(x):
    return str(x or "")
