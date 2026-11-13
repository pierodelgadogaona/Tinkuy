"""API HTTP de Tinkuy (Starlette) y servidor de la interfaz."""
from __future__ import annotations

import json
import re
from datetime import datetime

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import branding, storage
from .analysis import correspondence, pipeline
from .analysis.curate import curar
from .analysis.phases import REGISTRY
from .config import settings
from .extraction import browser
from .extraction.extractor import is_analyzable, manual_article
from .geo import geocoder
from .nlp import engine
from .security.urlguard import UrlRejected, normalize_url

storage.init()

EDITABLE_KEYS = {"interpretation", "text", "diferencias", "semejanzas", "patrones", "destaca_n1", "destaca_n2", "conclusiones",
                 "limitaciones", "respuesta", "resumen_ejecutivo", "acontecimiento", "titulo", "status_note"}
META_FIELDS = {"medio", "titular", "subtitulo", "fecha_publicacion", "fecha_actualizacion", "autoria", "seccion"}


def err(msg: str, status: int = 400, code: str = "error") -> JSONResponse:
    return JSONResponse({"error": msg, "code": code}, status_code=status)


async def body(request: Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load(pid: str):
    p = storage.get_project(pid)
    if not p:
        return None, err("El proyecto no existe.", 404, "no_encontrado")
    return p, None


def busy(pid: str):
    if pipeline.is_running(pid):
        return err("Hay una tarea en curso en este proyecto. Espera a que termine.", 409, "ocupado")
    return None


# --------------------------------------------------------------------------- configuración

async def config(request: Request):
    ok, why = browser.browser_available()
    return JSONResponse({
        "llm": settings.llm_status(), "navegador": {"disponible": ok, "detalle": why},
        "geocodificacion": geocoder.status(), "pln": engine.status(),
        "fases": [{"numero": n, "titulo": ph.title, "descripcion": ph.description,
                   "secciones": [{"id": s[0], "titulo": s[1], "pregunta": s[2]} for s in ph.sections]} for n, ph in sorted(REGISTRY.items())],
        "pdf": settings.pdf_enabled, "modo_pruebas": settings.allow_private_hosts,
        "umbral_correspondencia": correspondence.UMBRAL,
    })


# --------------------------------------------------------------------------- proyectos

async def list_projects(request: Request):
    return JSONResponse(storage.list_projects())


def empty_article(n: int, url: str = "") -> dict:
    return {"n": n, "url": url, "status": "pendiente", "status_label": "Pendiente", "status_detail": "", "meta": {}, "blocks": [],
            "attempts": [], "meta_edits": {}}


async def create_project(request: Request):
    data = await body(request)
    urls, manual = {}, {}
    for n in (1, 2):
        m = data.get(f"manual{n}")
        if isinstance(m, dict) and (m.get("text") or "").strip():
            manual[n] = m
            urls[n] = (m.get("url") or "").strip()
            continue
        raw = (data.get(f"url{n}") or "").strip()
        if not raw:
            return err(f"Falta el enlace de la noticia {n} (o su texto manual).", 400, "falta_enlace")
        try:
            urls[n] = normalize_url(raw)
        except UrlRejected as e:
            return err(f"Noticia {n}: {e.message}", 400, e.code)
    if urls.get(1) and urls.get(1) == urls.get(2) and not manual:
        return err("Los dos enlaces son iguales: introduce dos noticias distintas.", 400, "duplicado")
    pid = storage.new_id()
    p = {"id": pid, "created": storage.now(), "title": "Comparación de noticias", "stage": "lectura",
         "inputs": {"url1": urls.get(1, ""), "url2": urls.get(2, "")},
         "articles": [empty_article(1, urls.get(1, "")), empty_article(2, urls.get(2, ""))],
         "features": {}, "options": {"vision": settings.vision_enabled, "geocodificacion": False,
                                     "fases_desactivadas": [], "secciones_desactivadas": []},
         "phases": {}, "edit_log": []}
    for n, m in manual.items():
        p["articles"][n - 1] = manual_article(n, m.get("text", ""), url=m.get("url", ""), titular=m.get("titular", ""),
                                              medio=m.get("medio", ""), fecha=m.get("fecha", ""), autoria=m.get("autoria", ""),
                                              seccion=m.get("seccion", ""), subtitulo=m.get("subtitulo", ""))
    storage.save_project(p)
    to_fetch = [n for n in (1, 2) if n not in manual]
    if to_fetch:
        pipeline.start_extraction(pid, to_fetch)
    else:
        pipeline.compute_features(p)
        p["stage"] = "vista_previa"
        p["title"] = pipeline._title(p)
        storage.save_project(p)
    return JSONResponse({"id": pid}, status_code=201)


async def get_project(request: Request):
    p, e = load(request.path_params["pid"])
    if e:
        return e
    p["running"] = pipeline.is_running(p["id"])
    for a in p.get("articles") or []:
        branding.ensure(a)  # proyectos anteriores sin color de medio: se asigna sin red (no se guarda)
    p.pop("features", None) if request.query_params.get("ligero") else None
    return JSONResponse(p if request.query_params.get("crudo") else curar(p))


async def get_status(request: Request):
    p, e = load(request.path_params["pid"])
    if e:
        return e
    return JSONResponse({"stage": p.get("stage"), "progress": p.get("progress"), "running": pipeline.is_running(p["id"]),
                         "updated": p.get("updated")})


async def delete_project(request: Request):
    pid = request.path_params["pid"]
    if (b := busy(pid)):
        return b
    storage.delete_project(pid)
    return JSONResponse({"ok": True})


# --------------------------------------------------------------------------- artículos

async def refetch(request: Request):
    pid, n = request.path_params["pid"], int(request.path_params["n"])
    if (b := busy(pid)):
        return b
    p, e = load(pid)
    if e:
        return e
    data = await body(request)
    if data.get("url"):
        try:
            p["inputs"][f"url{n}"] = normalize_url(data["url"])
        except UrlRejected as ex:
            return err(ex.message, 400, ex.code)
    p["stage"] = "lectura"
    p["correspondence"] = None
    storage.save_project(p)
    pipeline.start_extraction(pid, [n])
    return JSONResponse({"ok": True})


async def manual(request: Request):
    pid, n = request.path_params["pid"], int(request.path_params["n"])
    if (b := busy(pid)):
        return b
    p, e = load(pid)
    if e:
        return e
    d = await body(request)
    if len((d.get("text") or "").split()) < 5:
        return err("Introduce el texto del artículo.", 400, "texto_vacio")
    prev = p["articles"][n - 1]
    url = d.get("url") or prev.get("url") or ""
    art = manual_article(n, d.get("text", ""), url=url, titular=d.get("titular") or (prev.get("meta") or {}).get("titular", ""),
                         medio=d.get("medio") or (prev.get("meta") or {}).get("medio", ""), fecha=d.get("fecha", ""),
                         autoria=d.get("autoria", ""), seccion=d.get("seccion", ""), subtitulo=d.get("subtitulo", ""))
    p["articles"][n - 1] = art
    pipeline.compute_features(p)
    p["stage"] = "vista_previa"
    p["correspondence"] = None
    p["title"] = pipeline._title(p)
    storage.save_project(p)
    return JSONResponse(p)


async def patch_meta(request: Request):
    pid, n = request.path_params["pid"], int(request.path_params["n"])
    if (b := busy(pid)):
        return b
    p, e = load(pid)
    if e:
        return e
    d = await body(request)
    art = p["articles"][n - 1]
    for k, v in d.items():
        if k not in META_FIELDS:
            continue
        if k == "autoria" and isinstance(v, str):
            v = [x.strip() for x in v.split(",") if x.strip()]
        if k in ("fecha_publicacion", "fecha_actualizacion") and v:
            from .extraction.extractor import parse_date
            parsed = parse_date(v)
            if not parsed:
                return err(f"No se reconoce la fecha «{v}». Usa el formato AAAA-MM-DD o AAAA-MM-DDTHH:MM.", 400, "fecha")
            v = parsed
        art.setdefault("meta_edits", {})
        if k not in art["meta_edits"]:
            art["meta_edits"][k] = {"original": art["meta"].get(k), "editado": storage.now()}
        art["meta"][k] = v
        art.setdefault("meta_sources", {})[k] = "corrección manual"
    pipeline.compute_features(p)
    p["title"] = pipeline._title(p)
    storage.save_project(p)
    return JSONResponse(p)


# --------------------------------------------------------------------------- correspondencia y análisis

async def run_correspondence(request: Request):
    pid = request.path_params["pid"]
    if (b := busy(pid)):
        return b
    p, e = load(pid)
    if e:
        return e
    bad = [a for a in p["articles"] if not is_analyzable(a)]
    if bad:
        return err("Antes de continuar, todas las noticias deben haberse leído (completa o parcialmente) o introducido manualmente: " +
                   "; ".join(f"noticia {a['n']}: {a.get('status_label')}" for a in bad), 400, "no_analizable")
    pipeline.start_correspondence(pid)
    return JSONResponse({"ok": True})


async def confirm_correspondence(request: Request):
    """La persona usuaria decide continuar cuando la correspondencia queda por debajo del umbral."""
    pid = request.path_params["pid"]
    p, e = load(pid)
    if e:
        return e
    d = await body(request)
    c = p.get("correspondence") or {}
    final = c.get("final")
    if not final:
        return err("Aún no se ha comprobado la correspondencia.", 400, "sin_correspondencia")
    rel = d.get("relacion") or final["relacion"]
    if rel not in ("mismo", "relacionados", "diferentes"):
        return err("Relación no válida.", 400)
    first = not final.get("confirmada")
    final.update({"relacion": rel, "confirmada": True, "confirmada_en": final.get("confirmada_en") or storage.now(),
                  "decision": final.get("decision") or "usuario",
                  "modificada_por_usuario": rel != (c.get("modelo") or c.get("heuristica") or {}).get("relacion")})
    final["etiqueta"] = correspondence.RELATION_LABELS[rel]
    if first or p.get("stage") in ("correspondencia", "vista_previa", "lectura"):
        p["stage"] = "configuracion"
    storage.save_project(p)
    return JSONResponse(p)


async def patch_options(request: Request):
    pid = request.path_params["pid"]
    p, e = load(pid)
    if e:
        return e
    d = await body(request)
    opts = p.setdefault("options", {})
    for k in ("vision", "geocodificacion"):
        if k in d:
            opts[k] = bool(d[k])
    for k in ("fases_desactivadas", "secciones_desactivadas"):
        if k in d and isinstance(d[k], list):
            opts[k] = [str(x) for x in d[k]]
    storage.save_project(p)
    return JSONResponse(opts)


def _ready_for_analysis(p) -> JSONResponse | None:
    final = ((p.get("correspondence") or {}).get("final") or {})
    if not final:
        return err("Primero hay que comprobar la correspondencia entre las noticias.", 400, "sin_correspondencia")
    if final.get("confirmada"):
        return None
    # proyectos anteriores a la regla del umbral: se mantenía la lógica antigua
    if "porcentaje" not in final and not final.get("requiere_confirmacion") and final.get("relacion") != "diferentes":
        return None
    return err(f"La correspondencia es del {final.get('porcentaje', 0)} % (umbral: {correspondence.UMBRAL} %). "
               "Decide si continúas con el análisis o revisas las noticias.", 400, "sin_confirmar")


async def run_analysis(request: Request):
    pid = request.path_params["pid"]
    if (b := busy(pid)):
        return b
    p, e = load(pid)
    if e:
        return e
    if (r := _ready_for_analysis(p)):
        return r
    pipeline.start_analysis(pid)
    return JSONResponse({"ok": True})


async def rerun_phase(request: Request):
    pid, n = request.path_params["pid"], int(request.path_params["n"])
    if (b := busy(pid)):
        return b
    p, e = load(pid)
    if e:
        return e
    if n not in REGISTRY:
        return err("Fase inexistente.", 404)
    if (r := _ready_for_analysis(p)):
        return r
    pipeline.start_analysis(pid, phases=[n], rerun_profile=not p.get("profile"))
    return JSONResponse({"ok": True})


async def edit(request: Request):
    pid = request.path_params["pid"]
    if (b := busy(pid)):
        return b
    p, e = load(pid)
    if e:
        return e
    d = await body(request)
    path = d.get("path")
    if not isinstance(path, list) or not path or path[0] not in ("phases", "synthesis"):
        return err("Ruta de edición no válida.", 400)
    if str(path[-1]) not in EDITABLE_KEYS and not (len(path) >= 2 and str(path[-2]) in EDITABLE_KEYS):
        return err("Ese campo no es editable.", 400)
    node = p
    try:
        for k in path[:-1]:
            node = node[int(k)] if isinstance(node, list) else node[str(k)]
        last = path[-1]
        key = int(last) if isinstance(node, list) else str(last)
        original = node[key] if (isinstance(node, list) and key < len(node)) or (isinstance(node, dict) and key in node) else None
        value = d.get("value")
        if isinstance(original, list) and isinstance(value, str):
            value = [x.strip(" •-") for x in value.split("\n") if x.strip(" •-")]
        node[key] = value
    except (KeyError, IndexError, ValueError, TypeError):
        return err("No se encontró el elemento a editar.", 404)
    p.setdefault("edit_log", []).append({"ruta": path, "original": original, "editado": storage.now()})
    if isinstance(node, dict):
        node.setdefault("_editados", [])
        if str(last) not in node["_editados"]:
            node["_editados"].append(str(last))
    storage.save_project(p)
    return JSONResponse({"ok": True, "value": value})


async def move_place(request: Request):
    """Corrección manual de una ubicación del mapa (fase 4)."""
    pid = request.path_params["pid"]
    if (b := busy(pid)):
        return b
    p, e = load(pid)
    if e:
        return e
    d = await body(request)
    try:
        lat, lon = float(d["lat"]), float(d["lon"])
        assert -90 <= lat <= 90 and -180 <= lon <= 180
    except Exception:
        return err("Coordenadas no válidas.", 400)
    pt_id, n = d.get("id"), 0
    for s in (p.get("phases", {}).get("4", {}) or {}).get("secciones", []):
        for b in s.get("blocks", []):
            for pt in b.get("points", []) if b.get("kind") == "map" else []:
                if pt.get("id") == pt_id:
                    pt.update({"lat": lat, "lon": lon, "aproximada": bool(d.get("aproximada", False)), "fuente": "Corrección manual",
                               "nota": (d.get("nota") or "Ubicación corregida por la persona usuaria.")})
                    n += 1
    if not n:
        return err("No se encontró ese lugar en el mapa.", 404)
    p.setdefault("edit_log", []).append({"ruta": ["phases", "4", "lugar", pt_id], "original": None, "editado": storage.now()})
    storage.save_project(p)
    return JSONResponse({"ok": True})


# --------------------------------------------------------------------------- versiones e importación

async def versions(request: Request):
    pid = request.path_params["pid"]
    p, e = load(pid)
    if e:
        return e
    if request.method == "POST":
        d = await body(request)
        v = storage.save_version(pid, d.get("label") or f"Versión del {datetime.now():%d/%m/%Y %H:%M}", p)
        return JSONResponse(v, status_code=201)
    return JSONResponse(storage.list_versions(pid))


async def restore_version(request: Request):
    pid, vid = request.path_params["pid"], request.path_params["vid"]
    if (b := busy(pid)):
        return b
    data = storage.get_version(pid, vid)
    if not data:
        return err("Versión no encontrada.", 404)
    current = storage.get_project(pid)
    if current:
        storage.save_version(pid, f"Copia automática antes de restaurar ({datetime.now():%d/%m %H:%M})", current)
    data["id"] = pid
    data.pop("running", None)
    storage.save_project(data)
    return JSONResponse(data)


async def import_project(request: Request):
    d = await body(request)
    if d.get("formato") != "tinkuy" or not isinstance(d.get("proyecto"), dict):
        return err("El archivo no es un proyecto exportado por Tinkuy.", 400, "formato")
    p = d["proyecto"]
    if not isinstance(p.get("articles"), list) or len(p["articles"]) != 2:
        return err("El proyecto importado está incompleto.", 400, "formato")
    p["id"] = storage.new_id()
    p["title"] = (p.get("title") or "Proyecto importado") + " (importado)"
    p.pop("running", None)
    if not p.get("features"):
        pipeline.compute_features(p)
    storage.save_project(p)
    return JSONResponse({"id": p["id"]}, status_code=201)


# --------------------------------------------------------------------------- exportación

def _slug(p) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (p.get("title") or "tinkuy").lower())[:60].strip("-") or "tinkuy"


