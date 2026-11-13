"""Reglas comunes, formato de las noticias para el modelo y fragmentos de esquema JSON."""
from __future__ import annotations

SYSTEM_RULES = """Eres un analista académico de medios de comunicación que compara cómo dos noticias periodísticas
construyen un mismo acontecimiento. Trabajas para una herramienta de investigación: tu respuesta se mostrará
junto a las evidencias y será revisada críticamente por investigadores.

REGLAS OBLIGATORIAS
1. Básate exclusivamente en el texto de las dos noticias que se te entregan. No uses conocimiento externo
   sobre los hechos, los medios o las personas. Si algo no está en el texto, indícalo como no disponible
   (null, lista vacía o "no_consta"); nunca lo completes.
2. Cada evidencia es una cita LITERAL copiada exactamente del texto (máximo 30 palabras), con el número de
   noticia (n: 1 o 2) y el identificador de unidad (p): T = titular, S = subtítulo, P1, P2... = párrafos,
   H1... = subtítulos internos, F1... = pies de foto. El sistema comprobará cada cita; las que no aparezcan
   en el texto se marcarán como no localizadas.
3. Distingue niveles: "explicito" (dicho por el medio), "atribuido" (dicho por una fuente citada),
   "interpretacion" (lectura analítica tuya) e "inferencia" (lo que se desprende sin estar dicho).
   No conviertas una inferencia en un hecho ni una acusación atribuida en responsabilidad demostrada.
4. La presencia de una palabra no prueba una intención editorial. No atribuyas una ideología general a un
   medio a partir de una sola noticia. No atribuyas emociones internas a personas por su apariencia.
5. No infieras identidades sensibles (género, edad, etnia, clase, religión, orientación, discapacidad) sin
   mención explícita en el texto.
6. Las métricas cuantitativas (palabras, párrafos, frecuencias, porcentajes) ya han sido calculadas por el
   sistema y se te proporcionan cuando son necesarias: no las estimes ni las recalcules.
7. Si una noticia está marcada como «extracción parcial», ten en cuenta que puede faltar texto y no
   interpretes ausencias como decisiones editoriales.
8. Escribe en español claro y académico, con afirmaciones prudentes y proporcionadas a la evidencia.
   Sé conciso: frases breves, sin relleno.
"""


def article_block(a: dict, *, max_words_per_unit: int = 400) -> str:
    m = a.get("meta", {})
    n = a["n"]
    lines = [f"=== NOTICIA {n} — {m.get('medio') or 'medio no identificado'} ===",
             f"Estado de lectura: {a.get('status_label', '')}" + (" (EXTRACCIÓN PARCIAL)" if a.get("status") == "parcial" else ""),
             f"Fecha de publicación: {m.get('fecha_publicacion') or 'no disponible'} | Actualización: {m.get('fecha_actualizacion') or 'no disponible'}",
             f"Autoría: {', '.join(m.get('autoria') or []) or 'no disponible'} | Sección: {m.get('seccion') or 'no disponible'}",
             f"[T] {m.get('titular') or '(sin titular)'}"]
    if m.get("subtitulo"):
        lines.append(f"[S] {m['subtitulo']}")
    for b in a.get("blocks", []):
        t = b["type"]
        if t == "paragraph":
            words = b["text"].split()
            txt = " ".join(words[:max_words_per_unit]) + (" […]" if len(words) > max_words_per_unit else "")
            tag = {"cita": " (cita destacada)", "lista": " (elemento de lista)"}.get(b.get("subtype", ""), "")
            lines.append(f"[{b['id']}]{tag} {txt}")
        elif t == "heading":
            lines.append(f"[{b['id']}] (subtítulo interno) {b['text']}")
        elif t == "figure":
            cap = b.get("caption") or "(sin pie de foto)"
            cred = f" | Crédito: {b['credit']}" if b.get("credit") else ""
            pri = " (imagen principal)" if b.get("principal") else ""
            lines.append(f"[{b['id']}] (imagen{pri}) Pie: {cap}{cred}")
        else:
            lines.append(f"[{b['id']}] ({t}: {b.get('provider', '')}) {b.get('title') or b.get('caption') or b.get('src', '')}")
    return "\n".join(lines)


def articles_text(articles: list[dict]) -> str:
    return "\n\n".join(article_block(a) for a in articles)


# --------------------------------------------------------------------------- esquemas

def s_str(desc: str = "") -> dict:
    return {"type": "string", "description": desc} if desc else {"type": "string"}


def s_enum(values: list[str], desc: str = "") -> dict:
    d = {"type": "string", "enum": values}
    if desc:
        d["description"] = desc
    return d


def s_arr(items: dict, desc: str = "") -> dict:
    d = {"type": "array", "items": items}
    if desc:
        d["description"] = desc
    return d


def s_obj(props: dict, required: list[str] | None = None, desc: str = "") -> dict:
    d = {"type": "object", "properties": props}
    if required is not None:
        d["required"] = required
    if desc:
        d["description"] = desc
    return d


def s_num(desc: str = "", minimum=None, maximum=None) -> dict:
    d = {"type": "number"}
    if desc:
        d["description"] = desc
    if minimum is not None:
        d["minimum"] = minimum
    if maximum is not None:
        d["maximum"] = maximum
    return d


EVIDENCE = s_obj({
    "n": {"type": "integer", "enum": [1, 2], "description": "Número de noticia"},
    "p": s_str("Unidad: T, S, P1, P2..., H1..., F1..."),
    "cita": s_str("Fragmento literal, máximo 30 palabras"),
}, ["n", "p", "cita"])
EVIDENCES = s_arr(EVIDENCE)
NIVEL = s_enum(["explicito", "atribuido", "interpretacion", "inferencia"])
CERTEZA = s_enum(["alta", "media", "baja"])
SYNTHESIS = s_obj({
    "resumen": s_str("Síntesis de la fase en DOS párrafos breves separados por una línea en blanco (unas 120-160 palabras en total): "
                     "el primero expone los hallazgos más importantes y las diferencias entre las dos noticias; el segundo, las semejanzas "
                     "y la conclusión que puede sostenerse. Sin listas, sin limitaciones metodológicas y sin repetir cifras ya mostradas."),
    "diferencias": s_arr(s_str(), "Diferencias principales encontradas en esta fase"),
    "semejanzas": s_arr(s_str()),
    "patrones": s_arr(s_str(), "Patrones relevantes"),
    "destaca_n1": s_str("Qué destaca la noticia 1"),
    "destaca_n2": s_str("Qué destaca la noticia 2"),
    "conclusiones": s_arr(s_str(), "Conclusiones que pueden sostenerse con la evidencia"),
    "limitaciones": s_arr(s_str(), "Limitaciones del análisis de esta fase"),
}, ["diferencias", "semejanzas", "conclusiones", "limitaciones"])
