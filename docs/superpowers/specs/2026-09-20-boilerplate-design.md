# Design: Remoção de boilerplate (cabeçalhos/rodapés repetidos)

**Data:** 2026-09-20
**Status:** Aprovado pelo usuário (opção A)

## Problema

PDFs trazem notas repetidas em toda página (ex.: licença Creative Commons, título do
livro, número de página). Essas linhas são lidas pelo TTS embora não façam parte do
texto.

## Solução

Detecção por repetição, sem lista fixa de palavras:

1. `extract_text` coleta o texto de cada página do capítulo **antes** de concatenar.
2. Cada linha é normalizada (espaços colapsados, sem bordas).
3. Linha presente em ≥50% das páginas do capítulo (e em ≥2 páginas) é considerada
   boilerplate e removida de todas as páginas. Capítulos com 1 página não têm nada
   removido (não há como inferir repetição).
4. Linhas que são apenas número (ex.: "42") são sempre removidas (numeração de página).

## Componentes

- `pdf_reader.py`: nova função `_drop_running_boilerplate(pages: list[str]) -> list[str]`,
  chamada por `extract_text`. Nenhuma mudança de assinatura pública.
- Testes: cabeçalho repetido removido; número de página removido; capítulo de 1 página
  intacto; texto normal preservado.

## Fora de escopo

- Filtrar por palavras-chave ("licença", "creative commons").
- Remoção em capítulos de 1 página.
