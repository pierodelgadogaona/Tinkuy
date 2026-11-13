"""Lectura mediante navegador automatizado (Chromium vía Playwright) para páginas
que construyen el contenido con JavaScript.

Cada solicitud que hace la página (documento, scripts, XHR) se valida con el
mismo control SSRF que la descarga directa; se bloquean imágenes, fuentes y
vídeo para acelerar la carga. No se rellenan formularios ni se intenta superar
muros de suscripción, inicios de sesión o desafíos antibots.
"""
from __future__ import annotations

import threading
from urllib.parse import urlsplit

from ..config import settings
from ..security.urlguard import UrlRejected, check_url

_lock = threading.Lock()


def browser_available() -> tuple[bool, str]:
    if not settings.browser_fallback:
        return False, "Desactivado (TINKUY_BROWSER=0)."
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False, "Playwright no está instalado (pip install playwright && playwright install chromium)."
    return True, ""


def render(url: str, *, timeout_ms: int = 30000) -> dict:
    ok, why = browser_available()
    if not ok:
        return {"ok": False, "error": why, "error_code": "sin_navegador"}
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import sync_playwright

    allow_private = settings.allow_private_hosts
    checked_hosts: dict[str, bool] = {}

    def allowed(u: str) -> bool:
        if u.startswith(("data:", "blob:", "about:")):
            return True
        host = urlsplit(u).netloc
        if host in checked_hosts:
            return checked_hosts[host]
        try:
            check_url(u, allow_private=allow_private)
            checked_hosts[host] = True
        except UrlRejected:
            checked_hosts[host] = False
        return checked_hosts[host]

    try:
        check_url(url, allow_private=allow_private)
    except UrlRejected as e:
        return {"ok": False, "error": e.message, "error_code": e.code}

    with _lock:  # un navegador a la vez: limita memoria
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    ctx = browser.new_context(user_agent=settings.user_agent, locale="es-PE",
                                              viewport={"width": 1280, "height": 2000})
                    page = ctx.new_page()

                    def on_route(route):
                        req = route.request
                        if req.resource_type in ("image", "media", "font"):
                            return route.abort()
                        if not allowed(req.url):
                            return route.abort()
                        return route.continue_()

                    page.route("**/*", on_route)
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except PWError:
                        pass
                    try:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                        page.wait_for_timeout(700)
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(700)
                    except PWError:
                        pass
                    html = page.content()
                    final_url = page.url
                    status = resp.status if resp else None
                finally:
                    browser.close()
        except Exception as e:  # el navegador puede no estar instalado en el sistema
            msg = str(e).splitlines()[0][:200]
            return {"ok": False, "error": f"El navegador automatizado no pudo abrir la página: {msg}", "error_code": "navegador"}
    if not allowed(final_url):
        return {"ok": False, "error": "La página redirigió a un destino no permitido.", "error_code": "destino"}
    return {"ok": status is None or 200 <= status < 400, "html": html, "final_url": final_url, "status": status,
            "error": "" if (status is None or status < 400) else f"El servidor respondió {status} al navegador.",
            "error_code": "" if (status is None or status < 400) else f"http_{status}"}
