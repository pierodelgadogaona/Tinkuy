"""Geocodificación con Nominatim (OpenStreetMap) y nomenclátor local de respaldo.

Reglas de rigor:
* El nivel de precisión del resultado nunca supera el nivel que la noticia permite
  establecer (si la noticia solo menciona un distrito, se representa el distrito).
* Si hay varios candidatos alejados entre sí, la ubicación se marca como ambigua.
* Si no se encuentra el lugar, se devuelve «no localizado»: no se inventan coordenadas.
* Política de uso de Nominatim: como máximo 1 solicitud por segundo, caché local y
  agente de usuario identificable (configurable con TINKUY_CONTACT_EMAIL).
"""
from __future__ import annotations

import json
import math
import threading
import time
from urllib.parse import urlencode

from .. import storage
from ..config import settings
from ..extraction.fetcher import fetch
from . import gazetteer

_rate_lock = threading.Lock()
_last_call = [0.0]
_nominatim_down = [0.0]

LEVEL_ORDER = ["pais", "region", "provincia", "ciudad", "distrito", "localidad", "via", "edificio", "punto"]
NOMINATIM_LEVEL = {
    "country": "pais", "state": "region", "region": "region", "province": "provincia", "county": "provincia",
    "city": "ciudad", "town": "ciudad", "municipality": "ciudad", "city_district": "distrito", "district": "distrito",
    "borough": "distrito", "suburb": "distrito", "quarter": "distrito", "neighbourhood": "localidad",
    "village": "localidad", "hamlet": "localidad", "road": "via", "street": "via", "highway": "via",
    "amenity": "edificio", "building": "edificio", "hospital": "edificio", "house": "punto", "place": "localidad",
}


def _rank(level: str) -> int:
    return LEVEL_ORDER.index(level) if level in LEVEL_ORDER else 4


def _dist_km(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _nominatim(query: str, country_codes: str = "") -> list[dict] | None:
    if time.time() - _nominatim_down[0] < 300:
        return None  # el servicio falló hace poco; no se insiste
    params = {"q": query, "format": "jsonv2", "limit": 4, "addressdetails": 1, "accept-language": "es"}
    if country_codes:
        params["countrycodes"] = country_codes
    if settings.contact_email:
        params["email"] = settings.contact_email
    url = f"{settings.nominatim_url}/search?{urlencode(params)}"
    with _rate_lock:
        wait = 1.1 - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        r = fetch(url, accept="application/json", max_bytes=2_000_000, timeout=12, allow_private=False)
    if not r.ok:
        _nominatim_down[0] = time.time()
        return None
    try:
        return json.loads(r.body.decode("utf-8"))
    except Exception:
        return None


def geocode(query: str, *, nivel_texto: str = "", country_codes: str = "pe") -> dict:
    """Devuelve {lat, lon, nivel, fuente, aproximada, ambigua, etiqueta, nota} o {no_localizado: True}."""
    q = (query or "").strip()
    if not q or settings.geocoding == "off":
        return {"no_localizado": True, "nota": "Geocodificación desactivada." if settings.geocoding == "off" else "Sin consulta."}
    cache_key = f"{q}|{nivel_texto}|{country_codes}"
    cached = storage.geocache_get(cache_key)
    if cached:
        return cached

    result = None
    if settings.geocoding == "nominatim":
        hits = _nominatim(q, country_codes)
        if hits is None and country_codes:
            pass
        elif hits == [] and country_codes:
            hits = _nominatim(q, "")
        if hits:
            best = hits[0]
            addresstype = best.get("addresstype") or best.get("type") or ""
            level = NOMINATIM_LEVEL.get(addresstype, NOMINATIM_LEVEL.get(best.get("category", ""), "localidad"))
            lat, lon = float(best["lat"]), float(best["lon"])
            ambigua = False
            if len(hits) > 1:
                others = [(float(h["lat"]), float(h["lon"])) for h in hits[1:]]
                ambigua = any(_dist_km((lat, lon), o) > 25 for o in others) and \
                    float(hits[1].get("importance") or 0) > 0.8 * float(best.get("importance") or 0.01)
            aproximada = False
            nota = ""
            if nivel_texto and _rank(level) > _rank(nivel_texto):
                # el geocodificador es más preciso que la noticia: no se finge precisión
                level = nivel_texto
                aproximada = True
                nota = "Se representa con la precisión que permite la noticia."
            result = {"lat": lat, "lon": lon, "nivel": level, "fuente": "Nominatim (OpenStreetMap)",
                      "aproximada": aproximada or ambigua, "ambigua": ambigua,
                      "etiqueta": best.get("display_name", q)[:160], "nota": nota or ("Varios lugares posibles con ese nombre." if ambigua else "")}

    if result is None:
        entry = gazetteer.find_in_text(q)
        if entry:
            name, _al, kind, lat, lon, ctx = entry
            level = {"pais": "pais", "region": "region", "ciudad": "ciudad", "distrito": "distrito", "localidad": "localidad"}[kind]
            if nivel_texto and _rank(nivel_texto) < _rank(level):
                level = nivel_texto  # la noticia es menos precisa
            approx_reason = "nomenclátor local: " + gazetteer.LEVEL_LABEL.get(kind, kind)
            more_precise = nivel_texto and _rank(nivel_texto) > _rank(kind)
            result = {"lat": lat, "lon": lon, "nivel": kind, "fuente": "Nomenclátor local de Tinkuy", "aproximada": True,
                      "ambigua": False, "etiqueta": f"{name}" + (f" ({ctx})" if ctx else ""),
                      "nota": ("La ubicación exacta no pudo determinarse; se representa " + gazetteer.LEVEL_LABEL.get(kind, kind)
                               + ".") if more_precise else approx_reason.capitalize() + "."}
    if result is None:
        result = {"no_localizado": True, "nota": "No se encontró una ubicación verificable para este lugar."}
    nominatim_answered = settings.geocoding == "nominatim" and time.time() - _nominatim_down[0] >= 300
    if settings.geocoding != "nominatim" or nominatim_answered:
        storage.geocache_put(cache_key, result)  # no se fija en caché un respaldo mientras Nominatim no responde
    return result


def status() -> dict:
    if settings.geocoding == "off":
        return {"activo": False, "detalle": "Desactivada."}
    if settings.geocoding == "gazetteer":
        return {"activo": True, "detalle": "Solo nomenclátor local (países, regiones del Perú y distritos de Lima y Callao)."}
    return {"activo": True, "detalle": "Nominatim (OpenStreetMap) con nomenclátor local de respaldo."}
