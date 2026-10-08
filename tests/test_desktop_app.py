"""Testes para utilitários da interface desktop."""
from pathlib import Path
import pytest
from pdf_reader import Chapter, Book
from desktop_app import sanitize, chapter_output_path, detection_badge
from tests.test_pdf_reader import make_pdf


def test_sanitize():
    assert sanitize('livro: teste / volume 1') == "livro_ teste _ volume 1"
    assert sanitize("") == "livro"
    assert len(sanitize("a" * 150, max_len=50)) == 50


def test_chapter_output_path():
    book = Book(filename="Meu Livro.pdf", chapters=[], page_count=10, data=b"")
    chapter = Chapter(title="Capítulo 1: Introdução", start_page=0, end_page=2)
    path = chapter_output_path(book, 0, chapter)
    expected = Path("output") / "Meu Livro" / "01 - Capítulo 1_ Introdução.mp3"
    assert path == expected


def test_detection_badge():
    # Sem capítulos
    empty_book = Book(filename="vazio.pdf", chapters=[], page_count=0, data=b"")
    assert detection_badge(empty_book) == "manual"

    # Com TOC
    toc_data = make_pdf(["p1", "p2"], toc=[(1, "Cap 1", 1)])
    toc_book = Book(
        filename="toc.pdf",
        chapters=[Chapter(title="Cap 1", start_page=0, end_page=1)],
        page_count=2,
        data=toc_data,
    )
    assert detection_badge(toc_book) == "sumário embutido"

    # Sem TOC
    no_toc_data = make_pdf(["Capítulo 1\ntexto"])
    text_book = Book(
        filename="text.pdf",
        chapters=[Chapter(title="Capítulo 1", start_page=0, end_page=0)],
        page_count=1,
        data=no_toc_data,
    )
    assert detection_badge(text_book) == "detectado por texto"
