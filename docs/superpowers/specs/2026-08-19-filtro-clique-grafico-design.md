# Filtro por clique em gráficos (barra, rosca, linha) — Design

## Contexto

Hoje o painel tem um sistema de "Variáveis" (`variaveis` + `painel_variaveis`)
que gera os filtros do topo (`FiltroVariavel.svelte`) e que as outras queries
do painel recebem via parâmetro SQL (mesmo mecanismo de sempre —
`filtrosAtivos` no `painel/[slug]/+page.svelte`).

Pedido: ao clicar numa barra/fatia/ponto de um gráfico (ex: gráfico de barras
"por fazenda", mostrando 5 fazendas), aplicar automaticamente o filtro
correspondente àquele item clicado — reaproveitando esse mesmo sistema de
variáveis, sem inventar um mecanismo de filtro paralelo.

## Decisões

- **O clique aciona uma variável já cadastrada no painel** (aba "Filtros" da
  tela de editar painel) — não existe filtro por clique "solto"; se a
  variável não estiver configurada ali, o clique não tem efeito. Isso
  significa zero mudança em como as outras queries do painel recebem o
  filtro — elas já recebem por parâmetro SQL do jeito que recebem hoje.
- **Resolução do valor por coluna explícita no SQL**, não por casamento de
  texto. O gráfico mostra um rótulo (`label`, texto), mas a variável de
  filtro guarda um id interno (`valor`) que pode ser diferente do texto
  exibido (ex: `var_fazenda`: `valor` = `propriedade_id`, `label` =
  `descricao`). Pra não depender do texto do gráfico bater exatamente com o
  texto da variável, o SQL da query do gráfico passa a poder devolver uma
  coluna extra com o id bruto (ex: `fazenda_id`), e o admin aponta qual é
  essa coluna. Mesmo espírito de `impressao_coluna`/`meta_coluna_valor`
  (aponta pra uma coluna do resultado) e de
  `query_subquery_parametros.coluna_origem` (drill-down do `table_dynamic`,
  ver `docs/superpowers/specs/2026-08-18-table-dynamic-design.md`).
- **Configuração em duas camadas**, porque o alvo (variável) é escopado ao
  painel mas a coluna de origem é escopada à query:
  - `queries.chart_filtro_coluna` — qual coluna do resultado tem o id bruto
    (configurado uma vez, na tela de editar/nova query).
  - `painel_indicadores.filtro_clique_variavel_id` — qual variável (já
    adicionada nesse painel) esse indicador aciona ao clicar (configurado por
    indicador, na aba "Indicadores" da tela de editar painel — o mesmo lugar
    onde já existe override de título/col_span/row_span). Um mesmo gráfico
    reusado em painéis diferentes pode acionar variáveis diferentes, ou
    nenhuma.
  - A feature só fica disponível pro admin quando as duas condições
    existirem: a query tem `chart_filtro_coluna` preenchida **e** o
    indicador aponta pra uma variável do painel.
- **Comportamento de clique segue o `tipo` da variável-alvo**, sem
  configuração extra:
  - `select` (valor único): clique define o filtro; clicar de novo no mesmo
    item limpa; clicar em outro item troca.
  - `multiselect`: clique alterna (toggle) — adiciona se não estava
    selecionado, remove se já estava.
- **Aplica imediatamente** (refaz a busca do painel ao clicar), sem precisar
  do botão "Aplicar". O botão "Limpar filtros" já existente limpa de graça
  (mesmo `filtrosAtivos`, `valoresIniciais()` já reseta todas as variáveis).
- **Destaque visual**: itens selecionados com opacidade cheia; os demais
  ficam com opacidade reduzida — só quando há alguma seleção ativa naquele
  gráfico. Em `chart_line`, o destaque fica nos símbolos dos pontos (a cor da
  linha em si não muda).
- **Sem correspondência = filtro vazio, não erro.** Como o valor vem direto
  de uma coluna do SQL (não mais por texto), não existe mais o caso "clicou
  mas não achou a opção" — o valor bruto vai direto pro filtro. Se não bater
  com nada nas outras queries, elas voltam vazias, mesmo comportamento já
  existente hoje pra qualquer filtro sem resultado.
- **A coluna de origem não pode virar série numérica.** `ChartPanel.svelte`
  hoje detecta automaticamente colunas numéricas (fora `label`) como séries
  extras em gráficos multi-série (`colunasSerie`). A coluna de filtro (ex:
  `fazenda_id`, numérica) precisa ser excluída dessa detecção, do mesmo jeito
  que `label` já é excluída.
