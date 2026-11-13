"""Validación de URL contra SSRF.

Reglas:
* Solo esquemas http/https, sin credenciales embebidas, longitud acotada.
* El nombre de host se resuelve y **todas** las direcciones devueltas deben ser
  públicas (se rechazan loopback, privadas, enlace-local, CGNAT, multicast,
  reservadas, no especificadas y direcciones IPv4 mapeadas en IPv6).
* Nombres internos (localhost, *.local, *.internal, metadatos de nube) se rechazan.
* Puertos permitidos: 80, 443, 8080 y 8443.
* Cada redirección se vuelve a validar (lo hace el módulo de descarga).
* El módulo de descarga se conecta a la IP ya validada (evita «DNS rebinding»).
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443, 8080, 8443}
BLOCKED_HOST_SUFFIXES = (".local", ".localhost", ".internal", ".intranet", ".lan", ".home", ".corp", ".arpa")
BLOCKED_HOSTS = {"localhost", "metadata", "metadata.google.internal", "instance-data", "kubernetes.default"}
MAX_URL_LENGTH = 2048


class UrlRejected(Exception):
    """La URL no es válida o apunta a un destino no autorizado."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class CheckedUrl:
    url: str
    scheme: str
    host: str
    port: int
    path: str  # ruta + consulta
    ips: list[str]


def normalize_url(raw: str) -> str:
    if raw is None:
        raise UrlRejected("vacia", "No se ha introducido ningún enlace.")
    url = raw.strip()
    if not url:
        raise UrlRejected("vacia", "No se ha introducido ningún enlace.")
    if len(url) > MAX_URL_LENGTH:
        raise UrlRejected("invalida", "El enlace es demasiado largo.")
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UrlRejected("esquema", f"Solo se admiten enlaces http o https (se recibió «{scheme}»).")
    if parts.username or parts.password:
        raise UrlRejected("credenciales", "El enlace no puede incluir usuario ni contraseña.")
    host = parts.hostname
    if not host:
        raise UrlRejected("invalida", "El enlace no contiene un dominio válido.")
    try:
        host_idna = host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise UrlRejected("invalida", "El dominio del enlace no es válido.")
    try:
        port = parts.port
    except ValueError:
        raise UrlRejected("invalida", "El puerto del enlace no es válido.")
    netloc = host_idna if not port else f"{host_idna}:{port}"
    if ":" in host_idna and not host_idna.startswith("["):  # IPv6 literal
        netloc = f"[{host_idna}]" + (f":{port}" if port else "")
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


def is_loopback(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def is_forbidden_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    if isinstance(addr, ipaddress.IPv6Address) and addr.sixtofour:
        addr = addr.sixtofour
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
        or not addr.is_global
    )


def check_url(raw: str, *, allow_private: bool = False, resolve: bool = True) -> CheckedUrl:
    url = normalize_url(raw)
    parts = urlsplit(url)
    scheme = parts.scheme
    host = (parts.hostname or "").lower()
    port = parts.port or (443 if scheme == "https" else 80)

    loopback_ok = allow_private and (host in ("localhost", "127.0.0.1", "::1", "[::1]") or host.startswith("127."))
    if not loopback_ok:
        if host in BLOCKED_HOSTS or host.endswith(BLOCKED_HOST_SUFFIXES) or "." not in host.strip("[]"):
            # Se permiten literales IPv6 (contienen ':'), se revisan después.
            if ":" not in host:
                raise UrlRejected("destino", "El enlace apunta a un nombre de red interno, no a una página pública.")
        if port not in ALLOWED_PORTS:
            raise UrlRejected("puerto", f"Puerto no permitido ({port}). Solo se admiten 80, 443, 8080 y 8443.")

    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query

    ips: list[str] = []
    if resolve:
        try:
            ipaddress.ip_address(host.strip("[]"))
            ips = [host.strip("[]")]
        except ValueError:
            try:
                infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            except socket.gaierror:
                raise UrlRejected("dns", f"No se pudo encontrar el dominio «{host}». Comprueba que el enlace esté bien escrito.")
            seen = []
            for info in infos:
                ip = info[4][0]
                if ip not in seen:
                    seen.append(ip)
            ips = seen
        if not ips:
            raise UrlRejected("dns", f"El dominio «{host}» no tiene direcciones asociadas.")
        if True:
            # En modo de pruebas (allow_private) solo se admite loopback; el resto sigue bloqueado.
            bad = [ip for ip in ips if is_forbidden_ip(ip) and not (allow_private and is_loopback(ip))]
            if bad:
                raise UrlRejected(
                    "destino",
                    "El enlace apunta a una dirección privada o reservada; por seguridad no se accede a ese destino.",
                )
    return CheckedUrl(url=url, scheme=scheme, host=host.strip("[]"), port=port, path=path, ips=ips)
