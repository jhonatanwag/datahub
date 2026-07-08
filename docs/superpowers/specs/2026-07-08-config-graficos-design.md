# Configurações de gráfico (fonte, truncar label, mostrar valor) + multi-série — Design

## Contexto

Os tipos `chart_bar`, `chart_bar_horizontal`, `chart_line` e `chart_doughnut` (renderizados por `frontend/src/lib/components/ChartPanel.svelte` via ECharts) não têm nenhuma opção configurável hoje — tamanho de fonte fixo (padrão do ECharts), rótulos do eixo nunca truncados, valores nunca mostrados no próprio gráfico, e suporte a **apenas uma** coluna de valor (`valor`). Pedido: (1) configurar tamanho de fonte do label, (2) truncar o texto do label com limite de caracteres configurável, (3) opção de mostrar o valor no gráfico, e (4) suportar múltiplas colunas de valor por label (ex: `fazenda` como label, `media_perdas` e `media_pendencia` como duas séries), renderizando barras/linhas agrupadas.

## Decisões

- **Escopo:** as 4 opções de configuração valem para os 4 tipos de gráfico (`chart_bar`, `chart_bar_horizontal`, `chart_line`, `chart_doughnut`).
- **Multi-série automática:** o contrato de colunas continua exigindo `label` + `valor` (compatível com todas as queries existentes). Qualquer coluna numérica **adicional** retornada pela SQL (além de `label`/`valor`) vira uma série extra automaticamente — nome da coluna SQL = nome da série na legenda. Não precisa nomear como `valor1`/`valor2`; pode ser qualquer alias (`media_perdas`, `media_pendencia`, etc.).
- **Doughnut não usa multi-série:** pizza/rosca representa partes de um todo — não há como mostrar 2 valores por fatia de forma coerente. Colunas extras são ignoradas nesse tipo (só `valor` é usado). As 4 opções de configuração continuam valendo (fonte/truncar afetam texto da legenda e das fatias; mostrar valor alterna entre só nome ou nome+valor na fatia).
- **Causa raiz do "não mostra todos os nomes":** o ECharts pula rótulos do eixo por padrão quando não cabem (`axisLabel.interval: 'auto'`). A correção real é `interval: 0` (força mostrar todos) combinado com o truncamento — truncar sozinho não resolve se o `interval` continuar automático.

## Modelo de dados

4 novas colunas em `queries` (mesmo padrão de `kpi_cor_fonte`/`mapa_camada`):

```sql
ALTER TABLE queries ADD COLUMN chart_fonte_tamanho INTEGER DEFAULT 12;
ALTER TABLE queries ADD COLUMN chart_truncar_label BOOLEAN DEFAULT false;
ALTER TABLE queries ADD COLUMN chart_truncar_tamanho INTEGER DEFAULT 15;
ALTER TABLE queries ADD COLUMN chart_mostrar_valor BOOLEAN DEFAULT false;
```

Aplicar via `ALTER TABLE` manual no Postgres de dev + refletir em `scripts/init-db.sql` e `scripts/init-meta-prod.sql`, seguindo o processo já estabelecido (sem sistema de migrations neste projeto — ver nota de deploy pendente no `README.md`).

## Backend

### `backend/routes/queries.py`

- `QueryInput`: `chart_fonte_tamanho: Optional[int] = 12`, `chart_truncar_label: Optional[bool] = False`, `chart_truncar_tamanho: Optional[int] = 15`, `chart_mostrar_valor: Optional[bool] = False`.
- `QueryUpdate`: os mesmos 4 campos, todos `Optional[...] = None`.
- `criar_query`: incluir os 4 campos no `INSERT`. Sem validação de range nos números (fonte/truncar_tamanho aceitam qualquer inteiro positivo razoável — sem regra de negócio que justifique rejeitar um valor específico, diferente de `tipo`/`mapa_camada` que são enums fechados).
- `atualizar_query`: incluir os 4 campos em `ALLOWED_COLS`.

### `backend/routes/paineis.py`

- `renderizar_painel`: incluir as 4 colunas no `SELECT` que já traz `kpi_cor_fonte, kpi_cor_fundo, mapa_camada`.

## Frontend — Cadastro/edição de query

