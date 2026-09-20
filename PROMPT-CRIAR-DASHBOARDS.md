# PROMPT-CRIAR-DASHBOARDS.md — Guia para criar painéis novos

## Para que serve este arquivo

Guia de referência que a IA (Claude) deve seguir sempre que o usuário pedir
para criar, adaptar ou estender um painel/dashboard no DataHub. Ele documenta
os **padrões reais** já usados nos painéis existentes (empresas `prats` e
`vitoria-agronegocios`, grupos Perdas/Pendência/EPI/Abastecimento/Inspeção),
não o desenho original do sistema — os arquivos `PROMPT-PAINEIS.md` e
`arquitetura-queries-dinamicas.md` na raiz do repo descrevem a versão inicial
do sistema (2026-07) e estão defasados em vários pontos (tipos de query,
grupos, table_dynamic, filtro por clique, meta etc. não existiam ainda).
Quando este arquivo e aqueles divergirem, **este arquivo vence**.

Leia o `README.md` (seções de deploy/armadilhas) e a memória do projeto antes
de tocar em produção — este guia cobre só o *como desenhar* o painel, não
deploy/infra.

---

## 1. Modelo mental

```
Variável (filtro reutilizável)
        ↓
Query (SQL cadastrado, usa $1, $2... na ordem de query_parametros)
        ↓
Grupo de queries (query_grupos — organiza por domínio: "Perdas", "EPI"...)
        ↓
Painel (grid de colunas + indicadores posicionados + variáveis vinculadas)
        ↓
Usuários com acesso ao painel
```

Cada empresa tem seu próprio banco (`prats`, `vitoria_agro`, etc.) — as
queries rodam nesse banco via `query_company`, nunca no `datahub_meta`. O
`datahub_meta` só guarda a *definição* de queries/variáveis/painéis.

---

## 2. Convenção de nomenclatura

- **Slug de query**: prefixo curto do domínio + nome descritivo, tudo
  minúsculo com `_`. Prefixos reais já em uso: `per_` (perdas), `pen_`
  (pendências), `epi_`, `lanc_` (lançamentos/fichas), `aba_`
  (abastecimento). Exemplos: `per_perda_media`, `pen_pendencias_por_frente`,
  `epi_cas_vencidos`.
  - `kpi_*`, `chart_*`, `table_*`, `map_*`, `rag_*` também aparecem como
    prefixo quando o painel é genérico (seed antigo `alpha`/`beta`/`gamma`)
    — para painéis de domínio real, prefira o prefixo do domínio, não do
    tipo (o `tipo` já fica na coluna `tipo`, repetir no slug é redundante,
    mas os dados reais mostram os dois estilos convivendo; siga o prefixo
    de domínio do grupo em que a query vai entrar).
- **Slug de variável**: sempre `var_<entidade>` (ex.: `var_fazenda`,
  `var_equipamento`, `var_marca_equipamento`). Exceções históricas sem
  prefixo: `periodo`, `data_unica`, `texto_livre` (variáveis genéricas
  seed, não específicas de domínio).
- **Nome (label) de query/variável**: português, capitalizado, curto —
  é o que aparece como título do card/filtro (`"Perda Média"`, `"Fazenda"`).
- **Slug de painel**: prefixo do domínio + contexto (`per_perdas_gerencial`,
  `pen_pendencias`, `epi_entrega_epi`). **Slug usa `_`, não `-`** — o slug
  vira o identificador da URL (`/painel/<slug>`) e é editável na tela de
  edição do painel.

---

## 3. Padrões de SQL

### 3.1 Bloco de FROM/JOIN reaproveitado por grupo

Todas as queries do mesmo domínio reaproveitam **o mesmo bloco de
FROM/JOIN**, mesmo que uma query só precise de 2 das 10 tabelas
disponíveis — mantém consistência de parâmetros entre as queries do grupo
(todas aceitam os mesmos filtros, na mesma ordem). Exemplo real (grupo
Perdas, banco `prats`):

