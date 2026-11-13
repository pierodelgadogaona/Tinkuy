"""Cliente de modelos de lenguaje con salida estructurada.

Proveedores:
* ``anthropic``: API de Mensajes de Anthropic con *tool use* forzado (el JSON
  se valida contra el esquema de la herramienta).
* ``openai``: cualquier API compatible con ``/chat/completions`` (OpenAI, servidores locales).
* ``replay``: lee respuestas pregrabadas de ``TINKUY_REPLAY_DIR`` (solo pruebas/demostración).
* ``none``: sin modelo; los análisis interpretativos se marcan como «requiere modelo».

La clave nunca sale del backend. Con ``TINKUY_LLM_RECORD_DIR`` se guardan las respuestas
reales para poder reproducir un análisis sin conexión.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from pathlib import Path

import requests

from ..config import settings


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    pass


_sem = threading.BoundedSemaphore(settings.llm_concurrency)


def available() -> bool:
    return settings.llm_status()["configurado"]


def _record(task: str, data: dict):
    d = os.getenv("TINKUY_LLM_RECORD_DIR")
    if d:
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{task}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def call(task: str, system: str, user: str, schema: dict, *, images: list[dict] | None = None,
         max_tokens: int | None = None, description: str = "") -> tuple[dict, dict]:
    """Devuelve (resultado, uso). ``images``: [{"media_type": "image/jpeg", "data": bytes, "label": str}]."""
    prov = settings.llm_provider
    if not available():
        raise LLMUnavailable(settings.llm_status()["detalle"] or "Modelo de lenguaje no configurado.")
    max_tokens = max_tokens or settings.llm_max_tokens
    t0 = time.time()
    with _sem:
        if prov == "anthropic":
            out, usage = _anthropic(task, system, user, schema, images, max_tokens, description)
        elif prov == "openai":
            out, usage = _openai(task, system, user, schema, images, max_tokens)
        elif prov == "replay":
            out, usage = _replay(task)
        else:
            raise LLMUnavailable("Proveedor de modelo desconocido.")
    usage["segundos"] = round(time.time() - t0, 1)
    usage["tarea"] = task
    if prov != "replay":
        _record(task, out)
    return out, usage


def _anthropic(task, system, user, schema, images, max_tokens, description):
    content = []
    for img in images or []:
        content.append({"type": "text", "text": f"Imagen: {img.get('label', '')}"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": img["media_type"],
                                                     "data": base64.b64encode(img["data"]).decode("ascii")}})
    content.append({"type": "text", "text": user})
    body = {
        "model": settings.anthropic_model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": content}],
        "tools": [{"name": "registrar_analisis", "description": description or "Registra el análisis estructurado.",
                   "input_schema": schema}],
        "tool_choice": {"type": "tool", "name": "registrar_analisis"},
    }
    temp = os.getenv("TINKUY_LLM_TEMPERATURE", "0")
    if temp != "":
        body["temperature"] = float(temp)
    headers = {"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    url = f"{settings.anthropic_base_url}/v1/messages"
    last_err = ""
    for attempt in range(4):
        try:
            r = requests.post(url, headers=headers, json=body, timeout=settings.llm_timeout)
        except requests.RequestException as e:
            last_err = f"No se pudo conectar con el proveedor del modelo ({type(e).__name__})."
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 200:
            data = r.json()
            if data.get("stop_reason") == "max_tokens" and attempt == 0:
                body["max_tokens"] = int(max_tokens * 1.6)
                continue
            for block in data.get("content", []):
                if block.get("type") == "tool_use":
                    u = data.get("usage", {})
                    return block.get("input") or {}, {"modelo": data.get("model", settings.anthropic_model),
                                                      "entrada": u.get("input_tokens"), "salida": u.get("output_tokens")}
            raise LLMError("El modelo no devolvió un resultado estructurado.")
        if r.status_code == 400 and "temperature" in r.text and "temperature" in body:
            body.pop("temperature")
            continue
        if r.status_code in (401, 403):
            raise LLMUnavailable("La clave de la API de Anthropic no es válida o no tiene permisos (HTTP %d)." % r.status_code)
        if r.status_code == 404:
            raise LLMUnavailable(f"El modelo «{settings.anthropic_model}» no existe o no está disponible para esta clave (TINKUY_MODEL).")
        if r.status_code in (429, 500, 502, 503, 529):
            wait = float(r.headers.get("retry-after") or 0) or 4 * (attempt + 1)
            last_err = f"El proveedor respondió {r.status_code} (saturación o límite de uso)."
            time.sleep(min(wait, 30))
            continue
        try:
            msg = r.json().get("error", {}).get("message", r.text[:200])
        except Exception:
            msg = r.text[:200]
        raise LLMError(f"Error del proveedor del modelo ({r.status_code}): {msg}")
    raise LLMError(last_err or "El proveedor del modelo no respondió.")


def _openai(task, system, user, schema, images, max_tokens):
    parts = [{"type": "text", "text": user + "\n\nResponde ÚNICAMENTE con un objeto JSON que cumpla este esquema:\n"
              + json.dumps(schema, ensure_ascii=False)}]
    for img in images or []:
        b64 = base64.b64encode(img["data"]).decode("ascii")
        parts.append({"type": "image_url", "image_url": {"url": f"data:{img['media_type']};base64,{b64}"}})
    body = {"model": settings.openai_model, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": parts}],
            "response_format": {"type": "json_object"}, "temperature": 0}
    headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
    last = ""
    for attempt in range(3):
        try:
            r = requests.post(f"{settings.openai_base_url}/chat/completions", headers=headers, json=body,
                              timeout=settings.llm_timeout)
        except requests.RequestException as e:
            last = f"No se pudo conectar con el proveedor ({type(e).__name__})."
            time.sleep(2)
            continue
        if r.status_code == 200:
            data = r.json()
            txt = data["choices"][0]["message"]["content"] or "{}"
            try:
                out = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
            except json.JSONDecodeError:
                raise LLMError("El modelo devolvió un JSON no válido.")
            u = data.get("usage", {})
            return out, {"modelo": data.get("model", settings.openai_model), "entrada": u.get("prompt_tokens"),
                         "salida": u.get("completion_tokens")}
        if r.status_code in (401, 403):
            raise LLMUnavailable("La clave del proveedor compatible con OpenAI no es válida.")
        if r.status_code in (429, 500, 502, 503):
            last = f"El proveedor respondió {r.status_code}."
            time.sleep(4 * (attempt + 1))
            continue
        raise LLMError(f"Error del proveedor ({r.status_code}): {r.text[:200]}")
    raise LLMError(last or "El proveedor no respondió.")


def _replay(task):
    f = settings.replay_dir / f"{task}.json"
    if not f.exists():
        raise LLMError(f"No hay respuesta pregrabada para la tarea «{task}» (modo de prueba).")
    return json.loads(f.read_text(encoding="utf-8")), {"modelo": "replay", "entrada": 0, "salida": 0}