`nova/+page.svelte` e `[id]/+page.svelte`: novo bloco condicional, mesmo padrão visual dos blocos de KPI/mapa, exibido quando `['chart_bar','chart_bar_horizontal','chart_line','chart_doughnut'].includes(form.tipo)`:

- Input numérico "Tamanho da fonte" (px).
- Checkbox "Truncar rótulos" + input numérico "Caracteres" (só aparece quando o checkbox está marcado).
- Checkbox "Mostrar valor no gráfico".

`[id]/+page.svelte` precisa incluir os 4 campos explicitamente no payload do `salvar()` (mesmo motivo do `mapa_camada`: essa tela monta um objeto explícito, não faz spread de `form`).

## Frontend — `ChartPanel.svelte`

- Novas props: `fonteTamanho = 12`, `truncarLabel = false`, `truncarTamanho = 15`, `mostrarValor = false`.
- **Detecção de séries:** a partir de `dados[0]` (primeira linha), colunas = todas as chaves exceto `label`, filtradas pra manter só as que têm valor numérico em pelo menos uma linha. Para `chart_doughnut`, usar só a primeira (`valor` ou a primeira coluna numérica encontrada) — ignorar as demais.
- **Truncamento:** função `truncar(texto)` — se `truncarLabel` e `texto.length > truncarTamanho`, retorna `texto.slice(0, truncarTamanho) + '…'`; usada no `axisLabel.formatter` (bar/line) e no `formatter` de legenda/label (doughnut).
- **Fonte:** `fontSize: fonteTamanho` no `axisLabel` (bar/line) e no `textStyle`/`label` (doughnut/legenda).
- **`interval: 0`** no `axisLabel` do eixo de categoria (bar/line), sempre — não é opcional, é a correção do bug relatado.
- **Mostrar valor:** `series[].label = { show: mostrarValor, position: isHorizontal ? 'right' : 'top', fontSize: fonteTamanho, color: corTexto }` pra bar/line; pra doughnut, sempre `label.show = true` (comportamento atual do ECharts), mas o `formatter` alterna entre `'{b}'` (nome) e `'{b}: {c}'` (nome + valor) conforme `mostrarValor`.
- **Multi-série (bar/line):** quando há 2+ colunas de série, `series` vira um array com um objeto por coluna (`type`, `name: coluna`, `data: dados.map(d => Number(d[coluna]))`), e `legend` é adicionado ao `option` (some quando há só 1 série, igual hoje).

## Frontend — `painel/[slug]/+page.svelte`

`<ChartPanel tipo={ind.query_tipo} dados={ind.dados} fonteTamanho={ind.chart_fonte_tamanho} truncarLabel={ind.chart_truncar_label} truncarTamanho={ind.chart_truncar_tamanho} mostrarValor={ind.chart_mostrar_valor} />`

## Fora de escopo

- Multi-série em `chart_doughnut` (arquitetonicamente incoerente pra pizza/rosca).
- Ordenar/reordenar séries manualmente (a ordem das colunas na SQL define a ordem das séries).
- Cores customizáveis por série (continua usando a paleta fixa `COLORS` já existente).
- Rotação do rótulo do eixo (não foi pedido; `interval: 0` sozinho já resolve o "não mostra todos os nomes" pro caso comum).

## Verificação

- Query `chart_bar` com só `label`+`valor` — continua funcionando exatamente como hoje (1 série, sem legenda).
- Query `chart_bar` com `label`, `valor`, mais uma coluna numérica extra (ex: `SELECT fazenda AS label, media_perdas AS valor, media_pendencia FROM ...`) — mostra 2 barras por fazenda, com legenda "valor"/"media_pendencia".
- Configurar fonte pequena + truncar em 10 caracteres numa query com muitos labels longos — todos os rótulos aparecem (nenhum é pulado), truncados com "…".
- Ligar "Mostrar valor" — números aparecem em cima/ao lado de cada barra (ou dentro/ao lado de cada fatia no doughnut).
- `chart_doughnut` com colunas extras — ignora as extras, mostra só 1 anel com a coluna `valor`.
- `chart_line` com as mesmas 4 opções — comporta-se de forma equivalente ao bar (múltiplas linhas, truncamento, fonte, mostrar valor no ponto).