```sql
FROM perda p
inner join perda_lancamento pl ON pl.perda_id = p.perda_id
left join frente_trabalho ft on ft.frente_trabalho_id = p.frente_trabalho_id
left join funcionario f on f.funcionario_id = p.funcionario_id
left join operacao o on o.operacao_id = p.operacao_id
left join propriedade p2 on p2.propriedade_id = p.propriedade_id
left join talhao t on t.talhao_id = pl.talhao_id
left join veiculo v on v.veiculo_id = p.veiculo_id
left join usuario u on u.usuario_id = p.usuario_cadastro_id
left join variedade v2 on v2.variedade_id = pl.variedade_id
left join metodo_perda mp on mp.metodo_perda_id = p.metodo_perda_id
```

Ao criar uma query nova num grupo já existente, **copie o bloco de JOIN da
query irmã mais próxima** em vez de reescrever do zero — garante que os
mesmos filtros (`$3`, `$4`...) funcionem em todo o grupo.

### 3.2 Filtro de período (`date_range`)

Padrão real (note o `to_date(to_char(...))` em vez de comparar a coluna de
timestamp direto — normaliza pra data pura, ignorando hora):

```sql
where to_date(to_char(p.data_cadastro,'dd/mm/yyyy'),'dd/mm/yyyy') between $1 and $2
```

`$1`/`$2` correspondem à variável `periodo` (`param_slot = 'inicio'/'fim'`
em `query_parametros`).

### 3.3 Filtro `multiselect`

O frontend manda o valor como **string separada por vírgula** num único
parâmetro — nunca use `= ANY($N)` direto, sempre `string_to_array`:

```sql
and ($3::text is null or o.operacao_id = any(string_to_array($3, ',')::bigint[]))
```

Troque `::bigint[]` por `::text[]` (ou remova o cast) se a coluna filtrada
for texto. Para variável `select` (valor único, não múltiplo):

```sql
and ($N::text is null or coluna = $N)
```

### 3.4 Filtro por clique (drill-down entre indicadores do mesmo painel)

Mecanismo pra "clicar numa barra/fatia do gráfico e filtrar o painel
inteiro por aquele valor":

1. Na query de **origem** do clique (o gráfico clicável), preencha
   `chart_filtro_coluna` com o nome da coluna do resultado que carrega o
   valor bruto a capturar (ex.: `operacao_id`, `propriedade_id` — **não**
   `label`, a menos que o clique deva filtrar por texto).
2. No `painel_indicadores` desse mesmo indicador, preencha
   `filtro_clique_variavel_id` com o id da **variável do painel** que deve
   receber o valor clicado (ex.: clicar em "Perdas por Operação" seta
   `var_operacao`).
3. Toda query do painel que já aceita `var_operacao` como filtro reage
   automaticamente — não precisa de nada a mais nelas.
4. Um último parâmetro de "data única" por clique também é comum: `$N`
   comparando a data normalizada com `coalesce($N, <a própria data>)` —
   usado quando o clique é num ponto de uma série temporal
   (`chart_filtro_coluna = 'label'` na query `per_evolucao_perda_data`).

Exemplos reais de mapeamento clique→variável (painel "Perdas"):
`per_perdas_operacao` (fatia) → `var_operacao`;
`per_top10_media_fazenda` (barra) → `var_fazenda`;
`per_top10_media_operador` (barra) → `var_funcionario_lanc_ficha`.

### 3.5 `query_fonte` de variável `select`/`multiselect`

Precisa retornar colunas **literalmente chamadas `valor` e `label`** — o
backend valida isso (`_validar_colunas_valor_label` em
`backend/routes/variaveis.py`) e recusa com erro claro em vez de preview
em branco. Padrão real:

```sql
select p.propriedade_id as valor, p.descricao as label
from propriedade p
where p.situacao_cadastro = 'ATIVO'
order by 2;
```