- **Aplica a `chart_bar`, `chart_bar_horizontal`, `chart_doughnut`,
  `chart_line`** — os quatro tipos pedidos.

## Modelo de dados

```sql
ALTER TABLE queries ADD COLUMN chart_filtro_coluna TEXT;

ALTER TABLE painel_indicadores
    ADD COLUMN filtro_clique_variavel_id INTEGER REFERENCES variaveis(id) ON DELETE SET NULL;
```

**Migração:** projeto não tem sistema de migrations — refletir em
`scripts/init-db.sql` (seed local) e `scripts/init-meta-prod.sql` (schema
prod), e documentar como pendência manual em produção no README, seção
"Deltas de schema pendentes" (mesmo processo dos specs anteriores).

## Backend

### `backend/routes/queries.py`

- `QueryInput`/`QueryUpdate`: adicionar `chart_filtro_coluna: Optional[str] = None`.
- `ALLOWED_COLS` (em `atualizar_query`): adicionar `'chart_filtro_coluna'`.
- `criar_query`: incluir `chart_filtro_coluna` no `INSERT`, mesmo padrão dos
  demais campos opcionais de texto livre (sem validação — mesmo nível de
  confiança que `impressao_coluna`/`meta_coluna_valor` já têm hoje, não
  confere se a coluna existe de fato no resultado).

### `backend/routes/paineis.py`

- `IndicadorInput`: adicionar `filtro_clique_variavel_id: Optional[int] = None`.
- `adicionar_indicador` e `salvar_indicadores`: incluir a coluna no
  `INSERT`/`RETURNING`, mesmo padrão de `col_span`/`row_span`.
- `renderizar_painel` (`SELECT` em `paineis.py:380-390`): incluir
  `q.chart_filtro_coluna` na lista de colunas do `JOIN`, e
  `pi.filtro_clique_variavel_id` já vem de graça (`pi.*`).
- Como o front precisa do **slug** e do **tipo** da variável-alvo (pra saber
  a chave de `filtrosAtivos` e o comportamento select/multiselect), não só o
  id: no mesmo `SELECT` de `renderizar_painel`, fazer um segundo `LEFT JOIN`
  com `variaveis` (alias `fv`) em
  `fv.id = pi.filtro_clique_variavel_id`, trazendo
  `fv.slug AS filtro_clique_variavel_slug, fv.tipo AS filtro_clique_variavel_tipo`.
  Evita uma query extra por indicador (mesmo espírito do JOIN único que já
  traz todas as outras colunas de config).
- **Ajustar o `pop` de `query_id`** (linha 446-448, já existe hoje —
  `if ind_dict.get("query_tipo") != "table_dynamic": pop("query_id")`): não
  precisa mudar por essa feature (o filtro por clique não depende de
  `query_id` no indicador, só de `filtro_clique_variavel_id`, que sempre
  fica no `ind_dict` normalmente).

### `backend/routes/paineis.py` — `listar_indicadores`

- Já devolve `pi.*` — `filtro_clique_variavel_id` já vem de graça, sem
  mudança na query. Usado pela tela de config do painel (não pela renderização).

## Frontend

### `frontend/src/lib/components/ChartPanel.svelte`

- Novas props: `filtroColuna` (nome da coluna com o id bruto, ou `null` se a
  feature não estiver configurada) e `valoresSelecionados` (array de valores
  brutos atualmente ativos pra essa variável — vazio se nenhum).
- `colunasSerie`: excluir `filtroColuna` da lista de chaves candidatas a
  série numérica (mesma exclusão que já existe pra `label`).
- `buildOption`: quando `filtroColuna` está definido, cada item de dado
  (`data[i]`) ganha `itemStyle.opacity` calculado: `1` se
  `String(dados[i][filtroColuna])` está em `valoresSelecionados` **ou**
  `valoresSelecionados` está vazio; `0.35` caso contrário. Vale pra barra,
  rosca e linha (linha: aplicado no `itemStyle` dos símbolos dos pontos).
- `onMount`: registrar `chart.on('click', params => { ... })`. Se
  `filtroColuna` não está definido, handler não faz nada (ou nem registra).
  No clique: pega `dados[params.dataIndex][filtroColuna]`, despacha
  `dispatch('filtroClique', { valor })` pro componente pai. (`dataIndex`
  mapeia corretamente pra linha de `dados` em qualquer série, já que todas
  as séries são construídas a partir do mesmo array `dados`, na mesma ordem
  — confirmado em `colunasSerie`/`series.map` atuais.)

