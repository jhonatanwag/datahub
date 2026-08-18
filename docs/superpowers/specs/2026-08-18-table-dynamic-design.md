# Query tipo `table_dynamic` — agrupamento, agregação e drill-down — Design

## Contexto

Baseado no desenho em `docs/table_dynamic.png`: um novo tipo de query,
`table_dynamic`, onde o SQL cadastrado devolve linhas planas (sem `GROUP BY`),
e a tela de configuração permite:

1. Escolher uma ou mais colunas de **agrupamento** (em ordem — 1º nível, 2º
   nível...), formando uma árvore visual (linha de grupo em destaque + linhas
   de detalhe embaixo).
2. Escolher uma ou mais **agregações** (coluna + função: soma, contagem,
   média, mínimo, máximo) mostradas na linha de cada grupo, em qualquer nível
   da árvore.
3. Configurar uma **subconsulta** (uma query já cadastrada, de qualquer tipo)
   ligada a um botão "Ações" em cada linha de detalhe. Ao clicar, uma ou mais
   colunas da linha são passadas como parâmetro pra essa subconsulta, e o
   resultado abre num dialog — renderizado conforme o **tipo da própria
   subconsulta** (table/kpi/chart/map), sem precisar escolher de novo.

## Decisões

- **Agrupamento e agregação são calculados no frontend**, em cima do
  resultado plano que a query já devolve hoje (mesmo formato `{colunas,
  dados}` de qualquer outro tipo) — sem exigir `GROUP BY` no SQL. Mantém o
  backend genérico (`resolver_query` não muda sua lógica de execução) e seguo
  o mesmo espírito "resolve em tempo de view" já usado no botão de impressão
  (`docs/superpowers/specs/2026-07-26-botao-impressao-table-design.md`).
- **Múltiplos níveis de agrupamento, múltiplas agregações por grupo,
  múltiplos mapeamentos coluna→parâmetro** pra subconsulta — todos como
  listas ordenadas configuráveis (não fixo em 1 de cada).
- **Subconsulta é uma query comum já cadastrada** (qualquer `tipo` existente
  — não um conceito novo). O dialog decide o que renderizar olhando o `tipo`
  dela, do mesmo jeito que `painel/[slug]/+page.svelte` já decide pros
  indicadores do painel.
- **Uma subconsulta só por query `table_dynamic`** (um botão "Ações" por
  linha, não vários) — como no desenho.
- **Dialog é um componente novo** (`Modal.svelte`) — não existe nenhum modal
  reutilizável no projeto hoje (confirmado por busca em todo `frontend/src`).
- Dentro do dialog, **reaproveita os componentes de renderização já
  existentes** (`DataTable`, `KPICard`, `ChartPanel`, `MapPanel`) — o mesmo
  switch por tipo que já existe em `painel/[slug]/+page.svelte`.
- **Tabelas filhas para as 3 listas** (agrupamentos, agregações, mapeamento
  de parâmetros da subconsulta), seguindo o padrão já estabelecido por
  `query_parametros` (não um JSON numa coluna só) — consistente com o resto
  do schema, que é aditivo/coluna-fixa mas já usa tabela filha pra listas de
  tamanho variável.

## Modelo de dados

```sql
ALTER TABLE queries ADD COLUMN subquery_id INTEGER REFERENCES queries(id);

CREATE TABLE query_agrupamentos (
    id        SERIAL PRIMARY KEY,
    query_id  INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    coluna    TEXT NOT NULL,
    ordem     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qagrup_query_id ON query_agrupamentos(query_id);

CREATE TABLE query_agregacoes (
    id        SERIAL PRIMARY KEY,
    query_id  INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    coluna    TEXT NOT NULL,
    funcao    VARCHAR(10) NOT NULL,  -- soma|contagem|media|minimo|maximo
    label     TEXT,
    ordem     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qagreg_query_id ON query_agregacoes(query_id);

-- "query_id" aqui é a query table_dynamic "pai" (dona do botão de ação)
CREATE TABLE query_subquery_parametros (
    id                SERIAL PRIMARY KEY,
    query_id          INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    coluna_origem     TEXT NOT NULL,   -- coluna da linha clicada
    parametro_destino TEXT NOT NULL,   -- deve bater com um query_parametros.nome da subconsulta
    ordem             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qsqp_query_id ON query_subquery_parametros(query_id);
```

**Migração:** projeto não tem sistema de migrations — refletir em
`scripts/init-db.sql` (seed local) e `scripts/init-meta-prod.sql` (schema
prod), e documentar como pendência manual em produção no README, seção
"Deltas de schema pendentes" (mesmo processo dos specs anteriores).

## Backend

### `backend/routes/queries.py`

