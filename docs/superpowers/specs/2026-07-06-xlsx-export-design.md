# Design: Export para Excel (.xlsx) no DataTable

**Data:** 2026-07-06

## Problema

O `DataTable.svelte` hoje só exporta CSV. Usuários que preferem abrir os
dados já num arquivo `.xlsx` nativo (com tipos de coluna preservados, sem
depender de como o Excel interpreta o delimitador do CSV) precisam dessa
opção adicional.

## Escopo

- Adicionar export em `.xlsx` real, **mantendo** o export CSV existente —
  ambos ficam disponíveis, lado a lado.
- Mesmo escopo de dados do CSV: sempre exporta o array `dados` completo
  (não só a página atual sendo exibida).
- Fora de escopo: estilização do arquivo (negrito, cores, largura de
  coluna) — a biblioteca escolhida (ver abaixo) tem suporte limitado a
  isso na versão gratuita; não vale a pena trocar por uma lib mais pesada
  só por causa de formatação visual.

## Dependência nova

`xlsx` (SheetJS Community Edition) — biblioteca padrão de mercado pra gerar
arquivos `.xlsx` no navegador sem precisar de backend. Adicionada como
dependência de produção em `frontend/package.json`.

## Mudanças em `frontend/src/lib/components/DataTable.svelte`

### Nova função `baixarXLSX()`

- Usa `colunasEfetivas` (derivação já existente) para montar o cabeçalho.
- Monta uma matriz (array-of-arrays): primeira linha com os labels das
  colunas, linhas seguintes com os valores brutos de `dados` (o array
  **completo**, não `dadosPaginados`) na mesma ordem de `colunasEfetivas`.
- Valores `null`/`undefined` viram string vazia `''` (mesmo comportamento
  do CSV); qualquer outro valor (`number`, `string`, `boolean`) é
  preservado com seu tipo original — números continuam número na planilha
  (permitindo soma/ordenação direta no Excel), diferente do CSV onde tudo
  vira texto.
- Quebras de linha embutidas em texto (o caso dos registros com `\r\n` no
  campo `pergunta`, que exigiu tratamento especial no CSV) não precisam de
  tratamento aqui — o formato `.xlsx` suporta célula multi-linha
  nativamente, sem risco de corromper a estrutura do arquivo.
- Usa `XLSX.utils.aoa_to_sheet(matriz)` para criar a planilha,
  `XLSX.utils.book_new()` + `XLSX.utils.book_append_sheet(wb, ws, 'Dados')`
  para o workbook, e `XLSX.writeFile(wb, nomeArquivo)` para disparar o
  download — a própria biblioteca cuida do mecanismo de download
  (não precisa do Blob/`<a download>` manual usado no CSV).
- Nome do arquivo: mesma sanitização já usada no CSV —
  `${titulo.replace(/[^a-zA-Z0-9]+/g, '_')}.xlsx`.

### Rodapé (`.pagination`)

O botão único "⬇ Baixar CSV" vira dois botões lado a lado, ambos
desabilitados quando `dados.length === 0`:

```svelte
<button class="btn-ghost btn-sm" on:click={baixarCSV} disabled={dados.length === 0}>
  ⬇ CSV
</button>
<button class="btn-ghost btn-sm" on:click={baixarXLSX} disabled={dados.length === 0}>
  ⬇ Excel
</button>
```

## Testes / verificação

Sem framework de testes automatizados no frontend (consistente com o resto
do projeto). Verificação manual com Playwright real, mesmo método usado
nas correções anteriores deste componente:

- Abrir `/painel/lanc_fichas`, clicar "⬇ Excel" → arquivo `.xlsx` baixado,
  abre corretamente, mesma quantidade de linhas do CSV (47995 + cabeçalho),
  coluna `qtd` reconhecida como número (não texto) pelo Excel.
- Confirmar que os 8 registros com quebra de linha embutida em `pergunta`
  aparecem como uma única linha na planilha (célula com quebra interna),
  sem gerar linha extra/deslocada.
- Painel sem dados (array vazio) → ambos os botões ("CSV" e "Excel")
  ficam desabilitados, sem erros.
- Confirmar que o botão CSV continua funcionando como antes (nada quebrou
  no export existente).
