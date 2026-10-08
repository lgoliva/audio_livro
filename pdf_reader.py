"""Leitura de PDF: sumário, capítulos e extração de texto."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz

CHAPTER_RE = re.compile(r"(?i)^\s*cap[íi]tulo\s+([0-9]+|[IVXLCDM]+)\b")

MIN_CHARS_PER_PAGE_IMAGE_WARNING = 100


@dataclass
class Chapter:
    title: str
    start_page: int  # 0-indexed, inclusiva
    end_page: int  # 0-indexed, inclusiva


@dataclass
class Book:
    filename: str
    chapters: list[Chapter] = field(default_factory=list)
    page_count: int = 0
    data: bytes = field(default=b"", repr=False)


def _chapters_from_toc(doc: fitz.Document, page_count: int) -> list[Chapter]:
    toc = doc.get_toc()
    level1 = [entry for entry in toc if entry[0] == 1]
    if not level1:
        return []
    chapters: list[Chapter] = []
    for i, (_level, title, page) in enumerate(level1):
        start_page = max(page - 1, 0)  # get_toc() usa páginas 1-indexed
        if i + 1 < len(level1):
            end_page = min(max(level1[i + 1][2] - 2, start_page), page_count - 1)
        else:
            end_page = page_count - 1
        chapters.append(Chapter(title=title, start_page=start_page, end_page=end_page))
    return chapters


def _chapters_from_text(doc: fitz.Document, page_count: int) -> list[Chapter]:
    starts: list[tuple[int, str]] = []
    for page_index in range(page_count):
        text = doc[page_index].get_text()
        for line in text.splitlines():
            match = CHAPTER_RE.match(line)
            if match:
                starts.append((page_index, line.strip()))
                break
    if not starts:
        return []
    chapters: list[Chapter] = []
    for i, (start_page, title) in enumerate(starts):
        if chapters and start_page <= chapters[-1].start_page:
            continue
        end_page = starts[i + 1][0] - 1 if i + 1 < len(starts) else page_count - 1
        chapters.append(Chapter(title=title, start_page=start_page, end_page=end_page))
    return chapters


def load_pdf(data: bytes, filename: str) -> Book:
    """Abre o PDF e detecta capítulos (sumário embutido → regex → manual)."""
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        page_count = doc.page_count
        chapters = _chapters_from_toc(doc, page_count)
        if not chapters:
            chapters = _chapters_from_text(doc, page_count)
        return Book(filename=filename, chapters=chapters, page_count=page_count, data=data)
    finally:
        doc.close()


def is_likely_scanned(doc: fitz.Document) -> bool:
    """Heurística: menos de 100 caracteres extraíveis por página em média."""
    if doc.page_count == 0:
        return True
    total = sum(len(doc[i].get_text()) for i in range(doc.page_count))
    return total / doc.page_count < MIN_CHARS_PER_PAGE_IMAGE_WARNING


PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")


def _drop_running_boilerplate(pages: list[str]) -> list[str]:
    """Remove linhas repetidas em ≥50% das páginas (cabeçalhos/rodapés)
    e linhas que são só número de página."""
    if len(pages) < 2:
        return pages
    normalized: list[list[str]] = []
    for page in pages:
        normalized.append(
            [re.sub(r"\s+", " ", line).strip() for line in page.splitlines()]
        )
    counts: dict[str, int] = {}
    for lines in normalized:
        for line in set(line for line in lines if len(line) >= 3):
            counts[line] = counts.get(line, 0) + 1
    threshold = max(2, len(pages) // 2)
    boilerplate = {line for line, count in counts.items() if count >= threshold}
    cleaned: list[str] = []
    for lines in normalized:
        kept = [
            line
            for line in lines
            if line and line not in boilerplate and not PAGE_NUMBER_RE.match(line)
        ]
        cleaned.append("\n".join(kept))
    return cleaned


def extract_text(book: Book, chapter: Chapter) -> str:
    """Concatena texto das páginas do capítulo, corrigindo hifenização."""
    doc = fitz.open(stream=book.data, filetype="pdf")
    try:
        parts = [
            doc[page_index].get_text()
            for page_index in range(chapter.start_page, chapter.end_page + 1)
        ]
    finally:
        doc.close()
    parts = _drop_running_boilerplate(parts)
    text = "\n".join(parts)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
