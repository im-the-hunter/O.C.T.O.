"""
Servicio de chunking (Fase 5 — RAG).

Estrategia por tipo de archivo:
- Código (.py/.js/.ts/.tsx/.jsx...): divide por funciones/clases cuando es
  posible (top-level defs), con solapamiento de ~50 tokens entre chunks.
- Markdown: divide por secciones (encabezados #, ##, ###...).
- Otros (json/yaml/texto): divide por párrafos / bloques de líneas.

Tamaño objetivo: ~500 tokens por chunk (configurable vía settings),
overlapping: ~50 tokens. El conteo de tokens usa tiktoken (cl100k_base)
con fallback heurístico (len/4) si la librería no está disponible.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("jarvis.chunking")

# --- Contador de tokens -----------------------------------------------------
try:  # pragma: no cover
    import tiktoken

    _ENCODER = None

    def _encoder():
        global _ENCODER
        if _ENCODER is None:
            _ENCODER = tiktoken.get_encoding("cl100k_base")
        return _ENCODER

    def count_tokens(text: str) -> int:
        try:
            return len(_encoder().encode(text, disallowed_special=()))
        except Exception:  # noqa: BLE001
            return max(1, len(text) // 4)
except ImportError:  # pragma: no cover
    def count_tokens(text: str) -> int:  # type: ignore[misc]
        return max(1, len(text) // 4)


LANGUAGE_BY_EXT: dict[str, str] = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".mjs": "javascript",
    ".cjs": "javascript", ".md": "markdown", ".markdown": "markdown",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".sql": "sql",
    ".sh": "shell", ".css": "css", ".html": "html", ".txt": "text",
}

CODE_LANGUAGES = {"python", "javascript", "typescript"}

TOP_LEVEL_DEF_RE = re.compile(
    r"^(?:(?:async\s+)?def\s+\w+|class\s+\w+|(?:export\s+)?(?:default\s+)?"
    r"(?:const|let|var|function)\s+\w+|@\w+.*)",
    re.MULTILINE,
)


@dataclass
class Chunk:
    text: str
    index: int
    total: int = 1
    metadata: dict = field(default_factory=dict)


def detect_language(path: str) -> str:
    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return LANGUAGE_BY_EXT.get(ext, "text")


# ---------------------------------------------------------------------------
# Helpers de división
# ---------------------------------------------------------------------------
def _split_by_blocks(text: str, pattern: re.Pattern) -> list[str]:
    """Divide manteniendo el delimitador al inicio de cada bloque."""
    parts = pattern.split(text)
    blocks: list[str] = []
    # re.split con grupo captorador alterna contenido/delimitador
    it = iter(parts)
    first = next(it, "")
    if first.strip():
        blocks.append(first)
    for delim, body in zip(it, it):
        block = (delim or "") + (body or "")
        if block.strip():
            blocks.append(block)
    return blocks or [text]


def _strip_leading_overlap(text: str, overlap_tokens: int) -> str:
    """Elimina del inicio los tokens que repite el solapamiento anterior.

    Mantiene intactas las líneas estructurales (encabezados markdown), de modo
    que los chunks siguen comenzando exactamente en el límite de sección.
    """
    tail = _tail_by_tokens(text, overlap_tokens)
    if not tail:
        return text
    lines = text.split("\n")
    cut = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):          # encabezado: límite de sección real
            break
        if stripped and stripped in tail:      # línea repetida por el overlap
            cut += 1
            continue
        break
    trimmed = "\n".join(lines[cut:])
    return trimmed if trimmed.strip() else text


def _merge_with_overlap(
    blocks: list[str],
    chunk_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """Une bloques pequeños hasta alcanzar ~chunk_tokens.

    Cada chunk nuevo (a partir del segundo) comienza con los últimos
    `overlap_tokens` del chunk anterior: solapamiento real que preserva
    el contexto entre fragmentos.
    """
    merged: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for block in blocks:
        b_tokens = count_tokens(block)

        # Bloque gigante por sí solo: troceo duro con solapamiento por caracteres
        if b_tokens > chunk_tokens:
            if current:
                merged.append("\n".join(current))
                current, current_tokens = [], 0
            merged.extend(_hard_split(block, chunk_tokens, overlap_tokens))
            continue

        if current_tokens + b_tokens > chunk_tokens and current:
            prev_text = "\n".join(current)
            merged.append(prev_text)
            tail = _tail_by_tokens(prev_text, overlap_tokens)
            current = [tail, block] if tail else [block]
            current_tokens = count_tokens("\n".join(current))
        else:
            current.append(block)
            current_tokens += b_tokens

    if current:
        merged.append("\n".join(current))
    chunks = [c for c in merged if c.strip()]

    # Solapamiento real entre chunks consecutivos: cada chunk (a partir del
    # segundo) comienza con los últimos `overlap_tokens` del anterior.
    if len(chunks) >= 2 and overlap_tokens > 0:
        overlapped = [chunks[0]]
        for c in chunks[1:]:
            tail = _tail_by_tokens(overlapped[-1], overlap_tokens)
            if tail and c[:40] not in tail:
                overlapped.append(f"{tail}\n{c}")
            else:
                overlapped.append(c)
        chunks = overlapped

    # Si la fusión dejó un único chunk pero el texto excede el objetivo,
    # dividir por bloques como mínimo para respetar la granularidad.
    if len(chunks) == 1 and len(blocks) > 1 and count_tokens(chunks[0]) > chunk_tokens:
        chunks = ["\n".join(b) for b in _regroup_blocks(blocks, chunk_tokens)]

    return chunks


def _regroup_blocks(blocks: list[str], chunk_tokens: int) -> list[list[str]]:
    """Agrupa bloques en grupos de <= chunk_tokens (sin solapamiento)."""
    groups: list[list[str]] = []
    current: list[str] = []
    tok = 0
    for b in blocks:
        bt = count_tokens(b)
        if current and tok + bt > chunk_tokens:
            groups.append(current)
            current, tok = [], 0
        current.append(b)
        tok += bt
    if current:
        groups.append(current)
    return groups


def _hard_split(text: str, chunk_tokens: int, overlap_tokens: int) -> list[str]:
    """Troceo por líneas para bloques que exceden el tamaño objetivo."""
    approx_chars = max(200, chunk_tokens * 4)
    overlap_chars = max(50, overlap_tokens * 4)
    out: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + approx_chars, n)
        if end < n:
            nl = text.find("\n", end - approx_chars // 4)
            if nl != -1 and nl > start:
                end = nl
        out.append(text[start:end])
        if end >= n:
            break
        start = max(start + 1, end - overlap_chars)
    return out


def _tail_by_tokens(text: str, tokens: int) -> str:
    """Devuelve el final del texto acotado a ~N tokens."""
    if tokens <= 0:
        return ""
    try:  # preferencia por tiktoken para precisión
        enc = _encoder()
        ids = enc.encode(text, disallowed_special=())
        if len(ids) <= tokens:
            return text
        return enc.decode(ids[-tokens:])
    except NameError:  # tiktoken no disponible
        chars = tokens * 4
        return text[-chars:] if len(text) > chars else text
    except Exception:  # noqa: BLE001
        chars = tokens * 4
        return text[-chars:] if len(text) > chars else text


# ---------------------------------------------------------------------------
# Estrategias por lenguaje
# ---------------------------------------------------------------------------
def chunk_code(text: str, chunk_tokens: int, overlap_tokens: int) -> list[str]:
    """Divide código por funciones/clases de nivel superior."""
    split_points = [m.start() for m in TOP_LEVEL_DEF_RE.finditer(text)]
    if not split_points:
        blocks = [text]
    else:
        if split_points[0] != 0:
            split_points.insert(0, 0)
        blocks = [text[i:j] for i, j in zip(split_points, split_points[1:] + [len(text)])]
    return _merge_with_overlap(blocks, chunk_tokens, overlap_tokens)


def chunk_markdown(text: str, chunk_tokens: int, overlap_tokens: int) -> list[str]:
    """Divide markdown por encabezados (#, ##, ...)."""
    # Lookahead en vez de captura: evita el desalineamiento de re.split
    blocks = re.split(r"\n(?=#{1,6}\s)", text)
    blocks = [b for b in blocks if b.strip()]
    return _merge_with_overlap(blocks or [text], chunk_tokens, overlap_tokens)


def chunk_paragraphs(text: str, chunk_tokens: int, overlap_tokens: int) -> list[str]:
    """Divide por párrafos (otros formatos: json, yaml, txt...)."""
    blocks = re.split(r"\n\s*\n", text)
    blocks = [b for b in blocks if b.strip()]
    if not blocks:
        blocks = [text]
    return _merge_with_overlap(blocks, chunk_tokens, overlap_tokens)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------
def chunk_file(
    path: str,
    content: str,
    *,
    chunk_tokens: int = 500,
    overlap_tokens: int = 50,
) -> list[Chunk]:
    """Trocea un archivo aplicando la estrategia adecuada según su lenguaje.

    Retorna una lista de Chunk con metadata básica (language). El llamador
    (ingest_repo.py) añade file_path, chunk_index, total_chunks, etc.
    """
    if not content or not content.strip():
        return []

    language = detect_language(path)
    if language in CODE_LANGUAGES:
        pieces = chunk_code(content, chunk_tokens, overlap_tokens)
    elif language == "markdown":
        pieces = chunk_markdown(content, chunk_tokens, overlap_tokens)
    else:
        pieces = chunk_paragraphs(content, chunk_tokens, overlap_tokens)

    total = len(pieces)
    return [
        Chunk(text=p.strip(), index=i, total=total, metadata={"language": language})
        for i, p in enumerate(pieces)
        if p.strip()
    ]
