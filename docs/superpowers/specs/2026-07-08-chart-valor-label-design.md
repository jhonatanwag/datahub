# Nome de exibição da série "valor" no gráfico — Design

## Contexto

A validação de contrato do editor de query exige que a coluna principal de valor se chame literalmente `valor` (pra tipos `chart_bar`, `chart_bar_horizontal`, `chart_line`, `chart_doughnut` — e também `kpi`/`map`, que usam o mesmo sistema de contrato). Isso significa que a legenda/tooltip do gráfico sempre mostra "valor" como nome da série principal, mesmo quando isso não é descritivo (ex: "Perdas" faria mais sentido que "valor"). Colunas extras (2ª+ série, multi-série automática) já podem ter qualquer alias — só a primeira coluna fica presa ao nome técnico exigido pelo contrato.

## Decisão

Novo campo opcional, só pra `chart_bar`/`chart_bar_horizontal`/`chart_line` (não se aplica a `chart_doughnut`, cujas fatias já são nomeadas pelo `label`, não por "valor"): um nome de exibição que sobrescreve como a série `valor` aparece na legenda e no tooltip, sem alterar a validação de contrato (que continua exigindo a coluna `valor` internamente). Se vazio, comportamento atual é preservado (mostra "valor").

**Fora de escopo:** renomear colunas extras (já funciona via alias SQL), relaxar a exigência de nome `valor` no contrato (afeta KPI/Mapa também, risco maior pra pouco ganho).

## Modelo de dados

```sql
ALTER TABLE queries ADD COLUMN chart_valor_label VARCHAR(50);
```

Nullable, sem default (`NULL` = usa "valor" como hoje).

## Backend

- `QueryInput`/`QueryUpdate`: `chart_valor_label: Optional[str] = None`
- `criar_query`: incluir no INSERT
- `atualizar_query`: incluir em `ALLOWED_COLS`
- `renderizar_painel`: incluir `q.chart_valor_label` no SELECT

## Frontend

- `nova/+page.svelte` e `[id]/+page.svelte`: campo de texto "Nome de exibição do valor principal (opcional)" dentro do bloco "Configurações do Gráfico", visível só quando `['chart_bar','chart_bar_horizontal','chart_line'].includes(form.tipo)` (aninhado dentro do bloco maior, que continua valendo pros 4 tipos pras outras 3 opções).
- `ChartPanel.svelte`: nova prop `valorLabel = null`. Onde hoje `cols` vira `series[].name` e `legend.data`, mapear: se a coluna for `'valor'` e `valorLabel` estiver preenchido, usar `valorLabel` no lugar; senão manter o nome da coluna como está hoje.
- `painel/[slug]/+page.svelte`: passar `valorLabel={ind.chart_valor_label}`.

## Verificação

- Query `chart_bar` sem `chart_valor_label` preenchido — legenda/tooltip continuam mostrando "valor" (sem regressão).
- Preencher "Perdas" — legenda/tooltip mostram "Perdas" no lugar de "valor"; colunas extras continuam com seus próprios nomes.
- `chart_doughnut` — campo não aparece na tela de config (fora de escopo pra esse tipo).
- Editar o campo depois de já ter dados em cache — reflete na hora (já corrigido o bug de invalidação de cache anteriormente).