### `frontend/src/routes/painel/[slug]/+page.svelte`

- Passar as duas novas props ao `ChartPanel` (bloco `chart_*` em
  ~linha 255-264):
  ```svelte
  <ChartPanel
    ...
    filtroColuna={ind.chart_filtro_coluna}
    valoresSelecionados={valoresClicados(ind)}
    on:filtroClique={(e) => onFiltroClique(ind, e.detail.valor)}
  />
  ```
- `valoresClicados(ind)`: lê `filtrosAtivos[ind.filtro_clique_variavel_slug]`;
  se `ind.filtro_clique_variavel_tipo === 'multiselect'`, faz `.split(',')`;
  se vazio/undefined, retorna `[]`.
- `onFiltroClique(ind, valor)`: se `ind.filtro_clique_variavel_slug` não
  existe, no-op. Senão:
  - `select`: se `filtrosAtivos[slug] === String(valor)`, limpa (`''`);
    senão substitui.
  - `multiselect`: pega a lista atual (`split(',')`, filtrando vazio),
    remove `valor` se já estava, adiciona senão; junta de volta com `,`
    (mesmo formato que `FiltroVariavel.svelte` já usa/espera).
  - Atualiza `filtrosAtivos` (mesmo padrão de `onFiltroMudou`) e chama
    `carregarDados()` na hora (sem esperar o botão "Aplicar").

### `frontend/src/routes/configuracoes/queries/nova/+page.svelte` (espelhar em `[id]/+page.svelte`)

- `form`: adicionar `chart_filtro_coluna: ''`.
- Dentro do bloco já existente `{#if [...].includes(form.tipo)}` de
  "Configurações do Gráfico" (linha ~482-512), novo campo:
  ```svelte
  <label class="lbl">
    Coluna com o id bruto pro filtro por clique (opcional)
    <select bind:value={form.chart_filtro_coluna}>
      <option value="">— nenhuma —</option>
      {#each resultadoTeste?.colunas ?? (form.chart_filtro_coluna ? [form.chart_filtro_coluna] : []) as c}
        <option value={c}>{c}</option>
      {/each}
    </select>
  </label>
  ```
  Mesmo padrão visual/de dados de `impressao_coluna` (linha ~325-329).

### `frontend/src/routes/configuracoes/paineis/[id]/+page.svelte`

- Cada item de `indicadores` ganha `filtro_clique_variavel_id: null` no
  default (linha ~93-97, ao adicionar indicador) e no `map` de carregamento
  (linha ~60-66).
- Na linha de config de cada indicador (perto de `col_span`/`row_span`,
  ~linha 304-317): se a query desse indicador (buscar em `queries`, já
  carregado nessa tela pro `<select>` de query) tiver `chart_filtro_coluna`
  preenchida, mostrar:
  ```svelte
  <select bind:value={ind.filtro_clique_variavel_id}>
    <option value={null}>— sem filtro por clique —</option>
    {#each variaveis as v}
      <option value={v.variavel_id}>{v.nome}</option>
    {/each}
  </select>
  ```
  `variaveis` já é carregado nessa tela (usado na aba "Filtros",
  linha ~26/38/82) — reusa a mesma lista, sem chamada nova.
- Ao salvar (`api.salvarIndicadores`, linha ~168): nada muda na chamada,
  `filtro_clique_variavel_id` já vai junto no corpo de cada indicador.

### `frontend/src/lib/api.js`

- Nenhuma rota nova — os campos entram nos payloads já existentes
  (`criarQuery`/`atualizarQuery`, `salvarIndicadores`).

## Fora de escopo

- Um clique acionar mais de uma variável ao mesmo tempo (um alvo só por
  indicador).
- Validar que `chart_filtro_coluna` realmente existe no resultado da query —
  mesmo nível de confiança que `impressao_coluna` já aceita hoje.
- Repassar o filtro clicado pra URL (deep link / compartilhar link com
  filtro aplicado) — fica só em estado local do componente, como o resto dos
  filtros hoje.
- Indicador de "isso é clicável" na UI além do cursor (`cursor: pointer`) e
  do próprio destaque de opacidade ao clicar — sem tooltip/hint adicional.
