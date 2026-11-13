"""Descarga segura de recursos externos.

La conexión se establece contra la IP previamente validada por ``urlguard``
(con SNI y verificación del certificado para el nombre de host original), de
modo que una segunda resolución DNS no puede redirigir la petición a una red
interna. Cada redirección se valida de nuevo.
"""
from __future__ import annotations

import re
import ssl
from dataclasses import dataclass, field
from urllib.parse import urljoin

import urllib3

from ..config import settings
from ..security.urlguard import UrlRejected, check_url

try:
    import certifi
    _CAFILE = certifi.where()
except Exception:  # pragma: no cover
    _CAFILE = None


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if _CAFILE:
        try:
            ctx.load_verify_locations(_CAFILE)
        except Exception:
            pass
    return ctx


_SSL_CTX = _ssl_context()


@dataclass
class FetchResult:
    ok: bool
    status: int | None = None
    url: str = ""
    final_url: str = ""
    content_type: str = ""
    body: bytes = b""
    truncated: bool = False
    redirects: list[str] = field(default_factory=list)
    error_code: str = ""
    error: str = ""
    headers: dict = field(default_factory=dict)

    def text(self) -> str:
        return decode_html(self.body, self.content_type)


def decode_html(body: bytes, content_type: str = "") -> str:
    charset = None
    m = re.search(r"charset=([\w\-]+)", content_type or "", re.I)
    if m:
        charset = m.group(1)
    if not charset:
        head = body[:4096].decode("ascii", "ignore")
        m = re.search(r"<meta[^>]+charset=[\"']?([\w\-]+)", head, re.I)
        if m:
            charset = m.group(1)
    for enc in [charset, "utf-8", "cp1252", "latin-1"]:
        if not enc:
            continue
        try:
            return body.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", "replace")


HTTP_MESSAGES = {
    400: "El servidor rechazó la solicitud (400).",
    401: "La página requiere autenticación (401).",
    402: "La página requiere pago o suscripción (402).",
    403: "El medio ha bloqueado el acceso automático a la página (403).",
    404: "La página no existe (404). Comprueba el enlace.",
    410: "La página ya no está disponible (410).",
    429: "El medio ha limitado las solicitudes (429). Inténtalo más tarde.",
    451: "El contenido no está disponible por motivos legales (451).",
}


def fetch(
    url: str,
    *,
    accept: str = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    max_bytes: int | None = None,
    max_redirects: int = 6,
    timeout: float | None = None,
    allow_private: bool | None = None,
) -> FetchResult:
    allow_private = settings.allow_private_hosts if allow_private is None else allow_private
    max_bytes = max_bytes or settings.max_page_bytes
    timeout = timeout or settings.fetch_timeout
    res = FetchResult(ok=False, url=url)
    current = url
    for _hop in range(max_redirects + 1):
        try:
            chk = check_url(current, allow_private=allow_private)
        except UrlRejected as e:
            res.error_code = e.code
            res.error = (f"La página redirige a un destino no permitido. {e.message}" if _hop else e.message)
            return res
        res.final_url = chk.url
        host_header = chk.host if chk.port in (80, 443) else f"{chk.host}:{chk.port}"
        if ":" in chk.host:
            host_header = f"[{chk.host}]" + ("" if chk.port in (80, 443) else f":{chk.port}")
        headers = {
            "Host": host_header,
            "User-Agent": settings.user_agent,
            "Accept": accept,
            "Accept-Language": "es-PE,es;q=0.9,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "close",
        }
        ip = chk.ips[0]
        tmo = urllib3.Timeout(connect=min(10.0, timeout), read=timeout)
        try:
            if chk.scheme == "https":
                pool = urllib3.HTTPSConnectionPool(
                    ip, chk.port, timeout=tmo, retries=False, maxsize=1,
                    server_hostname=chk.host, assert_hostname=chk.host,
                    ssl_context=_SSL_CTX, cert_reqs="CERT_REQUIRED",
                )
            else:
                pool = urllib3.HTTPConnectionPool(ip, chk.port, timeout=tmo, retries=False, maxsize=1)
            r = pool.urlopen("GET", chk.path, headers=headers, redirect=False,
                             preload_content=False, assert_same_host=False)
        except urllib3.exceptions.SSLError as e:
            res.error_code, res.error = "tls", f"No se pudo establecer una conexión segura con el medio ({type(e).__name__})."
            return res
        except (urllib3.exceptions.ConnectTimeoutError, urllib3.exceptions.ReadTimeoutError):
            res.error_code, res.error = "tiempo", "El medio tardó demasiado en responder."
            return res
        except urllib3.exceptions.HTTPError as e:
            res.error_code, res.error = "red", f"No se pudo conectar con el medio ({type(e).__name__})."
            return res
        except OSError as e:
            res.error_code, res.error = "red", f"Error de red al conectar con el medio ({e.__class__.__name__})."
            return res

        status = r.status
        if status in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location")
            r.release_conn()
            if not loc:
                res.error_code, res.error = "redireccion", "El medio redirigió sin indicar el destino."
                return res
            nxt = urljoin(chk.url, loc)
            res.redirects.append(nxt)
            current = nxt
            continue

        res.status = status
        res.headers = {k.lower(): v for k, v in r.headers.items()}
        res.content_type = r.headers.get("Content-Type", "")
        chunks, size = [], 0
        try:
            for chunk in r.stream(65536, decode_content=True):
                chunks.append(chunk)
                size += len(chunk)
                if size > max_bytes:
                    res.truncated = True
                    break
        except Exception as e:
            res.error_code, res.error = "lectura", f"La descarga se interrumpió ({type(e).__name__})."
            r.release_conn()
            return res
        finally:
            try:
                r.release_conn()
            except Exception:
                pass
        res.body = b"".join(chunks)[: max_bytes]
        if 200 <= status < 300:
            res.ok = True
        else:
            res.error_code = f"http_{status}"
            res.error = HTTP_MESSAGES.get(status, f"El servidor respondió con un error ({status}).")
        return res

    res.error_code, res.error = "redireccion", "Demasiadas redirecciones."
    return res
