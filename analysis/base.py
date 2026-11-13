"""Infraestructura común de las fases: secciones, bloques de presentación y contexto.

Cada fase devuelve una estructura serializable con secciones; cada sección contiene
bloques (tablas, gráficos, mapas, textos) con su origen declarado:
* ``programatico``: cálculo exacto realizado por código;
* ``heuristico``: reglas explícitas pero aproximadas;
* ``modelo``: interpretación del modelo de lenguaje (con evidencias verificadas);
* ``mixto``: el modelo clasifica y el código cuenta o verifica.
"""
from __future__ import annotations

import traceback
from datetime import datetime

from ..llm import client as llm
from ..llm.evidence import Verifier
from ..llm.prompts import SYSTEM_RULES, articles_text

STATUS_LABELS = {
    "ok": "Analizado",
    "parcial": "Análisis incompleto",
    "no_aplicable": "No aplicable",
    "no_disponible": "Información no disponible",
    "insuficiente": "Evidencia insuficiente",
    "extraccion_incompleta": "Extracción incompleta",
    "requiere_ia": "Requiere modelo de lenguaje",
    "desactivado": "Desactivado",
    "error": "Error",
}
ORIGIN_LABELS = {
    "programatico": "Cálculo programático",
    "heuristico": "Reglas heurísticas (aproximado)",
    "modelo": "Interpretación del modelo de lenguaje",
    "mixto": "Modelo de lenguaje + verificación programática",
    "usuario": "Editado por la persona usuaria",
}


class Section:
    def __init__(self, sid: str, title: str, question: str = ""):
        self.id = sid
        self.title = title
        self.question = question
        self.status = "ok"
        self.status_note = ""
        self.blocks: list[dict] = []
        self.interpretation = ""
        self.interpretation_origin = ""

    # --- bloques ---------------------------------------------------------------------
    def add(self, kind: str, title: str = "", *, description: str = "", interpretation: str = "",
            origin: str = "programatico", **data) -> dict:
        b = {"kind": kind, "id": f"{self.id}-{len(self.blocks) + 1}", "title": title, "description": description,
             "interpretation": interpretation, "origin": origin}
        b.update(data)
        self.blocks.append(b)
        return b

    def table(self, title, columns, rows, **kw):
        """columns: [{"key","label", "type"?}] · rows: [dict]"""
        return self.add("table", title, columns=columns, rows=rows, **kw)

    def compare(self, title, rows, **kw):
        """Tabla de doble entrada: rows = [{"label", "n1", "n2", "nota"?}]"""
        return self.add("compare", title, rows=rows, **kw)

    def text(self, text, origin="modelo", title="", **kw):
        return self.add("text", title, text=text, origin=origin, **kw)

    def notice(self, status, text):
        return self.add("notice", "", status=status, status_label=STATUS_LABELS.get(status, status), text=text,
                        origin="programatico")

    def set_status(self, status: str, note: str = ""):
        self.status = status
        self.status_note = note

    def finalize(self):
        """Ajusta el estado de la sección a su contenido real."""
        notices = [b for b in self.blocks if b["kind"] == "notice"]
        content = [b for b in self.blocks if b["kind"] != "notice"]
        if self.status in ("ok", "extraccion_incompleta") and notices and not content:
            self.status = notices[0]["status"]
        elif self.status == "ok" and any(n["status"] in ("requiere_ia", "error") for n in notices):
            self.status = "parcial"
            self.status_note = self.status_note or "Parte de la sección requiere el modelo de lenguaje o no pudo completarse."

    def to_dict(self) -> dict:
        self.finalize()
        return {"id": self.id, "title": self.title, "question": self.question, "status": self.status,
                "status_label": STATUS_LABELS.get(self.status, self.status), "status_note": self.status_note,
                "blocks": self.blocks, "interpretation": self.interpretation,
                "interpretation_origin": self.interpretation_origin}


