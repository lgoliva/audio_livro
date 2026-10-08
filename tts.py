"""Síntese de voz pt-BR com edge-tts → MP3."""
from __future__ import annotations

import asyncio
import re
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import edge_tts

VOICES: dict[str, str] = {
    "Antoni": "pt-BR-AntoniobarbaroNeural",
    "Thalita": "pt-BR-ThalitaNeural",
    "Brenda": "pt-BR-BrendaNeural",
    "Donato": "pt-BR-DonatoNeural",
    "Elza": "pt-BR-ElzaNeural",
    "Fábio": "pt-BR-FabioNeural",
    "Giovanna": "pt-BR-GiovannaNeural",
    "Leticia": "pt-BR-LeticiaNeural",
    "Manuela": "pt-BR-ManuelaNeural",
    "Nicolau": "pt-BR-NicolauNeural",
}

DEFAULT_VOICE = "pt-BR-ThalitaNeural"

_SENTENCE_END = re.compile(r"[.!?](?=\s)")


def chunk_text(text: str, max_chars: int = 3000) -> list[str]:
    """Divide em blocos ≤ max_chars, cortando preferencialmente em fim de frase."""
    chunks: list[str] = []
    paragraphs = [p.strip() for p in re.split(r"\n{2,}|\r\n{2,}", text) if p.strip()]
    for paragraph in paragraphs:
        pieces = [paragraph] if len(paragraph) <= max_chars else _split_long(paragraph, max_chars)
        for piece in pieces:
            chunks.append(piece)
    return [c for c in (chunk.strip() for chunk in chunks) if c]


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    remaining = paragraph
    while len(remaining) > max_chars:
        window = remaining[: max_chars + 1]
        cut = -1
        for match in _SENTENCE_END.finditer(window):
            cut = match.end()
        if cut <= 0:
            space = remaining.rfind(" ", 0, max_chars + 1)
            cut = space + 1 if space > 0 else max_chars
        piece = remaining[:cut].strip()
        if piece:
            pieces.append(piece)
        remaining = remaining[cut:].lstrip()
    if remaining.strip():
        pieces.append(remaining.strip())
    return pieces


MAX_PARALLEL_CHUNKS = 6
MAX_RETRIES = 3


def _synthesize_chunk(text: str, voice: str, out_path: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            communicate = edge_tts.Communicate(text, voice)
            asyncio.run(communicate.save(str(out_path)))
            return
        except Exception as exc:  # rate limit/falha de rede: tenta de novo
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise last_error if last_error else RuntimeError("Falha desconhecida no TTS")


def synthesize(
    text: str,
    voice: str,
    out_path: Path,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Gera MP3 por bloco (em paralelo) e concatena os bytes em out_path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError("Texto vazio: nada para sintetizar.")
    temp_paths: list[Path] = []
    done = 0
    try:
        with tempfile.TemporaryDirectory(prefix="audiolivro_") as tmp:
            tmp_dir = Path(tmp)
            chunk_paths = [tmp_dir / f"chunk_{i:04d}.mp3" for i in range(len(chunks))]
            max_workers = min(MAX_PARALLEL_CHUNKS, len(chunks))
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(_synthesize_chunk, chunk, voice, path): path
                    for chunk, path in zip(chunks, chunk_paths)
                }
                for future in as_completed(futures):
                    future.result()
                    done += 1
                    if progress is not None:
                        progress(done, len(chunks))
            temp_paths = chunk_paths
            out_path.write_bytes(b"".join(p.read_bytes() for p in temp_paths))
    except Exception:
        if out_path.exists():
            out_path.unlink()
        raise
    return out_path
