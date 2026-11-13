"""Exportación a PDF y captura de figuras con Chromium (Playwright).

Se abre la vista de impresión del informe servida por la propia aplicación
(127.0.0.1), se espera a que gráficos, tipografías y mapas estén listos y se
imprime en A4. El ancho de la ventana coincide con el ancho imprimible / escala,
de modo que los gráficos se dibujan exactamente al tamaño de la página.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
SCALE = 0.8
VIEWPORT_W = 880  # (210 mm − 2 × 12 mm) a 96 ppp ≈ 703 px  →  703 / 0,8


def _open(p, base: str, pid: str):
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": VIEWPORT_W, "height": 1200}, device_scale_factor=2)
    page.goto(f"{base}/#/proyecto/{pid}/informe?print=1", wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_function("window.__TINKUY_READY__ === true", timeout=45000)
    except Exception:
        pass  # se imprime igualmente lo disponible (p. ej., sin mapa base)
    page.wait_for_timeout(400)
    return browser, page


def build_pdf(base: str, pid: str) -> bytes:
    from playwright.sync_api import sync_playwright
    footer = ('<div style="font-size:7.5px;width:100%;padding:0 12mm;color:#8a8d93;font-family:Inter,Arial,sans-serif;'
              'display:flex;justify-content:space-between"><span>Tinkuy</span>'
              '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')
    with _lock, sync_playwright() as p:
        browser, page = _open(p, base, pid)
        try:
            return page.pdf(format="A4", print_background=True, scale=SCALE, display_header_footer=True,
                            header_template="<div></div>", footer_template=footer,
                            margin={"top": "14mm", "bottom": "16mm", "left": "12mm", "right": "12mm"})
        finally:
            browser.close()


def capture_figures(base: str, pid: str, kinds: set[str] | None = None) -> dict[str, bytes]:
    """Devuelve {id_de_bloque: PNG} para las figuras del informe."""
    from playwright.sync_api import sync_playwright
    out: dict[str, bytes] = {}
    with _lock, sync_playwright() as p:
        browser, page = _open(p, base, pid)
        try:
            for el in page.query_selector_all("[data-figure-id]"):
                fid = el.get_attribute("data-figure-id")
                fig = el.query_selector(".figure") or el.query_selector(".cards, .gallery, .flow, .t3, .argtree, .venn, .grid2")
                if not fig:
                    continue
                try:
                    out[fid] = fig.screenshot(type="png")
                except Exception:
                    continue
        finally:
            browser.close()
    return out