class Context:
    """Todo lo que una fase necesita para ejecutarse."""

    def __init__(self, project: dict):
        self.project = project
        self.articles = project["articles"]
        self.a1, self.a2 = self.articles
        self.f = {1: project["features"]["1"], 2: project["features"]["2"]}
        self.profile = project.get("profile") or {}
        self.plan = (self.profile.get("plan") or {})
        self.options = project.get("options") or {}
        self.relation = ((project.get("correspondence") or {}).get("final") or {}).get("relacion", "mismo")
        self.usage: list[dict] = []
        self.llm_errors: list[str] = []

    def medio(self, n: int) -> str:
        return (self.articles[n - 1].get("meta") or {}).get("medio") or f"Noticia {n}"

    def label(self, n: int) -> str:
        return f"N{n} · {self.medio(n)}"

    def partial(self, n: int | None = None) -> bool:
        arts = [self.articles[n - 1]] if n else self.articles
        return any(a.get("status") == "parcial" for a in arts)

    def section_enabled(self, sid: str) -> bool:
        return sid not in set(self.options.get("secciones_desactivadas") or [])

    def plan_status(self, sid: str) -> dict:
        return (self.plan.get(sid) or {})

    def llm_available(self) -> bool:
        return llm.available()

    def ask(self, task: str, instructions: str, schema: dict, *, extra: str = "", images=None,
            include_articles: bool = True, max_tokens: int | None = None, description: str = "") -> dict | None:
        """Llama al modelo. Devuelve el resultado con las evidencias ya verificadas, o None."""
        if not llm.available():
            return None
        context = ""
        if self.relation == "relacionados":
            context = ("ATENCIÓN: las noticias describen acontecimientos RELACIONADOS pero no idénticos. "
                       "Compara su tratamiento sin asumir que narran el mismo suceso.\n\n")
        elif self.relation == "diferentes":
            context = ("ATENCIÓN: la correspondencia entre las noticias es BAJA (la persona usuaria decidió continuar). "
                       "Pueden referirse a acontecimientos distintos: compara su tratamiento sin asumir que narran el mismo suceso "
                       "y señala cuando una diferencia se deba a que cuentan hechos diferentes.\n\n")
        prof = self.profile.get("modelo") or {}
        if prof.get("tipos"):
            tipos = ", ".join(t.get("tipo", "") for t in prof["tipos"])
            context += f"Naturaleza del acontecimiento identificada: {tipos}.\n\n"
        user = context + (articles_text(self.articles) + "\n\n" if include_articles else "") + \
            (extra + "\n\n" if extra else "") + "TAREA\n" + instructions
        try:
            out, usage = llm.call(task, SYSTEM_RULES, user, schema, images=images, max_tokens=max_tokens,
                                  description=description)
        except llm.LLMError as e:
            self.llm_errors.append(f"{task}: {e}")
            return {"__error__": str(e)}
        self.usage.append(usage)
        v = Verifier(self.articles)
        v.walk(out)
        out["__verificacion__"] = v.stats
        return out


class Phase:
    number: int = 0
    title: str = ""
    description: str = ""
    sections: list[tuple[str, str, str]] = []  # (id, título, pregunta analítica)

    def run(self, ctx: Context) -> dict:
        started = datetime.now()
        result = {"numero": self.number, "titulo": self.title, "descripcion": self.description,
                  "secciones": [], "sintesis": None, "sintesis_origen": "", "estado": "ok",
                  "errores": [], "verificacion": None}
        try:
            secs, synthesis, origin, verif = self.analyze(ctx)
            if ctx.partial():
                who = ", ".join(f"noticia {a['n']}" for a in ctx.articles if a.get("status") == "parcial")
                for s in secs:
                    if s.id != "1.1" and s.status in ("ok", "parcial"):
                        s.set_status("extraccion_incompleta", f"Extracción incompleta ({who}): los resultados pueden no reflejar el texto completo.")
            result["secciones"] = [s.to_dict() for s in secs]
            result["sintesis"] = synthesis
            result["sintesis_origen"] = origin
            result["verificacion"] = verif
        except Exception as e:  # una fase no debe bloquear las demás
            result["estado"] = "error"
            result["errores"].append(f"{type(e).__name__}: {e}")
            result["traza"] = traceback.format_exc()[-2000:]
        result["errores"] += ctx.llm_errors
        if ctx.llm_errors and result["estado"] == "ok":
            result["estado"] = "parcial"
        result["uso_modelo"] = ctx.usage
        result["generado"] = datetime.now().isoformat(timespec="seconds")
        result["duracion_s"] = round((datetime.now() - started).total_seconds(), 1)
        return result

    def analyze(self, ctx: Context):  # pragma: no cover - lo implementa cada fase
        raise NotImplementedError

    # --- utilidades compartidas -----------------------------------------------------------
    @staticmethod
    def make_sections(defs) -> dict[str, Section]:
        return {sid: Section(sid, title, q) for sid, title, q in defs}

    @staticmethod
    def no_llm(sec: Section, what: str):
        sec.notice("requiere_ia", f"{what} requiere un modelo de lenguaje, que no está configurado. "
                                  "Se muestran solo los resultados programáticos.")

    @staticmethod
    def llm_failed(sec: Section, out: dict | None, what: str) -> bool:
        if out is None:
            Phase.no_llm(sec, what)
            return True
        if "__error__" in out:
            sec.notice("error", f"No se pudo completar {what.lower()}: {out['__error__']}")
            return True
        return False


def verif_merge(*outs) -> dict:
    total = {"total": 0, "literal": 0, "corregida": 0, "aproximada": 0, "no_localizada": 0, "sin_cita": 0}
    for o in outs:
        if isinstance(o, dict) and o.get("__verificacion__"):
            for k, v in o["__verificacion__"].items():
                total[k] = total.get(k, 0) + v
    return total


def heuristic_synthesis(diffs: list[str], same: list[str], limits: list[str]) -> dict:
    return {"diferencias": diffs, "semejanzas": same, "patrones": [], "destaca_n1": "", "destaca_n2": "",
            "conclusiones": [], "limitaciones": limits}


def pct(a, b) -> float:
    return round(100 * a / b, 1) if b else 0.0


def rel_diff(a, b) -> str:
    """Describe la diferencia relativa entre dos cantidades."""
    if not a and not b:
        return "iguales (0)"
    if a == b:
        return "iguales"
    big, small, who = (a, b, 1) if a > b else (b, a, 2)
    if small == 0:
        return f"solo la noticia {who} tiene valor"
    return f"la noticia {who} supera a la otra en un {round(100 * (big - small) / small)} %"