- `TIPOS_VALIDOS`: adicionar `'table_dynamic'`.
- Novo `FUNCOES_AGREGACAO_VALIDAS = {'soma', 'contagem', 'media', 'minimo', 'maximo'}`.
- `QueryInput`/`QueryUpdate`: adicionar `subquery_id: Optional[int] = None`.
- `ALLOWED_COLS` (em `atualizar_query`, linha ~284-291): adicionar `'subquery_id'`.
- `criar_query`: incluir `subquery_id` no `INSERT`, mesmo padrão dos demais
  campos opcionais.
- Novos modelos `AgrupamentoInput {coluna, ordem}`, `AgregacaoInput {coluna,
  funcao, label, ordem}`, `SubqueryParametroInput {coluna_origem,
  parametro_destino, ordem}`.
- Três pares de endpoints novos, espelhando exatamente `listar_parametros`/
  `salvar_parametros` (linha 184-212: `DELETE` + `INSERT` em lote, retorna a
  lista salva):
  - `GET/PUT /api/queries/{id}/agrupamentos`
  - `GET/PUT /api/queries/{id}/agregacoes` (validar `funcao` contra
    `FUNCOES_AGREGACAO_VALIDAS`, mesmo estilo do erro 400 de `mapa_camada`)
  - `GET/PUT /api/queries/{id}/subquery-parametros`
- `executar_query` (linha 110-121): hoje não recebe `Request` e chama
  `resolver_query(..., )` sem `parametros`, então ignora qualquer querystring.
  Adicionar `request: Request` e `parametros=dict(request.query_params)`,
  igual ao que `renderizar_painel` já faz (`paineis.py:367`). Sem
  querystring, `dict(request.query_params)` é `{}`, equivalente ao
  comportamento atual — não quebra nenhum chamador existente. O frontend
  `api.js:84-87` (`executarQuery(slug, params)`) **já monta a querystring
  hoje** — só o backend precisa passar a aceitar.

### `backend/routes/paineis.py`

- `renderizar_painel` (`SELECT` em `paineis.py:380-390`): incluir
  `q.subquery_id` na lista de colunas do JOIN.
- Depois do loop que popula `ind_dict["dados"]` (linha 392-409), para
  indicadores com `query_tipo == 'table_dynamic'`, buscar e anexar:
  - `ind_dict["agrupamentos"]` ← `SELECT coluna FROM query_agrupamentos WHERE query_id = ... ORDER BY ordem`
  - `ind_dict["agregacoes"]` ← idem em `query_agregacoes`
  - se `subquery_id` não for nulo: `ind_dict["subquery"]` ←
    `{slug, tipo, parametros}` onde `slug`/`tipo` vêm de
    `SELECT slug, tipo FROM queries WHERE id = subquery_id` e `parametros`
    vem de `SELECT coluna_origem, parametro_destino FROM
    query_subquery_parametros WHERE query_id = ... ORDER BY ordem`; senão
    `ind_dict["subquery"] = None`.
  - Buscar essas 3-4 queries só quando `ind_dict["query_tipo"] ==
    'table_dynamic'` (custo zero pros demais tipos).

## Frontend

### `frontend/src/lib/api.js`

Três pares novos, mesmo molde de `parametrosQuery`/`salvarParametrosQuery`
(linha 70-71):
```js
agrupamentosQuery:            (id)    => request(`/api/queries/${id}/agrupamentos`),
salvarAgrupamentosQuery:      (id, d) => request(`/api/queries/${id}/agrupamentos`, { method: 'PUT', body: JSON.stringify(d) }),
agregacoesQuery:               (id)    => request(`/api/queries/${id}/agregacoes`),
salvarAgregacoesQuery:         (id, d) => request(`/api/queries/${id}/agregacoes`, { method: 'PUT', body: JSON.stringify(d) }),
subqueryParametrosQuery:        (id)    => request(`/api/queries/${id}/subquery-parametros`),
salvarSubqueryParametrosQuery:  (id, d) => request(`/api/queries/${id}/subquery-parametros`, { method: 'PUT', body: JSON.stringify(d) }),
```
`executarQuery` (linha 84-87) não muda — já serve.

### `frontend/src/routes/configuracoes/queries/nova/+page.svelte` (espelhar em `[id]/+page.svelte`)

Novo bloco `{#if form.tipo === 'table_dynamic'}`, populado por
`resultadoTeste?.colunas` (mesmo mecanismo do bloco de impressão):

- **Agrupamento**: lista ordenável de `<select>` (coluna), botões
  subir/descer/remover + "+ nível de agrupamento".
- **Agregações**: lista de linhas `[coluna ▾] [função ▾] [label opcional]` +
  "+ agregação". Função é um `<select>` fixo com as 5 opções.
- **Subconsulta**: `<select bind:value={form.subquery_id}>` carregado de
  `api.listarQueries()` (excluir a própria query quando em edição). Ao
  mudar, busca `api.parametrosQuery(form.subquery_id)` e, para cada
  parâmetro dela, mostra `<select>` "vem de qual coluna desta query?"
  (mesma fonte `resultadoTeste?.colunas`) — grava como
  `{coluna_origem, parametro_destino: <nome do parâmetro>}`.