async def export(request: Request):
    pid, fmt = request.path_params["pid"], request.path_params["fmt"]
    p, e = load(pid)
    if e:
        return e
    name = f"tinkuy-{_slug(p)}"
    if fmt == "json":
        payload = {"formato": "tinkuy", "version": 1, "exportado": storage.now(), "proyecto": p}
        return Response(json.dumps(payload, ensure_ascii=False, indent=1), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{name}.json"'})
    if fmt == "xlsx":
        from .export.xlsx_export import build_xlsx
        data = await run_in_threadpool(build_xlsx, curar(p))
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
    base = f"http://127.0.0.1:{request.url.port or settings.port}"
    if fmt == "pdf":
        from .export.pdf import build_pdf
        try:
            data = await run_in_threadpool(build_pdf, base, pid)
        except Exception as ex:
            return err(f"No se pudo generar el PDF: {ex}. Usa «Imprimir / Guardar como PDF» desde el navegador.", 500, "pdf")
        return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    if fmt == "docx":
        from .export.docx_export import build_docx
        data, note = await run_in_threadpool(build_docx, curar(p), base)
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f'attachment; filename="{name}.docx"', "X-Tinkuy-Nota": note.encode("ascii", "ignore").decode()})
    return err("Formato no soportado.", 400)


# --------------------------------------------------------------------------- interfaz

