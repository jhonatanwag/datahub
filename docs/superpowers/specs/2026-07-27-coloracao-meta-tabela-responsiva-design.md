# Coloração por meta e tabela responsiva (queries tipo `table`) — Design

## Contexto

Duas melhorias independentes, mas ambas em `DataTable.svelte` (componente usado
só por queries tipo `table`, já estendido recentemente com o botão de
impressão opcional — ver `docs/superpowers/specs/2026-07-26-botao-impressao-table-design.md`):

1. **Coloração condicional por meta:** o admin escolhe uma coluna "alvo" (a
   que vai ser colorida) e duas colunas de meta (início/fim, vindas do
   próprio SQL da query) — se o valor da coluna alvo estiver dentro do
   intervalo `[início, fim]`, o texto fica de uma cor; fora, de outra. As
   colunas de meta em si nunca aparecem na tabela (só a coluna alvo, com a
   cor aplicada).
2. **Tabela responsiva:** hoje `DataTable.svelte` só tem `overflow-x: auto`
   no wrapper — no celular isso vira barra de rolagem horizontal. Pedido:
   sem barra de rolagem, reorganizando em cards empilhados.

## Decisões

- **O que colorir:** só a cor do texto (fonte) da célula — confirmado com o
  usuário, sem mexer no fundo da célula.
- **Limites da meta:** inclusivos — `valor >= início AND valor <= fim` conta
  como "dentro da meta".