Pra opções fixas sem tabela (enums), usar `VALUES`:

```sql
SELECT situacao_pendencia as valor, desc_situacao_pendencia as label
FROM (VALUES
    ('PENDENTE', 'Pendente'),
    ('FINALIZADA', 'Finalizada')
) AS t(situacao_pendencia, desc_situacao_pendencia);
```

### 3.6 Parâmetro manual sem variável (`codigo_usuario_externo`)

Se precisar de um filtro **invisível pro usuário final** (o backend injeta
sozinho, não vira campo na tela), crie o parâmetro em `query_parametros`
**sem `variavel_id`**, com `nome = 'codigo_usuario_externo'` — é o único
caso hoje com esse padrão de injeção automática pelo backend. Não crie
esse padrão para outro nome sem confirmar com o usuário; é específico.

---

## 4. Contrato de retorno por `tipo` de query

Tipos válidos hoje (`TIPOS_VALIDOS` em `backend/routes/queries.py`): `kpi`,
`chart_line`, `chart_bar`, `chart_bar_horizontal`, `chart_doughnut`,
`table`, `table_dynamic`, `map`, `rag_context`.

| tipo | colunas obrigatórias | observações |
|---|---|---|
| `kpi` | `valor`, `label` | 1 linha só. `label` pode ser dinâmico (`CASE` pra "unidades mistas" quando agrega fontes diferentes). |
| `chart_line` / `chart_bar` / `chart_bar_horizontal` | `label`, `valor` | uma linha por categoria/ponto. |
| `chart_doughnut` | `label`, `valor` | idem, soma vira 100%. |
| `table` | qualquer | frontend gera cabeçalho de cada coluna do jeito que vier — **dê nome de coluna já em português/apresentável** (`select ... as "Fazenda"`), não IDs crus. |
| `table_dynamic` | qualquer, com aliases legíveis | ver seção 6 — os aliases das colunas viram os nomes usados em `agrupamentos`/`agregacoes`. |
| `map` | `lat`, `lng`, `label`, `valor` | `group by` nas coordenadas; `mapa_camada` = `'padrao'` ou `'satelite'`. |
| `rag_context` | livre | vira texto injetado no contexto do assistente IA. |

---

## 5. Campos de configuração por query (tabela `queries`)

- **`cache_ttl`** (segundos): `300` é o padrão pra tudo que roda com
  filtros; `600` pra gráficos "pesados" com poucas mudanças; `120` pra
  tabelas "recentes" que precisam atualizar mais rápido. `0` desliga cache.
- **KPI**: `kpi_cor_fonte`/`kpi_cor_fundo` (hex; os grupos reais usam pares
  temáticos por domínio — ex. `#F3F8F5`/`#2B5A45` no grupo Perdas, não o
  default genérico `#e6edf3`/`#161b22` — escolha uma paleta coerente por
  grupo). `kpi_valor_primeiro` (bool) inverte a ordem visual
  número/rótulo dentro do card. `kpi_imagem_habilitada` +
  `kpi_imagem_posicao` (`'direita'`/`'esquerda'`) pra logo/ícone dentro do
  card (upload via `POST /api/queries/{id}/kpi-imagem`, nunca no corpo do
  JSON — é `bytea`).
- **Chart**: `chart_rotulo_eixo`/`chart_rotulo_valor` (`'horizontal'` por
  padrão; usar `'vertical'`/outros valores válidos quando os rótulos do
  eixo X forem longos e colidirem). `chart_fonte_tamanho` (padrão `12`).
  `chart_truncar_label` + `chart_truncar_tamanho` (padrão `15` chars) pra
  categorias com nome longo. `chart_mostrar_valor` + `chart_valor_label`
  pra exibir o valor numérico junto da barra/fatia. `chart_filtro_coluna`
  — ver seção 3.4.
