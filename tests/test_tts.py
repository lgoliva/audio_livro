"""Testes de tts: chunk_text e synthesize (mockado, sem rede)."""
from pathlib import Path

import pytest

import tts
from tts import chunk_text, synthesize


class TestChunkText:
    def test_short_text_single_chunk(self):
        chunks = chunk_text("Uma frase curta.")
        assert chunks == ["Uma frase curta."]

    def test_blocks_bounded(self):
        text = " ".join("paragrafo com palavras." for _ in range(500))
        chunks = chunk_text(text, max_chars=300)
        assert chunks
        assert all(len(c) <= 300 for c in chunks)
        assert all(c.strip() == c for c in chunks)

    def test_cut_at_sentence_end(self):
        sentences = [f"Frase numero {i} fim." for i in range(40)]
        text = " ".join(sentences)
        chunks = chunk_text(text, max_chars=50)
        for chunk in chunks[:-1]:
            assert chunk.endswith((".", "!", "?"))

    def test_no_empty_blocks(self):
        text = "abc " * 2000
        chunks = chunk_text(text, max_chars=100)
        assert all(c for c in chunks)

    def test_paragraphs_split(self):
        text = "primeiro paragrafo.\n\nsegundo paragrafo."
        chunks = chunk_text(text, max_chars=3000)
        assert chunks == ["primeiro paragrafo.", "segundo paragrafo."]

    def test_empty_text(self):
        assert chunk_text("   \n\n  ") == []

    def test_very_long_sentence_hard_cut(self):
        text = "x" * 7000
        chunks = chunk_text(text, max_chars=3000)
        assert all(len(c) <= 3000 for c in chunks)
        assert "".join(chunks) == text


class FakeCommunicate:
    calls: list[tuple[str, str]] = []
    fail_on: int | None = None
    payload: bytes = b"MP3DATA"

    def __init__(self, text, voice, **kwargs):
        FakeCommunicate.calls.append((text, voice))
        self.text = text
        self.voice = voice
        self.index = len(FakeCommunicate.calls) - 1

    async def save(self, path):
        if FakeCommunicate.fail_on is not None and self.index >= FakeCommunicate.fail_on:
            raise RuntimeError("falha de rede simulada")
        Path(path).write_bytes(FakeCommunicate.payload)


@pytest.fixture(autouse=True)
def reset_fake():
    FakeCommunicate.calls = []
    FakeCommunicate.fail_on = None
    yield
    tts.edge_tts.Communicate = _original


_original = tts.edge_tts.Communicate


class TestSynthesize:
    def test_calls_communicate_per_chunk_and_writes_file(self, tmp_path):
        tts.edge_tts.Communicate = FakeCommunicate
        out = tmp_path / "saida.mp3"
        result = synthesize("bloco um.\n\nbloco dois.", "pt-BR-ThalitaNeural", out)
        assert result == out
        assert [c[0] for c in FakeCommunicate.calls] == ["bloco um.", "bloco dois."]
        assert [c[1] for c in FakeCommunicate.calls] == ["pt-BR-ThalitaNeural"] * 2
        assert out.read_bytes() == FakeCommunicate.payload * 2

    def test_failure_removes_partial_output(self, tmp_path):
        tts.edge_tts.Communicate = FakeCommunicate
        FakeCommunicate.fail_on = 1
        out = tmp_path / "saida.mp3"
        with pytest.raises(RuntimeError):
            synthesize("bloco um.\n\nbloco dois.", "voice", out)
        assert not out.exists()

    def test_empty_text_raises(self, tmp_path):
        with pytest.raises(ValueError):
            synthesize("   ", "voice", tmp_path / "vazio.mp3")

    def test_progress_callback_reports_all(self, tmp_path):
        tts.edge_tts.Communicate = FakeCommunicate
        events: list[tuple[int, int]] = []
        out = tmp_path / "saida.mp3"
        synthesize("um.\n\ndois.\n\ntrês.", "voice", out, progress=lambda d, t: events.append((d, t)))
        assert events[-1] == (3, 3)
        assert len(events) == 3

    def test_creates_parent_dirs(self, tmp_path):
        tts.edge_tts.Communicate = FakeCommunicate
        out = tmp_path / "sub" / "dir" / "saida.mp3"
        synthesize("ola.", "voice", out)
        assert out.exists()
