"""Leitor de Audiolivro — Interface Desktop (CustomTkinter)."""
from __future__ import annotations

import os
import re
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import fitz

from pdf_reader import Chapter, extract_text, is_likely_scanned, load_pdf
from tts import DEFAULT_VOICE, VOICES, synthesize

OUTPUT_DIR = Path("output")
BAD_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(name: str, max_len: int = 80) -> str:
    cleaned = BAD_FILENAME_RE.sub("_", name).strip(" .")
    return cleaned[:max_len] or "livro"


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


def open_file_or_folder(path: Path | str) -> None:
    """Abre arquivo ou pasta no gerenciador padrão do sistema operacional."""
    p = Path(path).resolve()
    if sys.platform == "win32":
        os.startfile(str(p))
    elif sys.platform == "darwin":
        import subprocess

        subprocess.Popen(["open", str(p)])
    else:
        import subprocess

        subprocess.Popen(["xdg-open", str(p)])


class AudioBookApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("🎧 Leitor de Audiolivro (PDF → MP3)")
        self.geometry("860x760")
        self.minsize(780, 680)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.book = None
        self.current_pdf_path: Path | None = None
        self.is_synthesizing = False
        self.last_generated_mp3: Path | None = None

        self._build_ui()

    def _build_ui(self):
        # Container principal com scroll
        self.main_scroll = ctk.CTkScrollableFrame(self, corner_radius=0)
        self.main_scroll.pack(fill="both", expand=True, padx=15, pady=15)

        # Cabeçalho
        header_frame = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 15))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="🎧 Leitor de Audiolivro",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = ctk.CTkLabel(
            header_frame,
            text="Converta capítulos de livros em PDF em audiolivros MP3 de alta qualidade.",
            text_color="gray70",
            font=ctk.CTkFont(size=13),
        )
        subtitle_lbl.pack(anchor="w")

        # Card 1: Seleção de PDF
        self._build_pdf_card()

        # Card 2: Capítulos e Configurações
        self._build_settings_card()

        # Card 3: Pré-visualização do texto
        self._build_preview_card()

        # Card 4: Geração de Áudio e Ações
        self._build_generation_card()

    def _build_pdf_card(self):
        card = ctk.CTkFrame(self.main_scroll, corner_radius=12)
        card.pack(fill="x", pady=(0, 15), padx=5)

        card_title = ctk.CTkLabel(
            card,
            text="1. Arquivo PDF",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        card_title.pack(anchor="w", padx=15, pady=(12, 6))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=(0, 10))

        self.btn_select_pdf = ctk.CTkButton(
            row,
            text="📁 Selecionar Livro (PDF)",
            command=self._on_select_pdf,
            font=ctk.CTkFont(weight="bold"),
            width=200,
            height=36,
        )
        self.btn_select_pdf.pack(side="left")

        self.lbl_pdf_info = ctk.CTkLabel(
            row,
            text="Nenhum arquivo selecionado",
            text_color="gray70",
            font=ctk.CTkFont(size=13),
        )
        self.lbl_pdf_info.pack(side="left", padx=15)

        self.lbl_badge = ctk.CTkLabel(
            card,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38bdf8",
        )
        self.lbl_badge.pack(anchor="w", padx=15, pady=(0, 10))

        self.lbl_scanned_warn = ctk.CTkLabel(
            card,
            text="⚠️ PDF parece ser escaneado (imagem). Capítulos e textos podem estar vazios.",
            text_color="#f87171",
            font=ctk.CTkFont(size=12),
        )
        # Oculto por padrão

    def _build_settings_card(self):
        self.card_settings = ctk.CTkFrame(self.main_scroll, corner_radius=12)
        self.card_settings.pack(fill="x", pady=(0, 15), padx=5)

        card_title = ctk.CTkLabel(
            self.card_settings,
            text="2. Capítulos & Voz",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        card_title.pack(anchor="w", padx=15, pady=(12, 10))

        # Linha de Seleção de Capítulo
        cap_row = ctk.CTkFrame(self.card_settings, fg_color="transparent")
        cap_row.pack(fill="x", padx=15, pady=(0, 10))

        lbl_cap = ctk.CTkLabel(cap_row, text="Capítulo:", width=80, anchor="w")
        lbl_cap.pack(side="left")

        self.combo_chapters = ctk.CTkOptionMenu(
            cap_row,
            values=["Nenhum capítulo disponível"],
            command=self._on_chapter_changed,
            height=34,
        )
        self.combo_chapters.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.btn_toggle_manual = ctk.CTkButton(
            cap_row,
            text="Modo Manual",
            width=110,
            command=self._toggle_manual_frame,
            fg_color="gray30",
            hover_color="gray40",
        )
        self.btn_toggle_manual.pack(side="left")

        # Frame para entrada manual de capítulo (inicialmente recolhido)
        self.manual_frame = ctk.CTkFrame(self.card_settings, fg_color=("gray85", "gray20"), corner_radius=8)
        
        man_title = ctk.CTkLabel(
            self.manual_frame,
            text="Definir Capítulo Manualmente",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        man_title.pack(anchor="w", padx=10, pady=(8, 4))

        man_grid = ctk.CTkFrame(self.manual_frame, fg_color="transparent")
        man_grid.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkLabel(man_grid, text="Pág Inicial:").grid(row=0, column=0, sticky="w", padx=5, pady=4)
        self.entry_start_page = ctk.CTkEntry(man_grid, width=70)
        self.entry_start_page.grid(row=0, column=1, padx=5, pady=4)
        self.entry_start_page.insert(0, "1")

        ctk.CTkLabel(man_grid, text="Pág Final:").grid(row=0, column=2, sticky="w", padx=5, pady=4)
        self.entry_end_page = ctk.CTkEntry(man_grid, width=70)
        self.entry_end_page.grid(row=0, column=3, padx=5, pady=4)
        self.entry_end_page.insert(0, "1")

        ctk.CTkLabel(man_grid, text="Título:").grid(row=0, column=4, sticky="w", padx=5, pady=4)
        self.entry_chapter_title = ctk.CTkEntry(man_grid, width=180)
        self.entry_chapter_title.grid(row=0, column=5, padx=5, pady=4)
        self.entry_chapter_title.insert(0, "Capítulo Manual")

        self.btn_add_manual = ctk.CTkButton(
            man_grid,
            text="Adicionar",
            width=80,
            command=self._apply_manual_chapter,
        )
        self.btn_add_manual.grid(row=0, column=6, padx=10, pady=4)

        # Linha de Seleção de Voz
        voice_row = ctk.CTkFrame(self.card_settings, fg_color="transparent")
        voice_row.pack(fill="x", padx=15, pady=(0, 15))

        lbl_voice = ctk.CTkLabel(voice_row, text="Voz pt-BR:", width=80, anchor="w")
        lbl_voice.pack(side="left")

        # Procura nome da voz default
        default_voice_name = next(
            (name for name, vid in VOICES.items() if vid == DEFAULT_VOICE),
            list(VOICES.keys())[0],
        )

        self.combo_voices = ctk.CTkOptionMenu(
            voice_row,
            values=list(VOICES.keys()),
            height=34,
            width=220,
        )
        self.combo_voices.set(default_voice_name)
        self.combo_voices.pack(side="left")

    def _build_preview_card(self):
        card = ctk.CTkFrame(self.main_scroll, corner_radius=12)
        card.pack(fill="x", pady=(0, 15), padx=5)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(10, 6))

        card_title = ctk.CTkLabel(
            header,
            text="3. Pré-visualização do Texto",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        card_title.pack(side="left")

        self.lbl_char_count = ctk.CTkLabel(
            header,
            text="0 caracteres",
            text_color="gray70",
            font=ctk.CTkFont(size=12),
        )
        self.lbl_char_count.pack(side="right")

        self.txt_preview = ctk.CTkTextbox(card, height=120, font=ctk.CTkFont(size=12))
        self.txt_preview.pack(fill="x", padx=15, pady=(0, 12))
        self.txt_preview.insert("0.0", "Selecione um PDF e um capítulo para visualizar o texto extraído.")
        self.txt_preview.configure(state="disabled")

    def _build_generation_card(self):
        card = ctk.CTkFrame(self.main_scroll, corner_radius=12)
        card.pack(fill="x", pady=(0, 15), padx=5)

        card_title = ctk.CTkLabel(
            card,
            text="4. Síntese e Download",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        card_title.pack(anchor="w", padx=15, pady=(12, 10))

        # Ações
        act_row = ctk.CTkFrame(card, fg_color="transparent")
        act_row.pack(fill="x", padx=15, pady=(0, 10))

        self.btn_generate = ctk.CTkButton(
            act_row,
            text="🔊 Gerar Audiolivro (MP3)",
            command=self._start_synthesis,
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            width=230,
        )
        self.btn_generate.pack(side="left")

        self.chk_force = ctk.CTkCheckBox(
            act_row,
            text="Forçar regeração (ignorar cache)",
            font=ctk.CTkFont(size=12),
        )
        self.chk_force.pack(side="left", padx=15)

        # Barra de Progresso
        prog_row = ctk.CTkFrame(card, fg_color="transparent")
        prog_row.pack(fill="x", padx=15, pady=(0, 10))

        self.prog_bar = ctk.CTkProgressBar(prog_row)
        self.prog_bar.pack(fill="x", expand=True, pady=(5, 5))
        self.prog_bar.set(0.0)

        self.lbl_status = ctk.CTkLabel(
            card,
            text="Pronto.",
            text_color="gray70",
            font=ctk.CTkFont(size=13),
        )
        self.lbl_status.pack(anchor="w", padx=15, pady=(0, 10))

        # Painel pós geração
        self.post_frame = ctk.CTkFrame(card, fg_color=("gray85", "gray20"), corner_radius=8)
        
        self.lbl_finished_path = ctk.CTkLabel(
            self.post_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#4ade80",
            wraplength=700,
            justify="left",
        )
        self.lbl_finished_path.pack(anchor="w", padx=12, pady=(8, 6))

        post_btns = ctk.CTkFrame(self.post_frame, fg_color="transparent")
        post_btns.pack(fill="x", padx=12, pady=(0, 8))

        self.btn_play_audio = ctk.CTkButton(
            post_btns,
            text="▶️ Reproduzir Áudio",
            command=self._play_audio,
            width=150,
            fg_color="#10b981",
            hover_color="#059669",
        )
        self.btn_play_audio.pack(side="left", padx=(0, 10))

        self.btn_open_folder = ctk.CTkButton(
            post_btns,
            text="📂 Abrir Pasta",
            command=self._open_output_folder,
            width=130,
            fg_color="gray30",
            hover_color="gray40",
        )
        self.btn_open_folder.pack(side="left")

    def _on_select_pdf(self):
        file_path = filedialog.askopenfilename(
            title="Selecione um arquivo PDF",
            filetypes=[("Arquivos PDF (*.pdf)", "*.pdf"), ("Todos os arquivos", "*.*")],
        )
        if not file_path:
            return

        path = Path(file_path)
        try:
            data = path.read_bytes()
            book = load_pdf(data, path.name)
        except Exception as exc:
            messagebox.showerror(
                "Erro ao abrir PDF",
                f"Não foi possível abrir o arquivo ({exc}). O arquivo está corrompido ou protegido por senha?",
            )
            return

        self.current_pdf_path = path
        self.book = book

        # Atualiza informações na UI
        self.lbl_pdf_info.configure(
            text=f"{path.name} ({book.page_count} páginas)",
            text_color=("gray10", "gray90"),
        )

        # Checar se é escaneado
        doc_probe = fitz.open(stream=data, filetype="pdf")
        try:
            scanned = is_likely_scanned(doc_probe)
        finally:
            doc_probe.close()

        if scanned:
            self.lbl_scanned_warn.pack(anchor="w", padx=15, pady=(0, 10))
        else:
            self.lbl_scanned_warn.pack_forget()

        badge = detection_badge(book)
        self.lbl_badge.configure(text=f"Detecção de capítulos: {badge}")

        # Atualiza lista de capítulos
        self._refresh_chapters_dropdown()

    def _refresh_chapters_dropdown(self):
        if not self.book or not self.book.chapters:
            self.combo_chapters.configure(values=["Nenhum capítulo detectado"])
            self.combo_chapters.set("Nenhum capítulo detectado")
            self._update_preview("")
            # Abre modo manual automaticamente se não houver capítulos
            self._show_manual_frame(True)
            return

        items = [
            f"{i + 1}. {ch.title} (págs {ch.start_page + 1}-{ch.end_page + 1})"
            for i, ch in enumerate(self.book.chapters)
        ]
        self.combo_chapters.configure(values=items)
        self.combo_chapters.set(items[0])
        self._on_chapter_changed(items[0])

    def _on_chapter_changed(self, choice: str):
        if not self.book or not self.book.chapters:
            return
        idx = self._get_selected_chapter_index()
        if idx is not None and 0 <= idx < len(self.book.chapters):
            chapter = self.book.chapters[idx]
            try:
                text = extract_text(self.book, chapter)
            except Exception:
                text = ""
            self._update_preview(text)

    def _get_selected_chapter_index(self) -> int | None:
        if not self.book or not self.book.chapters:
            return None
        choice = self.combo_chapters.get()
        match = re.match(r"^(\d+)\.", choice)
        if match:
            return int(match.group(1)) - 1
        return 0

    def _update_preview(self, text: str):
        self.txt_preview.configure(state="normal")
        self.txt_preview.delete("0.0", "end")
        if text:
            self.txt_preview.insert("0.0", text)
            self.lbl_char_count.configure(text=f"{len(text):,} caracteres")
        else:
            self.txt_preview.insert("0.0", "Nenhum texto disponível para este capítulo.")
            self.lbl_char_count.configure(text="0 caracteres")
        self.txt_preview.configure(state="disabled")

    def _toggle_manual_frame(self):
        if self.manual_frame.winfo_ismapped():
            self._show_manual_frame(False)
        else:
            self._show_manual_frame(True)

    def _show_manual_frame(self, show: bool):
        if show:
            self.manual_frame.pack(fill="x", padx=15, pady=(0, 10))
            self.btn_toggle_manual.configure(text="Ocultar Manual")
            if self.book:
                self.entry_start_page.delete(0, "end")
                self.entry_start_page.insert(0, "1")
                self.entry_end_page.delete(0, "end")
                self.entry_end_page.insert(0, str(self.book.page_count))
        else:
            self.manual_frame.pack_forget()
            self.btn_toggle_manual.configure(text="Modo Manual")

    def _apply_manual_chapter(self):
        if not self.book:
            messagebox.showwarning("Aviso", "Selecione um PDF primeiro.")
            return

        try:
            start_p = int(self.entry_start_page.get().strip())
            end_p = int(self.entry_end_page.get().strip())
        except ValueError:
            messagebox.showerror("Erro", "As páginas inicial e final devem ser números inteiros.")
            return

        if start_p < 1 or end_p > self.book.page_count or start_p > end_p:
            messagebox.showerror(
                "Erro",
                f"Intervalo de páginas inválido! O livro possui páginas de 1 a {self.book.page_count}.",
            )
            return

        title = self.entry_chapter_title.get().strip() or "Capítulo Manual"
        new_chapter = Chapter(title=title, start_page=start_p - 1, end_page=end_p - 1)
        self.book.chapters.append(new_chapter)
        self._refresh_chapters_dropdown()
        # Seleciona o capítulo recém-adicionado
        new_index = len(self.book.chapters) - 1
        items = self.combo_chapters.cget("values")
        self.combo_chapters.set(items[new_index])
        self._on_chapter_changed(items[new_index])
        messagebox.showinfo("Sucesso", f"Capítulo '{title}' adicionado com sucesso!")

    def _start_synthesis(self):
        if self.is_synthesizing:
            return

        if not self.book or not self.book.chapters:
            messagebox.showwarning("Aviso", "Selecione um PDF e um capítulo válido.")
            return

        idx = self._get_selected_chapter_index()
        if idx is None:
            messagebox.showwarning("Aviso", "Selecione um capítulo válido.")
            return

        chapter = self.book.chapters[idx]

        try:
            text = extract_text(self.book, chapter)
        except Exception:
            text = ""

        if not text.strip():
            messagebox.showwarning("Aviso", "Capítulo sem texto extraível (possivelmente imagens).")
            return

        voice_name = self.combo_voices.get()
        voice_id = VOICES.get(voice_name, DEFAULT_VOICE)
        out_path = chapter_output_path(self.book, idx, chapter)
        force_regen = bool(self.chk_force.get())

        if out_path.exists() and not force_regen:
            self.last_generated_mp3 = out_path
            self.lbl_status.configure(text="MP3 carregado do cache!")
            self.prog_bar.set(1.0)
            self._show_post_generation(out_path)
            return

        # Inicia síntese em thread separada para não travar a interface
        self.is_synthesizing = True
        self.btn_generate.configure(state="disabled")
        self.btn_select_pdf.configure(state="disabled")
        self.prog_bar.set(0.0)
        self.lbl_status.configure(text="Conectando ao edge-tts...")
        self.post_frame.pack_forget()

        threading.Thread(
            target=self._synthesis_worker,
            args=(text, voice_id, out_path),
            daemon=True,
        ).start()

    def _synthesis_worker(self, text: str, voice_id: str, out_path: Path):
        def progress_cb(done: int, total: int):
            self.after(0, self._update_progress_ui, done, total)

        try:
            synthesize(text, voice_id, out_path, progress=progress_cb)
            self.after(0, self._on_synthesis_success, out_path)
        except Exception as exc:
            self.after(0, self._on_synthesis_error, str(exc))

    def _update_progress_ui(self, done: int, total: int):
        frac = done / total if total > 0 else 0.0
        self.prog_bar.set(frac)
        self.lbl_status.configure(text=f"Processando blocos de áudio: {done}/{total} ({int(frac * 100)}%)...")

    def _on_synthesis_success(self, out_path: Path):
        self.is_synthesizing = False
        self.btn_generate.configure(state="normal")
        self.btn_select_pdf.configure(state="normal")
        self.prog_bar.set(1.0)
        self.lbl_status.configure(text="Áudio gerado com sucesso!")
        self.last_generated_mp3 = out_path
        self._show_post_generation(out_path)

    def _on_synthesis_error(self, err_msg: str):
        self.is_synthesizing = False
        self.btn_generate.configure(state="normal")
        self.btn_select_pdf.configure(state="normal")
        self.lbl_status.configure(text="Erro ao gerar áudio.")
        messagebox.showerror(
            "Falha ao gerar áudio",
            f"Ocorreu um erro durante a síntese de voz.\nVerifique sua conexão com a internet.\n\nDetalhes: {err_msg}",
        )

    def _show_post_generation(self, out_path: Path):
        self.lbl_finished_path.configure(text=f"Arquivo gerado: {out_path}")
        self.post_frame.pack(fill="x", padx=15, pady=(0, 10))

    def _play_audio(self):
        if self.last_generated_mp3 and self.last_generated_mp3.exists():
            open_file_or_folder(self.last_generated_mp3)
        else:
            messagebox.showwarning("Aviso", "O arquivo de áudio não foi encontrado.")

    def _open_output_folder(self):
        if self.last_generated_mp3:
            folder = self.last_generated_mp3.parent
        else:
            folder = OUTPUT_DIR.resolve()
        folder.mkdir(parents=True, exist_ok=True)
        open_file_or_folder(folder)


def main():
    app = AudioBookApp()
    app.mainloop()


if __name__ == "__main__":
    main()
