"""Testes de pdf_reader: detecção de capítulos e extração de texto."""
import re

import fitz
import pytest

import pdf_reader
from pdf_reader import Chapter, extract_text, load_pdf


def make_pdf(pages_text: list[str], toc: list | None = None) -> bytes:
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    if toc is not None:
        doc.set_toc(toc)
    data = doc.tobytes()
    doc.close()
    return data


class TestTocDetection:
    def test_toc_entries_become_chapters(self):
        data = make_pdf(
            ["intro", "p2", "cap 1 texto", "p4", "cap 2 texto"],
            toc=[(1, "Introdução", 1), (1, "Capítulo 1", 3), (1, "Capítulo 2", 5)],
        )
        book = load_pdf(data, "livro.pdf")
        assert book.page_count == 5
        assert len(book.chapters) == 3
        assert [c.title for c in book.chapters] == [
            "Introdução",
            "Capítulo 1",
            "Capítulo 2",
        ]

    def test_toc_page_limits(self):
        data = make_pdf(
            ["p1", "p2", "p3", "p4", "p5"],
            toc=[(1, "A", 1), (1, "B", 3), (1, "C", 5)],
        )
        book = load_pdf(data, "livro.pdf")
        assert [(c.start_page, c.end_page) for c in book.chapters] == [
            (0, 1),
            (2, 3),
            (4, 4),
        ]

    def test_toc_first_page_clamped(self):
        data = make_pdf(["p1", "p2"], toc=[(1, "A", 1), (1, "B", 2)])
        book = load_pdf(data, "livro.pdf")
        assert book.chapters[-1].end_page == book.page_count - 1


class TestRegexDetection:
    def test_arabic_and_roman(self):
        data = make_pdf(
            [
                "CAPÍTULO I\nComeço",
                "texto da pagina",
                "capitulo 2\nOutro começo",
                "mais texto",
            ]
        )
        book = load_pdf(data, "livro.pdf")
        assert len(book.chapters) == 2
        assert book.chapters[0].start_page == 0
        assert book.chapters[0].end_page == 1
        assert book.chapters[1].start_page == 2
        assert book.chapters[1].end_page == 3

    def test_no_match_means_manual_mode(self):
        data = make_pdf(["pagina sem capitulos", "outra pagina"])
        book = load_pdf(data, "livro.pdf")
        assert book.chapters == []

    def test_case_insensitive_with_accent_and_without(self):
        data = make_pdf(["Capítulo X\num", "meio", "CAPITULO XI\ndois"])
        book = load_pdf(data, "livro.pdf")
        assert len(book.chapters) == 2


class TestPageLimits:
    def test_no_overlap_and_bounds(self):
        data = make_pdf(
            [f"Capítulo {i}\nconteudo {i}" for i in range(1, 6)]
        )
        book = load_pdf(data, "livro.pdf")
        previous_end = -1
        for chapter in book.chapters:
            assert chapter.start_page >= previous_end + 1
            assert 0 <= chapter.start_page <= chapter.end_page < book.page_count
            previous_end = chapter.end_page


class TestExtractText:
    def test_hyphenation_removed(self):
        data = make_pdf(["pala-\nvra continua aqui."])
        book = load_pdf(data, "livro.pdf")
        chapter = Chapter(title="tudo", start_page=0, end_page=0)
        text = extract_text(book, chapter)
        assert "palavra continua aqui." in text.replace("  ", " ")

    def test_pages_concatenated(self):
        data = make_pdf(["primeira pagina.", "segunda pagina."])
        book = load_pdf(data, "livro.pdf")
        chapter = Chapter(title="tudo", start_page=0, end_page=1)
        text = extract_text(book, chapter)
        assert "primeira pagina." in text
        assert "segunda pagina." in text

    def test_excess_newlines_collapsed(self):
        data = make_pdf(["linha um\n\n\n\n\n\n\nlinha dois"])
        book = load_pdf(data, "livro.pdf")
        chapter = Chapter(title="tudo", start_page=0, end_page=0)
        text = extract_text(book, chapter)
        assert "\n\n\n" not in text


class TestBoilerplate:
    def test_repeated_header_removed(self):
        data = make_pdf(
            [
                "Licença Creative Commons Atribuição\nprimeiro conteudo aqui.",
                "Licença Creative Commons Atribuição\nsegundo conteudo aqui.",
                "Licença Creative Commons Atribuição\nterceiro conteudo aqui.",
            ]
        )
        book = load_pdf(data, "livro.pdf")
        chapter = Chapter(title="tudo", start_page=0, end_page=2)
        text = extract_text(book, chapter)
        assert "Licença" not in text
        assert "primeiro conteudo" in text
        assert "terceiro conteudo" in text

    def test_page_number_lines_removed(self):
        data = make_pdf(
            ["Licença X\nconteudo um.\n12", "Licença X\nconteudo dois.\n13"]
        )
        book = load_pdf(data, "livro.pdf")
        chapter = Chapter(title="tudo", start_page=0, end_page=1)
        text = extract_text(book, chapter)
        assert "Licença" not in text
        assert not re.search(r"\b12\b", text)
        assert "conteudo um." in text

    def test_single_page_untouched(self):
        data = make_pdf(["Licença repetida\ntexto do capitulo."])
        book = load_pdf(data, "livro.pdf")
        chapter = Chapter(title="tudo", start_page=0, end_page=0)
        text = extract_text(book, chapter)
        assert "Licença repetida" in text

    def test_body_text_preserved(self):
        data = make_pdf(
            ["cabeçalho\nlinha comum numero um.", "cabeçalho\nlinha diversa numero dois."]
        )
        book = load_pdf(data, "livro.pdf")
        chapter = Chapter(title="tudo", start_page=0, end_page=1)
        text = extract_text(book, chapter)
        assert "cabeçalho" not in text
        assert "linha comum numero um." in text
        assert "linha diversa numero dois." in text

    def test_short_lines_not_removal_candidates(self):
        # linha de 2+ chars repetida entra em boilerplate; linha curta isolada fica
        data = make_pdf(["ab\ntexto um.", "ab\ntexto dois."])
        book = load_pdf(data, "livro.pdf")
        chapter = Chapter(title="tudo", start_page=0, end_page=1)
        text = extract_text(book, chapter)
        assert "ab" in text


class TestScannedHeuristic:
    def test_likely_scanned(self):
        doc = fitz.open()
        doc.new_page()  # página sem texto
        assert pdf_reader.is_likely_scanned(doc)
        doc.close()

    def test_not_scanned(self):
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "x " * 200)
        assert not pdf_reader.is_likely_scanned(doc)
        doc.close()


def test_corrupted_pdf_raises():
    with pytest.raises(Exception):
        load_pdf(b"nao-e-um-pdf", "quebrado.pdf")