- **Sem meta ou valor não numérico → sem colorir:** célula usa a cor padrão
  do texto da tabela, comportamento silencioso (mesmo princípio de "falha
  silenciosa sem quebrar a tabela" já estabelecido pro botão de impressão).
  "Não numérico" cobre: `meta_coluna_inicio`/`meta_coluna_fim` nulos na
  linha, ou qualquer um dos três valores (`início`, `fim`, valor da coluna
  alvo) não convertendo pra número via `Number(...)` (resulta em `NaN`).
- **Cores configuráveis por query:** dois color-pickers ("dentro da meta" /
  "fora da meta"), mesmo padrão visual de "Cores do KPI" já existente —
  aplicadas a todas as linhas da tabela, sem variação por linha.
- **Onde ocultar as colunas de meta:** generalizar o mecanismo que já oculta
  a coluna do UUID (botão de impressão) — hoje é um filtro por uma única
  chave (`impressaoColuna`); passa a ser um filtro contra um conjunto de
  chaves ocultas (`impressaoColuna`, `metaColunaInicio`, `metaColunaFim`).
  A coluna alvo (`metaColunaValor`) **continua visível** — só ganha a cor.
- **Responsivo — cards empilhados**, não colunas priorizadas escondidas
  automaticamente (confirmado com o usuário) — cada linha vira um card com
  todas as colunas visíveis, formato "Rótulo: valor" empilhado. Sem barra
  de rolagem horizontal em nenhum tamanho de tela.
- **Breakpoint mobile:** `≤768px`, mesmo valor já usado em todo o resto do
  projeto (`+layout.svelte`, sidebar).
- **Implementação via CSS, não JS de resize:** os dois layouts (tabela e
  cards) ficam ambos no DOM, alternados por `@media (max-width: 768px)` —
  mesma técnica já usada pro sidebar colapsável. Evita duplicar
  fetch/estado, só duplica marcação, e não depende de `window.innerWidth`/
  listener de resize.
- **Botão de impressão no card:** vira um ícone (mesmo 🖨, mesma função
  `imprimir()`) ancorado no canto superior direito do card via
  `position: absolute` dentro de um card com `position: relative` — não um
  botão de largura total, pra manter consistência visual com a versão
  desktop (ícone, não texto).
- **Paginação/CSV/Excel/itens-por-página:** não mudam — continuam como
  estão, fora da tabela/cards, compartilhados pelos dois layouts.

## Modelo de dados

```sql
ALTER TABLE queries ADD COLUMN meta_habilitada BOOLEAN DEFAULT false;
ALTER TABLE queries ADD COLUMN meta_coluna_valor TEXT;
ALTER TABLE queries ADD COLUMN meta_coluna_inicio TEXT;
ALTER TABLE queries ADD COLUMN meta_coluna_fim TEXT;
ALTER TABLE queries ADD COLUMN meta_cor_dentro TEXT DEFAULT '#3fb950';
ALTER TABLE queries ADD COLUMN meta_cor_fora TEXT DEFAULT '#f85149';
```

Só fazem sentido quando `tipo = 'table'`, mas existem em todas as linhas —
mesmo padrão de `kpi_cor_fonte`/`impressao_*`. `#3fb950` (verde) e
`#f85149` (vermelho) são as mesmas cores já usadas em `slot-badge`
(`queries/nova/+page.svelte`) e `STATUS_COLOR` (`DataTable.svelte`) — reuso
de paleta, não uma cor nova no projeto.

**Migração:** sem sistema de migrations — `ALTER TABLE` manual + refletir em
`scripts/init-db.sql`, `scripts/init-meta-prod.sql` e README ("Deltas de
schema pendentes"), mesmo processo das features anteriores.

## Backend

### `backend/routes/queries.py`

- `QueryInput`: adicionar os 6 campos (após `impressao_coluna`):
  ```python
  meta_habilitada: bool = False
  meta_coluna_valor: Optional[str] = None
  meta_coluna_inicio: Optional[str] = None
  meta_coluna_fim: Optional[str] = None
  meta_cor_dentro: Optional[str] = '#3fb950'
  meta_cor_fora: Optional[str] = '#f85149'
  ```
- `QueryUpdate`: os mesmos 6 campos, todos `Optional`/default `None`.
- `ALLOWED_COLS` (em `atualizar_query`): adicionar os 6 nomes.
- `criar_query`: incluir os 6 campos no `INSERT`/`VALUES` (19 → 25
  colunas/placeholders, `$20` a `$25`).
- Sem validação extra de conteúdo (mesmo nível de confiança que os campos
  de impressão/chart — admin configura, sem checar contra os dados reais).

### `backend/routes/paineis.py`

- `renderizar_painel` (mesmo `SELECT` que já traz `impressao_habilitada`
  etc.): incluir `q.meta_habilitada, q.meta_coluna_valor,
  q.meta_coluna_inicio, q.meta_coluna_fim, q.meta_cor_dentro,
  q.meta_cor_fora`.

## Frontend — Cadastro/edição de query

`frontend/src/routes/configuracoes/queries/nova/+page.svelte` e
`.../[id]/+page.svelte`:

- `form`: adicionar `meta_habilitada: false, meta_coluna_valor: '',
  meta_coluna_inicio: '', meta_coluna_fim: '', meta_cor_dentro: '#3fb950',
  meta_cor_fora: '#f85149'` (nova) / carregar de `q.meta_* ?? <mesmos
  defaults>` (edição, mesmo padrão de fallback já usado pros campos de
  impressão).
- Novo bloco `{#if form.tipo === 'table'}`, inserido **logo depois** do
  bloco existente "Botão de Impressão" (mesmo `{#if form.tipo === 'table'}`
  guard — os dois blocos convivem dentro da mesma condição de tipo, um
  após o outro):

  ```svelte
  <div class="section-block">
    <span class="section-title">Coloração por Meta</span>
    <label class="check-inline">
      <input type="checkbox" bind:checked={form.meta_habilitada} />
      Colorir uma coluna conforme uma meta (início/fim)
    </label>
    {#if form.meta_habilitada}
      <label class="lbl">
        Coluna a colorir (continua visível na tabela)
        <select bind:value={form.meta_coluna_valor}>
          <option value="">— selecione —</option>
          {#each resultadoTeste?.colunas ?? (form.meta_coluna_valor ? [form.meta_coluna_valor] : []) as c}
            <option value={c}>{c}</option>
          {/each}
        </select>
      </label>
      <label class="lbl">
        Coluna com o início da meta (fica oculta na tabela)
        <select bind:value={form.meta_coluna_inicio}>
          <option value="">— selecione —</option>
          {#each resultadoTeste?.colunas ?? (form.meta_coluna_inicio ? [form.meta_coluna_inicio] : []) as c}
            <option value={c}>{c}</option>
          {/each}
        </select>
      </label>
      <label class="lbl">
        Coluna com o fim da meta (fica oculta na tabela)
        <select bind:value={form.meta_coluna_fim}>
          <option value="">— selecione —</option>
          {#each resultadoTeste?.colunas ?? (form.meta_coluna_fim ? [form.meta_coluna_fim] : []) as c}
            <option value={c}>{c}</option>
          {/each}
        </select>
      </label>
      <div class="cores-row">
        <label class="lbl">
          Cor dentro da meta
          <div class="color-pick">
            <input type="color" bind:value={form.meta_cor_dentro} />
            <input type="text"  bind:value={form.meta_cor_dentro} placeholder="#3fb950" style="width:90px" />
          </div>
        </label>
        <label class="lbl">
          Cor fora da meta
          <div class="color-pick">
            <input type="color" bind:value={form.meta_cor_fora} />
            <input type="text"  bind:value={form.meta_cor_fora} placeholder="#f85149" style="width:90px" />
          </div>
        </label>
      </div>
      <p class="hint-block">
        Se o valor da coluna escolhida estiver entre início e fim (incluindo os limites), o texto
        fica na "cor dentro da meta"; fora disso, na "cor fora da meta". Linha sem meta definida ou
        com valor não numérico fica com a cor padrão, sem indicar dentro/fora.
      </p>
    {/if}
  </div>
  ```

- Incluir os 6 campos no payload de `criarQuery` (`nova`, já cobre
  automaticamente — `salvar()` envia `form` inteiro) e no payload explícito
  de `atualizarQuery` (`[id]`, que lista campos um a um).

## Frontend — `frontend/src/lib/components/DataTable.svelte`

### Props novas

```js
export let metaHabilitada    = false;
export let metaColunaValor   = null;
export let metaColunaInicio  = null;
export let metaColunaFim     = null;
export let metaCorDentro     = '#3fb950';
export let metaCorFora       = '#f85149';
```

### Ocultar colunas de meta (generalizar o filtro existente)

Trocar o filtro atual de uma chave só por um conjunto:

```js
$: colunasOcultas = new Set([impressaoColuna, metaColunaInicio, metaColunaFim].filter(Boolean));
$: colunasEfetivas = (colunas.length > 0
  ? colunas
  : (dados[0] ? Object.keys(dados[0]).map(k => ({ key: k, label: k })) : [])
).filter(c => !colunasOcultas.has(c.key));
```

(`metaColunaValor` não entra em `colunasOcultas` — continua visível.)

### Cálculo da cor

```js
function corMeta(row) {
  if (!metaHabilitada || !metaColunaValor || !metaColunaInicio || !metaColunaFim) return null;
  const valor  = Number(row[metaColunaValor]);
  const inicio = Number(row[metaColunaInicio]);
  const fim    = Number(row[metaColunaFim]);
  if (Number.isNaN(valor) || Number.isNaN(inicio) || Number.isNaN(fim)) return null;
  return (valor >= inicio && valor <= fim) ? metaCorDentro : metaCorFora;
}
```

Retorna `null` (sem estilo aplicado, cor padrão) nos casos de "sem meta" e
"não numérico" — usado como `style="color: {corMeta(row) ?? 'inherit'}"` (ou
omitindo o `style` quando `null`) na célula/linha correspondente à coluna
`metaColunaValor`, tanto na tabela desktop quanto no card mobile.

### Marcação — tabela desktop (ajuste na célula existente)

No `{#each colunasEfetivas as col}` dentro do `<tbody>`, adicionar a cor
condicional na branch que já existe (sem criar uma branch nova — só aplicar
`style` quando `col.key === metaColunaValor`):

```svelte
<td style={col.key === metaColunaValor && corMeta(row) ? `color:${corMeta(row)}` : ''}>
  {#if col.key === 'status'}
    ...
  {:else if col.key === 'valor'}
    {fmtValor(row[col.key])}
  {:else}
    {row[col.key] ?? '—'}
  {/if}
</td>
```

### Marcação nova — cards mobile

Bloco novo, paralelo ao `<table>` existente, dentro do mesmo `.table-wrap`:

```svelte
<div class="cards-mobile">
  {#each dadosPaginados as row}
    <div class="card-linha">
      {#if mostrarAcoes && row[impressaoColuna]}
        <button class="btn-ghost btn-sm card-acao" on:click={() => imprimir(row)} title="Imprimir">🖨</button>
      {/if}
      {#each colunasEfetivas as col}
        <div class="card-campo">
          <span class="card-rotulo">{col.label ?? col.key}</span>
          <span
            class="card-valor"
            style={col.key === metaColunaValor && corMeta(row) ? `color:${corMeta(row)}` : ''}
          >
            {#if col.key === 'status'}
              <span class="dot" style="background:{STATUS_COLOR[row[col.key]] ?? 'var(--muted)'}"></span>
              {row[col.key]}
            {:else if col.key === 'valor'}
              {fmtValor(row[col.key])}
            {:else}
              {row[col.key] ?? '—'}
            {/if}
          </span>
        </div>
      {/each}
    </div>
  {/each}
</div>
```

### CSS — alternância por media query + estilos do card

```css
.cards-mobile { display: none; }

@media (max-width: 768px) {
  table { display: none; }
  .cards-mobile { display: flex; flex-direction: column; gap: 10px; }
  .card-linha {
    position: relative;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 14px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .card-acao { position: absolute; top: 8px; right: 8px; }
  .card-campo { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }
  .card-rotulo { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }
  .card-valor { text-align: right; }
}
```

`.table-wrap { overflow-x: auto; }` continua existindo para telas ≥768px
(não afeta o mobile, já que a `<table>` está `display:none` lá).

## Frontend — `frontend/src/routes/painel/[slug]/+page.svelte`

Passar as 6 novas props ao `<DataTable>` a partir de `ind.meta_*` (mesmo
padrão dos outros campos já passados):

```svelte
<DataTable
  dados={ind.dados}
  titulo={ind.titulo || ind.query_slug}
  impressaoHabilitada={ind.impressao_habilitada}
  impressaoUrlBase={...}
  impressaoColuna={ind.impressao_coluna}
  metaHabilitada={ind.meta_habilitada}
  metaColunaValor={ind.meta_coluna_valor}
  metaColunaInicio={ind.meta_coluna_inicio}
  metaColunaFim={ind.meta_coluna_fim}
  metaCorDentro={ind.meta_cor_dentro}
  metaCorFora={ind.meta_cor_fora}
/>
```

## Fora de escopo

- Validação de que as colunas escolhidas (`meta_coluna_valor`/`inicio`/`fim`)
  existem de fato nos dados retornados — falha silenciosa, mesmo padrão do
  botão de impressão.
- Mais de uma coluna colorida por meta, por query.
- Cor de fundo da célula (só cor de fonte, confirmado).
- Esconder colunas automaticamente por prioridade no mobile — abordagem
  escolhida foi cards, não colunas priorizadas.
- Qualquer breakpoint além de `768px` (ex: tablet intermediário) — mobile
  vira card, resto continua tabela normal com scroll horizontal se
  necessário (comportamento atual, inalterado acima de 768px).
- Tornar `STATUS_COLOR`/formatação de `valor` configuráveis — continuam
  como estão, a coloração por meta é um mecanismo adicional independente
  que só sobrepõe a cor do texto.

## Verificação

- Criar query tipo `table` com meta habilitada, colunas de início/fim/alvo
  selecionadas via dropdown pós-"Testar", cores customizadas — salvar e
  reabrir mostra os valores salvos corretamente.
- Painel com essa query: linha com valor dentro do intervalo → texto na cor
  "dentro"; linha fora do intervalo → cor "fora"; linha com meta nula ou
  valor não numérico → cor padrão, sem quebrar a tabela.
- Colunas de início/fim nunca aparecem como dado visível (nem na tabela nem
  no CSV/Excel); coluna alvo continua visível e presente no export, só sem
  a cor (export é texto puro, sem estilo).
- Redimensionar a janela (ou abrir em viewport ≤768px): tabela vira cards
  empilhados, sem barra de rolagem horizontal; acima de 768px, comportamento
  idêntico ao atual (tabela normal).
- Card mobile: cada linha mostra todas as colunas como "Rótulo: valor",
  coluna colorida por meta aparece com a cor certa, botão de impressão (se
  habilitado) aparece como ícone no canto do card e funciona igual à
  versão desktop.
- Query `table` sem coloração por meta habilitada: comportamento idêntico
  ao atual (sem cor condicional), em ambos os layouts (tabela e card).
- KPI, gráficos e mapa — não afetados.