- **Meta (linha de referência)**: `meta_habilitada` + `meta_coluna_valor`
  (coluna do resultado com o valor real) + `meta_coluna_inicio`/
  `meta_coluna_fim` (faixa aceitável) + `meta_cor_dentro`/`meta_cor_fora`
  (verde/vermelho por padrão) — usado em gráficos onde existe uma meta a
  bater.
- **Impressão/PDF**: `impressao_habilitada` + `impressao_caminho` +
  `impressao_coluna` — liga essa query ao fluxo de "Imprimir" de
  documento externo por linha da tabela (proxy). Em painéis, cada
  indicador também tem `painel_indicadores.imprimir` (bool) controlando
  se aquele card entra no PDF do relatório do painel (independente da
  tela normal).
- **`grupo_id`**: vincula a query a um `query_grupos.id` — organiza queries
  por domínio na tela de configuração. Crie o grupo antes (ou reaproveite
  um existente do mesmo domínio) e aponte todas as queries do painel pra
  ele.
- **`subquery_id`**: só relevante pra `table_dynamic` — ver seção 6.

---

## 6. `table_dynamic` (tabela pivot com drill-down)

Usada quando o usuário quer agrupar/agregar dados no próprio frontend em
vez de fazer `GROUP BY` no SQL (permite trocar o agrupamento sem editar a
query). A query em si é só um `SELECT` "flat" com colunas já formatadas
(os nomes de coluna viram os rótulos usados a seguir — dê nomes
apresentáveis, com acento e espaço se for o caso, ex.: `"Frente de
trabalho"`, `"Tipo de equipamento"`, `"Id."`).

- `query_agrupamentos` (`coluna`, `ordem`): colunas pelas quais a tabela
  agrupa, em cascata (nível 0, nível 1...) — referencia o nome exato da
  coluna retornada pela query.
- `query_agregacoes` (`coluna`, `funcao`, `label`, `ordem`): o que mostrar
  por grupo. `funcao` ∈ `soma`, `contagem`, `media`, `minimo`, `maximo`
  (ver `FUNCOES` em `frontend/src/lib/components/DynamicTable.svelte`).
- **Pivô de colunas (opcional)** — colunas dinâmicas tipo "Jan | Fev | Mar |
  Total Geral" (`queries.pivot_coluna`, `pivot_ordem_coluna`, `pivot_total`;
  seção "Pivô de colunas" na tela da query): `pivot_coluna` é a coluna do
  resultado cujos **valores distintos viram colunas**; `pivot_ordem_coluna`
  (opcional) ordena essas colunas (ex.: `aaaamm` numérico — sem ela vale a
  ordem de aparição; a coluna de ordem some das linhas de detalhe);
  `pivot_total` liga a coluna "Total Geral" e a linha "Total Geral" no fim.
  Cada célula usa a **1ª agregação** (sem nenhuma, conta linhas); mês sem
  ocorrência fica em branco. Exige ao menos 1 agrupamento (as células ficam
  nas linhas de grupo: subtotal por grupo, e o detalhe abre ao expandir).
  O rótulo da coluna vem do SQL, então devolva já formatado e ordenável
  (ex.: `to_char(data,'MM/YYYY')` + `to_char(data,'YYYYMM')::int` como ordem).
  Funciona na tela, no PDF do painel e no export CSV/Excel.
- **Drill-down opcional**: se `subquery_id` aponta pra outra query
  (normalmente `tipo = 'table'`), ao expandir uma linha o frontend chama
  essa subquery passando parâmetros extraídos da linha clicada, mapeados
  em `query_subquery_parametros` (`coluna_origem` = nome da coluna na
  linha pai, `parametro_destino` = nome do parâmetro esperado pela
  subquery, casado por **nome** em `query_parametros` da subquery, não
  por posição).

