# Design: Leitor de Audiolivro a partir de PDF

**Data:** 2026-09-20
**Status:** Aprovado pelo usuário

## Visão Geral

Aplicação web local em Streamlit para converter livros em PDF em audiolivros. O usuário anexa um PDF, seleciona um capítulo (detectado automaticamente ou por intervalo manual de páginas), escolhe uma voz pt-BR e ouve/guarda o MP3 gerado.

## Requisitos

1. Upload de PDF pela interface web local (navegador).
2. Detecção automática de capítulos:
   - Prioridade 1: sumário/marcadores embutidos no PDF.
   - Prioridade 2: padrões de texto no corpo ("Capítulo 1", "CAPÍTULO II", "capitulo 3" — números arábicos ou romanos, case-insensitive).
   - Prioridade 3 (fallback): intervalo manual de páginas informado pelo usuário.
3. Síntese de voz com edge-tts (gratuito, vozes pt-BR naturais, requer internet).
4. Um MP3 por capítulo, salvo em `output/<nome-do-livro>/<índice> - <capítulo>.mp3`.
5. Player no navegador (`st.audio`) + botão de download.
6. Cache: capítulo já gerado não é regenerado.
7. Seletor de voz pt-BR (ex.: Antoni, Thalita).

## Stack

- Python 3.10+
- Streamlit (UI)
- PyMuPDF (leitura de sumário e extração de texto)
- edge-tts (síntese de fala)
- pytest (testes)

## Estrutura do Projeto

```
audiolivro/
├── app.py            # UI Streamlit
├── pdf_reader.py     # estrutura do PDF: sumário, capítulos, texto
├── tts.py            # síntese edge-tts → MP3
├── tests/
│   ├── test_pdf_reader.py
│   └── test_tts.py
├── requirements.txt
└── output/           # MP3s gerados (não versionado)
```

## Componentes

### `pdf_reader.py`

- `load_pdf(data: bytes, filename: str) -> Book`
- `Book`:
  - `filename: str`
  - `chapters: list[Chapter]`
  - `page_count: int`
- `Chapter`:
  - `title: str`
  - `start_page: int` (0-indexed, inclusiva)
  - `end_page: int` (0-indexed, inclusiva)
- Detecção em cascata:
  1. `fitz.Document.get_toc()` — se retornar entradas de nível 1, cada entrada vira um capítulo; `end_page` da entrada N é `start_page` da entrada N+1 menos 1 (última vai até fim do PDF).
  2. Varredura de texto página a página com regex `(?i)^\s*cap[íi]tulo\s+([0-9]+|[IVXLCDM]+)\b`; primeira página com match inicia novo capítulo. Se nenhum match em todo o PDF, sinaliza necessidade de modo manual.
  3. Modo manual: UI pede intervalo de páginas (início/fim, 1-indexed para o usuário, convertido internamente).
- `extract_text(book: Book, chapter: Chapter) -> str`: concatena texto das páginas do capítulo (`page.get_text()`), junta hifenização quebrada em fim de linha (ex.: "pala-\nvra" → "palavra") e remove excesso de quebras de linha.

### `tts.py`

- `VOICES: dict[str, str]` — vozes pt-BR (nome amigável → ID edge-tts).
- `chunk_text(text: str, max_chars: int = 3000) -> list[str]`: divide em blocos por parágrafo; bloco que exceder `max_chars` é cortado em fim de senteça (`.` `!` `?`) mais próximo; blocos resultantes sempre não-vazios e sem espaços nas bordas.
- `synthesize(text: str, voice: str, out_path: Path) -> Path`:
  1. Divide com `chunk_text`.
  2. Gera MP3 de cada bloco via `edge_tts.Communicate(text, voice)` (stream para arquivo temporário).
  3. Concatena bytes dos blocos em `out_path` (MP3 aceita concatenação binária de frames).
  4. Se qualquer bloco falhar, remove arquivos parciais e propaga exceção.

### `app.py`

Fluxo da UI:
1. Título + upload (`st.file_uploader`, tipo PDF).
2. Carrega PDF (`@st.cache_data` por conteúdo do arquivo) e mostra como os capítulos foram detectados (badge: "sumário embutido" / "detectado por texto" / "manual").
3. Se nenhum capítulo detectado: formulário de intervalo manual de páginas (modo 3).
4. Selectbox de capítulos + selectbox de vozes pt-BR.
5. Botão "Ouvir capítulo": calcula caminho de saída (`output/<nome-do-livro>/<índice> - <capítulo>.mp3`, com sanitização de caracteres inválidos em nomes de arquivo Windows e nome do livro truncado em 80 chars); se MP3 já existe, carrega direto; senão gera com `st.spinner`.
6. `st.audio` + `st.download_button` do MP3.
7. Estado (livro carregado, capítulo selecionado) em `st.session_state`.

## Fluxo de Dados

```
Upload PDF → load_pdf() → Book.chapters
  → seleção do usuário → extract_text() → texto do capítulo
  → chunk_text() → blocos → edge-tts → MP3s temporários
  → concatenação → output/<livro>/<capítulo>.mp3
  → st.audio / download
```

## Tratamento de Erros

- **PDF sem texto extraível** (scaneado): se total de caracteres extraídos < 100 por página em média, exibir aviso "PDF parece ser imagem (scaneado). OCR não suportado nesta versão."
- **Sem internet / edge-tts falha**: `st.error` com mensagem "Falha ao gerar áudio. Verifique sua conexão com a internet."
- **Capítulo sem texto**: aviso "Capítulo sem texto extraível (possivelmente imagens)."
- **PDF corrompido/senha**: `st.error` com causa.

## Testes

- `test_pdf_reader.py`:
  - Detecção via sumário embutido (PDF de teste gerado com PyMuPDF, com TOC).
  - Detecção via regex (PDF de teste com "Capítulo 1" no corpo, sem TOC).
  - Limites de página corretos (start/end, sem sobreposição).
  - `extract_text`: hifenização removida, texto concatenado.
- `test_tts.py`:
  - `chunk_text`: blocos ≤ max_chars, cortes em fim de frase, sem blocos vazios.
  - `synthesize`: mock de `edge_tts.Communicate` (sem rede); verifica chamadas, arquivo final e limpeza em falha.
- PDFs de teste pequenos são gerados no próprio teste com PyMuPDF (sem fixtures binárias).

## Fora de Escopo (v1)

- OCR para PDFs scaneados.
- Servir a aplicação em rede (acesso de outros dispositivos).
- Exportar MP3 combinando múltiplos capítulos em um único arquivo.
- Controle de velocidade/tom da voz.
