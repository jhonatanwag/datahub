# Botão de impressão em queries tipo `table` — Design

## Contexto

Cada empresa cliente tem um sistema legado próprio (ex: `VitoriaAgronegocios`)
que gera relatórios de impressão em uma URL fixa por empresa, seguida de um
caminho específico do relatório e um UUID que identifica o registro:

```
https://www.psosistemas.com.br:8443/VitoriaAgronegocios/relatorioPerda/Impressao.xhtml?uuid=1642d8a9-a204-4745-b446-64232422a886
```

Pedido: numa query do DataHub tipo `table`, permitir habilitar (opcionalmente,
não obrigatório) um botão de impressão por linha, que monta esse link
concatenando três partes e abre em nova aba:

1. **Base por empresa** — `https://www.psosistemas.com.br:8443/VitoriaAgronegocios/`
2. **Caminho por query** — `relatorioPerda/Impressao.xhtml?uuid=`
3. **UUID da linha** — vem de uma coluna do próprio resultado da query,
   escolhida pelo admin ao configurar a query

## Decisões

- **Concatenação simples, sem encoding especial:** `base + caminho + valor_da_coluna`,
  montada no frontend em tempo de render (mesmo padrão de "resolver em tempo de
  view" já usado no projeto — nada é pré-calculado/persistido).
- **Coluna do UUID fica oculta** na tabela renderizada — não aparece como coluna
  de dado normal, só é usada internamente para montar o link.
- **Abre em nova aba** (`window.open(..., '_blank')`) — preserva o contexto do
  painel/filtros aplicados.
- **Sem URL de impressão na empresa → botão simplesmente não aparece** (falha
  silenciosa, sem erro visível, mesmo que a query tenha o recurso habilitado).
- **Linha sem valor na coluna do UUID → sem botão nessa linha específica**
  (célula em branco), não quebra a tabela nem afeta as outras linhas.
- **Seleção da coluna do UUID via dropdown**, populado pelos resultados do
  botão "Testar" que já existe na tela de query (mesmo campo `colunas` que
  `/api/queries/testar` já retorna hoje). Sem testar ainda (ex: reabrindo uma
  query já salva pra editar), o dropdown mostra só o valor atualmente salvo
  como opção única, até o admin clicar em Testar de novo.
- **Sem validação de que a coluna escolhida realmente existe** nos dados
  retornados — mesmo nível de confiança que os demais campos de exibição já
  existentes (`chart_valor_label`, `kpi_cor_fonte` etc.): se o admin errar o
  nome, o botão simplesmente não aparece pra aquela linha (valor `undefined`
  é tratado igual a vazio).

## Modelo de dados

```sql
ALTER TABLE empresas ADD COLUMN url_impressao_base TEXT;

ALTER TABLE queries ADD COLUMN impressao_habilitada BOOLEAN DEFAULT false;
ALTER TABLE queries ADD COLUMN impressao_caminho TEXT;
ALTER TABLE queries ADD COLUMN impressao_coluna TEXT;
```

`impressao_habilitada`/`impressao_caminho`/`impressao_coluna` só são
relevantes quando `queries.tipo = 'table'`, mas as colunas existem em todas as
linhas — mesmo padrão de `kpi_cor_fonte`/`mapa_camada`, que só se aplicam a
determinados `tipo`.

**Migração:** projeto não tem sistema de migrations — refletir em:
- `scripts/init-db.sql` (seed local de dev)
- `scripts/init-meta-prod.sql` (schema de produção)
- README, seção "Deltas de schema pendentes" (novo item, aplicar manualmente
  em produção via `psql -U postgres -d datahub_meta` — ver
  `docs/superpowers/specs/` anteriores para o padrão desse checklist)

Aplicar o `ALTER TABLE` no Postgres real de produção (VPS) é um passo manual,
fora do escopo desta implementação — só fica documentado como pendência.

## Backend

### `backend/routes/empresas.py`

- `EmpresaInput`: adicionar `url_impressao_base: str | None = None`.
- `EmpresaUpdate`: adicionar `url_impressao_base: str | None = None`.
- `listar_empresas` (`GET /`): não precisa retornar o campo (view de lista,
  não usa).
- `buscar_empresa` (`GET /{id}`): incluir `url_impressao_base` no `SELECT`.
- `criar_empresa` (`POST /`): incluir `url_impressao_base` no `INSERT`.
- `atualizar_empresa` (`PATCH /{id}`): incluir `url_impressao_base` no
  `UPDATE` (mesmo estilo posicional já usado, não é `ALLOWED_COLS` parcial
  como em `queries.py` — `empresas.py` sempre grava a linha inteira).

### `backend/routes/queries.py`

- `QueryInput`: adicionar `impressao_habilitada: bool = False`,
  `impressao_caminho: Optional[str] = None`, `impressao_coluna: Optional[str] = None`.
- `QueryUpdate`: os mesmos três campos, todos `Optional`/default `None`.
- `ALLOWED_COLS` (em `atualizar_query`): adicionar os três nomes.
- `criar_query`: incluir os três campos no `INSERT`/`VALUES`.
- Sem validação extra de conteúdo (livre, como `chart_valor_label`).

### `backend/middleware/auth.py`

- `get_current_user`: adicionar `e.url_impressao_base` nas duas queries de
  usuário (interno, linha ~66-74, e externo, linha ~39-42) — passa a vir
  automaticamente em qualquer request autenticado, incluindo o payload
  devolvido por `GET /api/auth/me`.

### `backend/routes/paineis.py`

- `renderizar_painel` (linha ~344-348): incluir
  `q.impressao_habilitada, q.impressao_caminho, q.impressao_coluna` no mesmo
  `SELECT` que já traz `q.kpi_cor_fonte, q.kpi_cor_fundo, q.mapa_camada,
  q.chart_*` — chega no payload de cada indicador do painel.

## Frontend

### `frontend/src/lib/stores/auth.js` e os 3 lugares que montam `empresaAtiva`

`empresaAtiva` é construído manualmente em três arquivos, sempre a partir do
retorno de `api.me()` logo após popular `usuario`:
- `frontend/src/routes/+layout.svelte` (linha ~86)
- `frontend/src/routes/selecionar-empresa/+page.svelte` (linha ~38)
- `frontend/src/routes/sso/+page.svelte` (linha ~20)

Adicionar `url_impressao_base: me.url_impressao_base ?? null` nos três
objetos. (Em `selecionar-empresa/+page.svelte`, o objeto é montado a partir de
`empresa` — da lista retornada pelo login — não de `me`; como o campo só
existe hoje no retorno de `/me`, usar `me.url_impressao_base` ali também, já
que a chamada a `api.me()` já acontece logo em seguida nesse mesmo fluxo.)

### `/configuracoes/empresas/nova` e `/configuracoes/empresas/[id]`

Novo campo de texto opcional, mesmo estilo visual dos campos de SSO já
existentes (`sso_query_acesso`):

```svelte
<label class="lbl">
  URL base de impressão (opcional)
  <input
    type="text"
    bind:value={empresa.url_impressao_base}
    placeholder="https://www.psosistemas.com.br:8443/NomeDaEmpresa/"
  />
</label>
```

Incluir `url_impressao_base` no payload de `criarEmpresa`/`atualizarEmpresa`.

### `/configuracoes/queries/nova` e `/configuracoes/queries/[id]`

- `form`: adicionar `impressao_habilitada: false, impressao_caminho: '',
  impressao_coluna: ''` (nova) / carregar de `q.impressao_*` (edição, com
  fallback pros mesmos defaults).
- Novo bloco condicional `{#if form.tipo === 'table'}`, mesmo estilo visual
  dos blocos `{#if form.tipo === 'map'}` / `chart`:

```svelte
{#if form.tipo === 'table'}
  <div class="section-block">
    <span class="section-title">Botão de Impressão</span>
    <label class="check-inline">
      <input type="checkbox" bind:checked={form.impressao_habilitada} />
      Habilitar botão de impressão nesta tabela
    </label>
    {#if form.impressao_habilitada}
      <label class="lbl">
        Caminho do relatório (concatenado após a URL base da empresa)
        <input
          type="text"
          bind:value={form.impressao_caminho}
          placeholder="relatorioPerda/Impressao.xhtml?uuid="
        />
      </label>
      <label class="lbl">
        Coluna com o UUID/link (teste a query pra ver as colunas disponíveis)
        <select bind:value={form.impressao_coluna}>
          <option value="">— selecione —</option>
          {#each resultadoTeste?.colunas ?? (form.impressao_coluna ? [form.impressao_coluna] : []) as c}
            <option value={c}>{c}</option>
          {/each}
        </select>
      </label>
      <p class="hint-block">
        A coluna escolhida fica oculta na tabela do painel — usada só pra
        montar o link. O link final é
        <code>URL base da empresa + caminho acima + valor da coluna</code>.
        Sem URL base cadastrada na empresa (Configurações → Empresas), o
        botão não aparece pra ela, mesmo com o recurso habilitado aqui.
      </p>
    {/if}
  </div>
{/if}
```

- Incluir os três campos no payload de `criarQuery`/`atualizarQuery`.

### `frontend/src/lib/components/DataTable.svelte`

- Novas props: `export let impressaoHabilitada = false; export let
  impressaoUrlBase = null; export let impressaoColuna = null;`
- `colunasEfetivas`: filtrar `impressaoColuna` para fora do resultado final,
  independente de vir do array `colunas` explícito ou do derivado
  automaticamente das chaves da primeira linha — em ambos os casos a coluna
  do UUID nunca deve aparecer como dado visível. Como `baixarCSV`/`baixarXLSX`
  já usam `colunasEfetivas` para montar cabeçalho/linhas, a coluna oculta
  também fica de fora automaticamente da exportação, sem mudança adicional
  nessas duas funções.
- Se `impressaoHabilitada && impressaoUrlBase && impressaoColuna`: renderizar
  uma `<th>`/`<td>` extra ("Ações") ao final de cada linha, com um botão
  ícone (🖨) que chama:
  ```js
  function imprimir(row) {
    const valor = row[impressaoColuna];
    if (!valor) return; // sem valor -> sem link, botão nem deveria estar aqui
    window.open(`${impressaoUrlBase}${valor}`, '_blank');
  }
  ```
  Linha sem valor na coluna (`null`/`undefined`/`''`): célula vazia, sem
  botão — não usar `disabled`, simplesmente não renderiza o botão nessa
  linha.

### `frontend/src/routes/painel/[slug]/+page.svelte`

Passar as novas props ao `<DataTable>` (linha ~242), calculando a URL base só
quando ambos os lados existem:

```svelte
<DataTable
  dados={ind.dados}
  titulo={ind.titulo || ind.query_slug}
  impressaoHabilitada={ind.impressao_habilitada}
  impressaoUrlBase={
    ind.impressao_habilitada && $empresaAtiva?.url_impressao_base && ind.impressao_caminho
      ? `${$empresaAtiva.url_impressao_base}${ind.impressao_caminho}`
      : null
  }
  impressaoColuna={ind.impressao_coluna}
/>
```

Com `impressaoUrlBase` nulo, `DataTable` não renderiza a coluna de ação —
cobre tanto "empresa sem URL cadastrada" quanto "query sem caminho definido".

## Fora de escopo

- Validação de que `impressao_coluna` existe de fato nos dados retornados
  pela query (falha silenciosa, não bloqueia salvar).
- Mais de uma coluna/link de impressão por query.
- Qualquer processamento/encoding especial do valor da coluna antes de
  concatenar (assume UUID simples, sem caracteres que precisem de escape).
- Aplicar o `ALTER TABLE` em produção (VPS) — fica documentado como
  pendência manual de deploy.
- Alterar `dashboard_layout` (rota legada `/api/queries/layout/dashboard`) —
  não usado pelo fluxo atual de painéis, fora do escopo.

## Verificação

- Cadastrar/editar empresa com `url_impressao_base` — salva e recarrega
  corretamente; campo vazio continua funcionando (empresas antigas sem o
  campo preenchido).
- Criar query tipo `table`, testar, selecionar coluna do UUID no dropdown,
  habilitar impressão, salvar — reabrir a query mostra os valores salvos.
- Painel com essa query, empresa com `url_impressao_base` cadastrada: cada
  linha da tabela mostra o botão 🖨, clique abre o link correto em nova aba;
  coluna do UUID não aparece como dado visível.
- Mesma query, mas empresa **sem** `url_impressao_base`: tabela renderiza
  normalmente, sem coluna de ação nenhuma.
- Linha com valor nulo na coluna do UUID: tabela renderiza, célula de ação
  vazia só nessa linha, resto funciona normal.
- Exportar CSV/Excel da mesma tabela: não inclui a coluna oculta do UUID nem
  uma coluna de "Ações" (export usa `colunasEfetivas`, que já exclui ambas).
- Query tipo `table` sem `impressao_habilitada`: comportamento idêntico ao
  atual (sem coluna de ação).
- KPI, charts, mapa e demais tipos de query — não afetados.