Exemplo real: `equipamentos_por_frente` (`table_dynamic`) agrupa por
`"Frente de trabalho"` → `"Tipo de equipamento"`, agrega `contagem` de
`"Id."` como `"Qtd."`; ao expandir, `subquery_id` aponta pra
`sub_query_historico_alocacao`, mapeando a coluna `"Id."` da linha clicada
pro parâmetro `equip` da subquery.

---

## 7. Layout de painel

`paineis.colunas` define o grid (a maioria dos painéis reais usa `4`,
alguns telas de exportação usam `1`). Cada `painel_indicadores` tem
`linha`/`coluna` (posição no grid, começa em 1) + `col_span`/`row_span`
(quantas células ocupa) + `posicao` (ordem de leitura/render, não precisa
bater com a ordem visual linha/coluna).

**Padrão real de painel "gerencial" (grid de 4 colunas)** — copie esta
estrutura ao criar um painel de visão geral de um domínio:

1. Linha 1–2: KPIs em `col_span = 2` (2 por linha → 4 KPIs em 2 linhas).
   Ex.: "Perda Média", "Aferições" / "Maior Perda", "Fazendas Avaliadas".
2. Depois dos KPIs: um `chart_doughnut` em `col_span = 4` (largura cheia)
   — visão de distribuição por categoria principal do domínio.
3. Em seguida: dois `chart_bar_horizontal` lado a lado, `col_span = 2`
   cada — rankings ("Top 10 por X", "Top 10 por Y").
4. Depois: um `chart_line` em `col_span = 4` — evolução temporal.
5. Depois: mais um `chart_bar_horizontal` em `col_span = 4`, se houver
   outro ranking relevante.
6. Por último: uma `table` em `col_span = 4` — o detalhe linha a linha,
   normalmente a mesma que alimenta `impressao_habilitada` pro PDF.

Todos os indicadores desse padrão real têm `imprimir = true` (entram no
relatório PDF por padrão — só desmarque se um card for redundante no
papel, ex. gráfico interativo sem valor impresso).

---

## 8. Variáveis padrão de um painel

Praticamente todo painel de domínio real tem:

- Um **multiselect por entidade relevante do domínio** (equipamento,
  fazenda, funcionário/operador, operação, marca, modelo, sistema, tipo
  de equipamento, frente de trabalho — conforme o que a query realmente
  filtra).
- **`periodo`** (`date_range`) sempre por último na lista, **obrigatório**
  (`obrigatorio = true`), com `valor_padrao_inicio = 'mes_atual_inicio'`
  e `valor_padrao_fim = 'mes_atual_fim'` (tokens resolvidos tanto no
  backend — `query_runner._cast`, quanto no frontend —
  `resolverToken()`). Não invente outro range como default sem pedir
  confirmação — "mês atual" é o padrão observado em todos os painéis
  reais.

A ordem das variáveis no painel (`painel_variaveis.posicao`) segue a
ordem em que aparecem como parâmetros nas queries do painel — entidades
primeiro, período por último.

---

## 9. Grupos (`query_grupos` / `paineis.grupo_id`)

Cada domínio de negócio (Perdas, Pendência, EPI, Abastecimento...) tem seu
próprio grupo — usado só para organizar a listagem nas telas de
configuração (`/configuracoes/queries`, `/configuracoes/paineis`), sem
efeito em permissão ou execução. Ao criar um domínio novo, crie o grupo
primeiro (`POST` equivalente em `query_grupos`/`painel_grupos` — checar
rota exata em `backend/routes/` antes de inserir direto no banco) e
aponte todas as queries/o painel novo pra ele.

---

## 10. Passo a passo para criar um painel novo

Quando o usuário pedir um painel novo, siga esta ordem (não pule etapas,
mas adapte: se as variáveis/grupo já existirem, reaproveite):

1. **Entender o domínio**: que tabelas/colunas do banco da empresa
   alimentam esse painel? Peça ao usuário (ou explore o banco da empresa
   via `docker exec` se tiver acesso) — nunca invente nomes de coluna.