async def index(request: Request):
    return FileResponse(settings.frontend_dir / "index.html")


routes = [
    Route("/api/config", config),
    Route("/api/projects", list_projects, methods=["GET"]),
    Route("/api/projects", create_project, methods=["POST"]),
    Route("/api/import", import_project, methods=["POST"]),
    Route("/api/projects/{pid}", get_project, methods=["GET"]),
    Route("/api/projects/{pid}", delete_project, methods=["DELETE"]),
    Route("/api/projects/{pid}/status", get_status),
    Route("/api/projects/{pid}/articles/{n:int}/refetch", refetch, methods=["POST"]),
    Route("/api/projects/{pid}/articles/{n:int}/manual", manual, methods=["POST"]),
    Route("/api/projects/{pid}/articles/{n:int}/meta", patch_meta, methods=["PATCH"]),
    Route("/api/projects/{pid}/correspondence", run_correspondence, methods=["POST"]),
    Route("/api/projects/{pid}/correspondence/confirm", confirm_correspondence, methods=["POST"]),
    Route("/api/projects/{pid}/options", patch_options, methods=["PATCH"]),
    Route("/api/projects/{pid}/analysis", run_analysis, methods=["POST"]),
    Route("/api/projects/{pid}/phases/{n:int}/rerun", rerun_phase, methods=["POST"]),
    Route("/api/projects/{pid}/edit", edit, methods=["PATCH"]),
    Route("/api/projects/{pid}/places", move_place, methods=["PATCH"]),
    Route("/api/projects/{pid}/versions", versions, methods=["GET", "POST"]),
    Route("/api/projects/{pid}/versions/{vid}/restore", restore_version, methods=["POST"]),
    Route("/api/projects/{pid}/export/{fmt}", export),
    Route("/", index),
    Mount("/", StaticFiles(directory=str(settings.frontend_dir)), name="static"),
]

app = Starlette(routes=routes, middleware=[Middleware(GZipMiddleware, minimum_size=2000)])
