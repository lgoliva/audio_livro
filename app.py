"""Leitor de Audiolivro — UI Streamlit."""
from __future__ import annotations

import re
from pathlib import Path

import fitz
import streamlit as st

from pdf_reader import Chapter, extract_text, is_likely_scanned, load_pdf
from tts import VOICES, synthesize

OUTPUT_DIR = Path("output")

st.set_page_config(page_title="Audiolivro", page_icon="🎧", layout="centered")

st.title("🎧 Leitor de Audiolivro (PDF → MP3)")

BAD_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(name: str, max_len: int = 80) -> str:
    cleaned = BAD_FILENAME_RE.sub("_", name).strip(" .")
    return cleaned[:max_len] or "livro"


@st.cache_data(show_spinner="Carregando PDF...")
def cached_load_pdf(data: bytes, filename: str):
    return load_pdf(data, filename)


def chapter_output_path(book, index: int, chapter: Chapter) -> Path:
    safe_book = sanitize(book.filename.rsplit(".", 1)[0])
    safe_title = sanitize(chapter.title, max_len=100)
    return OUTPUT_DIR / safe_book / f"{index + 1:02d} - {safe_title}.mp3"


def detection_badge(book) -> str:
    if not book.chapters:
        return "manual"
    doc = fitz.open(stream=book.data, filetype="pdf")
    try:
        if doc.get_toc() and any(e[0] == 1 for e in doc.get_toc()):
            return "sumário embutido"
    finally:
        doc.close()
    return "detectado por texto"


uploaded = st.file_uploader("Anexe um livro em PDF", type=["pdf"])

if uploaded is None:
    st.info("Anexe um PDF para começar.")
    st.stop()

data = uploaded.getvalue()

try:
    book = cached_load_pdf(data, uploaded.name)
except Exception as exc:
    st.error(f"Não foi possível abrir o PDF ({exc}). Arquivo corrompido ou protegido por senha?")
    st.stop()

doc_probe = fitz.open(stream=data, filetype="pdf")
try:
    scanned = is_likely_scanned(doc_probe)
finally:
    doc_probe.close()

if scanned:
    st.warning(
        "PDF parece ser imagem (scaneado). OCR não suportado nesta versão."
        " Capítulos podem não ser detectados e o texto estará vazio."
    )

badge = detection_badge(book)
st.caption(f"Detecção de capítulos: **{badge}** · {book.page_count} páginas")

chapters = book.chapters

if not chapters:
    st.warning("Nenhum capítulo detectado automaticamente. Informe o intervalo manualmente.")
    with st.form("manual_range"):
        col1, col2 = st.columns(2)
        first = col1.number_input("Primeira página", min_value=1, max_value=book.page_count, value=1)
        last = col2.number_input(
            "Última página", min_value=int(first), max_value=book.page_count, value=book.page_count
        )
        title = st.text_input("Título do capítulo", value="Capítulo manual")
        submitted = st.form_submit_button("Criar capítulo manual")
    if submitted:
        chapters = [
            Chapter(
                title=title.strip() or "Capítulo manual",
                start_page=int(first) - 1,
                end_page=int(last) - 1,
            )
        ]
    else:
        st.stop()

book.chapters = chapters

col_sel, col_voice = st.columns(2)
with col_sel:
    chapter_index = st.selectbox(
        "Capítulo",
        range(len(chapters)),
        format_func=lambda i: f"{i + 1}. {chapters[i].title}",
    )
with col_voice:
    voice_name = st.selectbox("Voz (pt-BR)", list(VOICES.keys()), index=1)

voice_id = VOICES[voice_name]
chapter = chapters[chapter_index]

if st.button("🔊 Ouvir capítulo", type="primary"):
    try:
        text = extract_text(book, chapter)
    except Exception:
        text = ""
    if not text:
        st.warning("Capítulo sem texto extraível (possivelmente imagens).")
        st.stop()

    out_path = chapter_output_path(book, chapter_index, chapter)
    try:
        if not out_path.exists():
            bar = st.progress(0.0, text="Gerando áudio com edge-tts...")

            def update(done: int, total: int) -> None:
                bar.progress(done / total, text=f"Bloco {done}/{total}...")

            synthesize(text, voice_id, out_path, progress=update)
            bar.empty()
    except Exception:
        st.error("Falha ao gerar áudio. Verifique sua conexão com a internet.")
        st.stop()

    st.success(f"MP3 pronto: `{out_path}`")
    st.audio(str(out_path), format="audio/mp3")
    st.download_button(
        "⬇️ Baixar MP3",
        data=out_path.read_bytes(),
        file_name=out_path.name,
        mime="audio/mpeg",
    )