2. **Variáveis**: crie as que faltarem (`var_<entidade>`, `multiselect`
   com `query_fonte` retornando `valor`/`label`) — reaproveite as que já
   existem (ex. `var_fazenda`, `var_equipamento` já cobrem várias
   empresas/domínios).
3. **Grupo**: crie ou reaproveite um `query_grupos` pro domínio.
4. **Queries**: uma por indicador do painel, seguindo a seção 3 (bloco de
   JOIN reaproveitado, filtros na mesma ordem entre queries irmãs).
   **Teste cada query antes de salvar** (endpoint `POST
   /api/queries/testar` ou equivalente na tela) — nunca cadastre SQL não
   testado.
5. **Painel**: crie com `colunas` (normalmente 4) e monte o layout
   seguindo o padrão da seção 7.
6. **Vincular indicadores**: `linha`/`coluna`/`col_span`/`row_span`,
   `titulo` (override), `filtro_clique_variavel_id` se aplicável,
   `imprimir`.
7. **Vincular variáveis**: entidades do domínio + `periodo` por último,
   com os defaults da seção 8.
8. **Vincular usuários**: quem deve ver esse painel.
9. **Testar de ponta a ponta**: abrir o painel, aplicar filtros, testar
   clique-pra-filtrar se configurado, gerar o PDF se o painel tiver
   `impressao_habilitada` em alguma query.

---

## 11. Portabilidade dev → produção

Depois que o painel estiver pronto e testado em dev, use a feature de
portabilidade em vez de recriar manualmente em produção:

- `GET /api/paineis/{id}/exportar` — baixa um `.json` (bundle) com painel
  + indicadores + queries + variáveis + grupos envolvidos.
- `POST /api/portabilidade/paineis/analisar` — sobe o bundle no ambiente
  de destino e devolve um diagnóstico (o que já existe, o que é novo, o
  que colide por slug) **sem aplicar nada**.
- `POST /api/portabilidade/paineis/importar` — aplica de fato, com um
  mapa `aplicar` dizendo o que criar/sobrescrever a partir da análise
  anterior.

Sempre rode `analisar` antes de `importar` e mostre o diagnóstico pro
usuário confirmar — nunca importe direto sem essa etapa. Ver
`backend/services/portabilidade.py` pro contrato exato dos campos.

**Nota de estado (2026-09-16):** essa feature foi mergeada em `master`
mas ainda não teve o frontend testado em browser numa sessão anterior —
antes de recomendar seu uso via UI para o usuário, confirme que a tela
`/configuracoes/paineis/importar` está funcional (teste rápido) ao invés
de assumir que está pronta.

---

## 12. Quando propor ajuste no sistema em vez de só configurar

Este guia cobre o que já é possível com o sistema atual. Se o pedido do
usuário esbarrar numa limitação real (ex.: um tipo de agregação que
`DynamicTable.svelte` não suporta, uma camada de mapa nova, um tipo de
gráfico que não existe), **não invente um workaround silencioso dentro do
SQL** — pare, explique a limitação encontrada, e proponha o ajuste de
código necessário como uma mudança separada (bounded, com confirmação),
seguindo os padrões de código do restante do projeto (FastAPI/asyncpg no
backend, Svelte 5 sem TypeScript no frontend).

## 13. Segurança e validação (não pule)

- Toda query cadastrada passa por `validar_sql` — só `SELECT` é permitido,
  palavras como `drop`/`delete`/`insert`/`update`/`alter` são bloqueadas.
  Não tente contornar isso em nome de "facilitar" o pedido do usuário.
- `slug` de query é único por `(slug, empresa_id)` — pode reaproveitar o
  mesmo slug entre queries global/empresa-específica, mas não duplicar
  dentro da mesma empresa.
- Nunca cole SQL não testado direto em produção — teste em dev (ou via
  `testar_query` contra o banco da empresa certa) antes de exportar.