- Ao salvar (mesmo ponto onde a tela já chama `salvarParametrosQuery` depois
  de criar/atualizar a query base): chamar também
  `salvarAgrupamentosQuery`, `salvarAgregacoesQuery`,
  `salvarSubqueryParametrosQuery`.

### `frontend/src/lib/components/DynamicTable.svelte` (novo)

- Props: `colunas`, `dados`, `agrupamentos` (`string[]`, ordenado),
  `agregacoes` (`[{coluna, funcao, label}]`), `subquery`
  (`{slug, tipo, parametros: [{coluna_origem, parametro_destino}]} | null`),
  `titulo`.
- Função pura `construirArvore(dados, agrupamentos, agregacoes)`: agrupa
  recursivamente pelas colunas de `agrupamentos`, nível a nível; em cada nó
  de grupo calcula os valores de `agregacoes` sobre todas as linhas
  descendentes (soma/contagem/média/mínimo/máximo); no último nível, o nó
  guarda as linhas originais como folhas.
- Renderização recursiva: linha de grupo (destaque, indentada por nível) com
  o valor da coluna de agrupamento + os valores agregados alinhados à
  direita; linhas de detalhe (folha) com as colunas restantes (todas menos
  as usadas em `agrupamentos` — mesmo padrão de ocultar coluna técnica que
  `DataTable.svelte` já usa) + coluna "Ações" (só quando `subquery` não é
  `null`), com um botão que:
  1. monta `params = Object.fromEntries(subquery.parametros.map(m => [m.parametro_destino, row[m.coluna_origem]]))`;
  2. chama `api.executarQuery(subquery.slug, params)`;
  3. abre o `Modal` com estado `carregando → dados → erro`.
- **Sem paginação nem exportação (CSV/Excel/PDF)** nesta primeira versão —
  fica só no `DataTable` tradicional (ver "Fora de escopo").

### `frontend/src/lib/components/Modal.svelte` (novo)

- Props: `aberto` (bool), `onClose` (fn), slot padrão para o conteúdo.
- Overlay fixo (`position: fixed`, fundo semi-transparente) + caixa
  centralizada + botão fechar (✕); fecha em ESC ou clique fora da caixa.
- Sem biblioteca externa (nenhuma dependência nova).

### `frontend/src/routes/painel/[slug]/+page.svelte`

- Novo branch no `{#if ind.query_tipo === ...}` (depois do de `'table'`,
  linha ~260):
  ```svelte
  {:else if ind.query_tipo === 'table_dynamic'}
    <DynamicTable
      dados={ind.dados}
      titulo={ind.titulo || ind.query_slug}
      agrupamentos={ind.agrupamentos}
      agregacoes={ind.agregacoes}
      subquery={ind.subquery}
    />
  ```
- Dentro do `Modal` (dentro de `DynamicTable`, ou renderizado no próprio
  `+page.svelte` — decidir na implementação conforme ficar mais simples),
  reaproveitar o mesmo switch por tipo (`kpi`/`table`/`chart_*`/`map`) que já
  existe nesta página para os indicadores normais, aplicado ao resultado da
  subconsulta.

## Fora de escopo

- Paginação e exportação CSV/Excel/PDF na `DynamicTable` — fica restrito ao
  `DataTable` tradicional por enquanto.
- Reordenar agrupamentos/agregações por drag-and-drop — só botões
  subir/descer.
- Mais de uma subconsulta (mais de um botão de ação) por linha.
- Cache específico de resultado da subconsulta no frontend — cada clique
  chama de novo; o cache de `resolver_query` no backend (`cache_ttl` da
  subconsulta) já se aplica normalmente.
- Validar que as colunas escolhidas (agrupamento/agregação/parâmetro)
  realmente existem no resultado — mesmo nível de confiança que
  `impressao_coluna` já aceita hoje (falha silenciosa, não bloqueia salvar).
- Aplicar as migrações em produção (fica documentado como pendência manual).

## Verificação

- Criar query `table_dynamic` com 2 níveis de agrupamento, 2 agregações e
  uma subconsulta com 2 parâmetros mapeados; salvar e reabrir — tudo
  recarrega certo.
- Painel com essa query: árvore renderiza nos dois níveis, valores agregados
  batem com soma/contagem manual dos dados.
- Clique em "Ações" numa linha de detalhe: dialog abre com "Carregando...",
  depois mostra os dados no tipo certo — testar com subconsulta `table`,
  `kpi` e `map`.
- Subconsulta que falha (SQL quebrado ou parâmetro obrigatório faltando):
  dialog mostra a mensagem de erro, painel não quebra.
- Query `table_dynamic` sem subconsulta configurada: coluna "Ações" não
  aparece.
- Tipos existentes (`table`, `kpi`, `chart_*`, `map`) continuam funcionando
  sem nenhuma regressão.
