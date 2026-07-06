# Design: Paginação client-side e export CSV no DataTable

**Data:** 2026-07-06

## Problema

Widgets do tipo `table` em um painel (ex: `/painel/lanc_fichas`) podem retornar
dezenas de milhares de linhas em uma única resposta da API — o backend não
implementa paginação no servidor, retorna o resultado completo da query de
uma vez (confirmado: 47.995 linhas em uma chamada). Hoje o `DataTable.svelte`
renderiza todas essas linhas de uma vez no DOM, sem forma de o usuário
escolher quantos itens ver por página, e sem forma de exportar os dados para
Excel.

## Contexto: contrato de paginação existente é código morto

`DataTable.svelte` já tem props `total`/`page` e despacha um evento
`dispatch('page', ...)` pensado para paginação controlada pelo componente
pai. `frontend/src/routes/painel/[slug]/+page.svelte` — o único lugar do
código onde `DataTable` é usado — nunca escuta esse evento nem passa
`total`/`page`. Esse contrato nunca funcionou. Como não há outro
consumidor do componente, este design **remove esse contrato e substitui
por paginação totalmente interna ao componente**.

## Escopo

- Paginação client-side sobre o array `dados` já carregado (sem mudança no
  backend/`resolver_query`).
- Seletor de itens por página: 10, 50, 100 ou 500 — padrão 50.
- Botão de download que exporta **todas** as linhas de `dados` (não só a
  página atual) em CSV.
- Fora de escopo: paginação no servidor, exportação em `.xlsx` nativo
  (adicionaria uma dependência nova — `xlsx`/SheetJS — sem necessidade,
  CSV já abre corretamente no Excel), exportação de apenas a página atual.

## Mudanças em `frontend/src/lib/components/DataTable.svelte`

### Props

- `colunas` (mantém, já teve fallback adicionado no fix anterior)
- `dados` (mantém)
- `titulo` (novo, opcional, default `'dados'`) — usado no nome do arquivo
  exportado
- **Remove:** `total`, `page` (não usados por nenhum consumidor real)

### Estado interno de paginação

```js
let paginaAtual   = 1;
let tamanhoPagina = 50;

const TAMANHOS_PAGINA = [10, 50, 100, 500];

$: totalPaginas = Math.max(1, Math.ceil(dados.length / tamanhoPagina));
$: dadosPaginados = dados.slice(
  (paginaAtual - 1) * tamanhoPagina,
  paginaAtual * tamanhoPagina
);

// Reseta para a página 1 quando os dados mudam (novo filtro aplicado)
// ou o tamanho de página muda, para nunca ficar numa página vazia/inválida.
$: dados, tamanhoPagina, (paginaAtual = 1);
```

O corpo da tabela (`<tbody>`) itera sobre `dadosPaginados` em vez de
`dados`. Isso também resolve, como efeito colateral desejado, o problema de
renderizar dezenas de milhares de `<tr>` simultaneamente no DOM.

### Rodapé (`.pagination`)

Reorganizado para conter, da esquerda para a direita:

1. Botão "Baixar CSV" (ver seção seguinte)
2. Contagem real: `{dados.length} registros`
3. Seletor "Itens por página": `<select bind:value={tamanhoPagina}>` com as
   opções 10/50/100/500
4. Botões "← Anterior" / "Pág {paginaAtual} / {totalPaginas}" / "Próxima →",
   agora efetivamente funcionais (incrementam/decrementam `paginaAtual`,
   desabilitados nos limites)

### Export CSV

Função `baixarCSV()`, acionada pelo clique do botão:

- Usa `colunasEfetivas` (já existente, derivado das chaves da primeira
  linha quando `colunas` não é passado) como cabeçalho.
- Usa o array `dados` **completo** (não `dadosPaginados`) — a exportação
  sempre traz o resultado inteiro da query, independente da paginação em
  tela.
- Separador `;` (ponto e vírgula) — convenção do Excel em português, que
  usa vírgula como separador decimal e portanto espera `;` como delimitador
  de campo em CSV.
- Prefixo BOM UTF-8 (`﻿`) no início do arquivo, para o Excel
  reconhecer corretamente acentuação/caracteres especiais.
- Escape por campo: valores contendo `;`, aspas (`"`) ou quebra de linha
  são envolvidos em aspas duplas, com aspas internas duplicadas (`"` →
  `""`) — regra padrão de CSV.
- Nome do arquivo: `${tituloSanitizado}.csv`, onde `tituloSanitizado`
  substitui espaços e caracteres não alfanuméricos por `_` (evita nomes de
  arquivo problemáticos), a partir do prop `titulo`.
- Mecanismo: monta uma `Blob` com o texto CSV e `type: 'text/csv;charset=utf-8;'`,
  cria uma `URL.createObjectURL(blob)`, dispara o download via um elemento
  `<a download>` temporário (criado, clicado via JS, removido), e libera a
  URL com `URL.revokeObjectURL` — tudo nativo do navegador, sem dependência
  nova no `package.json`.

## Mudança em `frontend/src/routes/painel/[slug]/+page.svelte`

Uma única alteração na chamada existente do componente (linha ~197):

```svelte
{:else if ind.query_tipo === 'table'}
  <DataTable dados={ind.dados} titulo={ind.titulo || ind.query_slug} />
```

## Testes / verificação

Sem framework de testes automatizados no frontend (consistente com o resto
do projeto). Verificação manual, incluindo com Playwright real (mesmo
método usado na correção anterior deste componente):

- Abrir `/painel/lanc_fichas` (empresa com dados, ex: Prats) → confirmar
  que só 50 linhas aparecem no DOM inicialmente, contagem mostra o total
  real (ex: "47995 registros"), navegação Anterior/Próxima funciona e
  desabilita nos limites.
- Trocar o seletor de itens por página (10/50/100/500) → tabela
  re-renderiza com a quantidade certa, volta para a página 1.
- Aplicar um novo filtro de período → paginação volta para a página 1
  automaticamente.
- Clicar "Baixar CSV" → arquivo baixado abre no Excel com acentuação
  correta, todas as linhas presentes (não só a página atual), nome de
  arquivo baseado no título do indicador.
- Caso de painel sem dados (array vazio) → sem erros, "0 registros",
  paginação mostra "Pág 1 / 1" sem quebrar, botão de download gera um CSV
  só com cabeçalho (ou fica desabilitado — decidir na implementação, ver
  nota abaixo).

**Nota de implementação:** o botão "Baixar CSV" deve ficar desabilitado
quando `dados.length === 0`, para não gerar um arquivo vazio sem sentido.
