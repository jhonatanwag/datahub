# Query Base — reaproveitar SQL entre indicadores irmãos — Design

## Contexto

Levantamento real no banco de dev (2026-09-16): o grupo de queries
"Pendência" (`query_grupos.id = 5`) tem hoje 30 queries ativas (10 formas
de indicador × 3 "tipos" de pendência — `PENDENCIA`/`SEDE`/`LAVOURA`,
essas duas últimas criadas nesta mesma sessão por pedido do usuário,
duplicando o padrão já existente), somando ~70KB de `sql_texto`. Confirmado
por inspeção linha a linha: as 10 formas por tipo compartilham o **mesmo**
bloco de `FROM pendencia this_ ... 14 LEFT JOIN ... WHERE <12 parâmetros>`
— só o `SELECT`/`GROUP BY` final e o literal `tipo = 'X'` mudam. Esse
bloco compartilhado responde por ~80% do texto de cada query. O mesmo
padrão (reaproveitar o bloco de JOIN entre "queries irmãs" do mesmo
domínio) está documentado como convenção deliberada em
`PROMPT-CRIAR-DASHBOARDS.md` seção 3.1 — o problema não é o padrão em si
(ele é correto: mantém os mesmos filtros em todo o grupo), é que hoje
cada query irmã **copia o texto inteiro**, então qualquer ajuste no JOIN
(nova tabela, filtro novo) precisa ser replicado manualmente em todas.

Esse mesmo padrão se repete nos grupos Perdas, EPI e Abastecimento.

**Duas dores distintas, tratadas em fases separadas:**
1. **Manutenção** — editar o JOIN em 10+ lugares toda vez, risco real de
   esquecer uma query irmã (já aconteceu: ver histórico de correções
   pontuais em queries específicas do mesmo grupo).
2. **Performance** — um painel com 10 indicadores dispara hoje até 10
   idas ao Postgres, mesmo quando 9 delas fariam o mesmo JOIN de novo só
   pra agrupar diferente.

Este documento cobre só a **Fase 1** (mata a duplicação de SQL, baixo
risco, não muda o motor de execução). A Fase 2 (uma execução da base
compartilhada entre indicadores irmãos do mesmo carregamento de painel,
resolvendo a dor de performance) fica para um design separado depois que
a Fase 1 estiver validada em produção — ela depende do conceito de "base"
que a Fase 1 introduz.

## Decisões

- **Novo campo `queries.query_base_id`** (FK pra `queries.id`), mesmo
  padrão que `subquery_id` já usa hoje (FK simples, sem tabela filha,
  `ON DELETE SET NULL`).
- **Composição por CTE**: quando `query_base_id` está preenchido, o
  backend executa `WITH base AS (<sql_texto da base>) <sql_texto da
  derivada>`. A query derivada escreve seu SQL **como se `base` já fosse
  uma tabela** — sem repetir `FROM`/`JOIN`/filtros.
- **Parâmetros pertencem à base.** Uma query derivada normalmente não tem
  `query_parametros` próprios — os `$1..$N` usados dentro do SQL da base
  são resolvidos a partir de `query_parametros` **da base**, não da
  derivada. Se uma derivada precisar de um parâmetro próprio (raro, ex.
  um filtro extra só daquele indicador), ele é numerado **depois** dos da
  base (`$N+1` em diante) e cadastrado em `query_parametros` da própria
  derivada — os valores são concatenados nessa ordem.
- **Só 1 nível.** Uma query que já é derivada (`query_base_id IS NOT
  NULL`) não pode ser escolhida como base de outra — validado em
  `criar_query`/`atualizar_query`. Evita CTE aninhada e mantém o mental
  model simples ("base" é sempre uma folha).
- **Tipo da base não é travado**, mas a convenção recomendada é
  `tipo = 'table'` (a base é uma fonte de linhas cruas; quem decide como
  exibir — kpi/chart/table — é sempre a derivada, do mesmo jeito que
  `table_dynamic` já separa "dado" de "apresentação"). Não crio validação
  bloqueante pra isso nesta fase — mesmo nível de confiança que o resto
  do cadastro de query já tem hoje (ex: `impressao_coluna` não valida se
  a coluna existe).
- **Cache continua por slug da derivada**, sem mudança em
  `cache_ttl`/chave Redis. Isso significa que, nesta fase, 10 indicadores
  derivados da mesma base ainda disparam até 10 execuções reais no
  Postgres (a CTE roda de novo, do zero, a cada SELECT separado) — **a
  Fase 1 resolve só a duplicação de texto, não o número de consultas**.
  Documentado explicitamente em "Fora de escopo" pra não criar expectativa
  errada.
- **Nenhuma mudança no contrato de retorno por tipo, no `renderizar_painel`,
  nem nos componentes de frontend que consomem `ind.dados`.** Do ponto de
  vista de quem consome o resultado de uma query derivada, nada muda —
  ela continua tendo seu próprio `slug`, `tipo`, `kpi_cor_*`, `chart_*`,
  `meta_*`, `chart_filtro_coluna`, `impressao_*`, `imprimir` por
  indicador, cache_ttl próprio, tudo igual a uma query independente de
  hoje. Só a **origem do dado bruto** passa a ser compartilhada.
- **Ortogonal a `subquery_id`/`table_dynamic`.** Uma query pode ter
  `query_base_id` E `subquery_id` ao mesmo tempo (é uma derivada de uma
  base, e também tem um drill-down configurado) — os dois mecanismos não
  se sobrepõem.

## Modelo de dados

```sql
ALTER TABLE queries ADD COLUMN query_base_id INTEGER REFERENCES queries(id) ON DELETE SET NULL;
CREATE INDEX idx_queries_base ON queries(query_base_id);
```

**Migração:** refletir em `scripts/init-db.sql` (seed local) e
`scripts/init-meta-prod.sql` (schema prod), documentar como pendência
manual em produção no README ("Deltas de schema pendentes"), mesmo
processo dos specs anteriores.

## Backend

### `backend/services/query_runner.py` — `resolver_query`

Depois de buscar `query = dict(rows[0])` (linha ~98), antes de montar
`sql`/`param_rows`:

```python
sql = query["sql_texto"]
query_params_id = query["id"]

if query.get("query_base_id"):
    base_rows = await query_meta(
        "SELECT * FROM queries WHERE id = $1 AND ativo = true", query["query_base_id"]
    )
    if not base_rows:
        raise ValueError(f"Query base de '{slug}' não encontrada ou inativa")
    base = dict(base_rows[0])
    sql = f"WITH base AS ({base['sql_texto']}) {query['sql_texto']}"
    query_params_id = base["id"]
```

E trocar a busca de `param_rows` (linha ~110) pra usar `query_params_id`
em vez de `query["id"]` direto. Se a derivada também tiver seus próprios
`query_parametros` (caso raro citado nas Decisões), concatenar depois:

```python
param_rows = await query_meta(""" ... WHERE qp.query_id = $1 ORDER BY qp.id """, query_params_id)
if query.get("query_base_id"):
    param_rows += await query_meta(""" ... WHERE qp.query_id = $1 ORDER BY qp.id """, query["id"])
```

Resto da função (resolução de valor por parâmetro, `_cast`, execução via
`query_company`, cache) **não muda nada** — já opera em cima de
`sql`/`param_rows`/`valores` genéricos.

### `backend/routes/queries.py`

- `QueryInput`/`QueryUpdate`: adicionar `query_base_id: Optional[int] = None`.
- `criar_query` e `atualizar_query`: nova validação (função helper
  `_validar_query_base(query_base_id, excluir_id=None)`):
  - Busca a query base por id; se não existir ou `ativo=false`, 400.
  - Se `base["query_base_id"] is not None`, 400 ("não é permitido
    encadear: a query escolhida como base já é derivada de outra").
  - Se `query_base_id == excluir_id` (a própria query, em edição), 400.
- `criar_query`: incluir `query_base_id` no `INSERT` (mesmo padrão de
  `subquery_id`, linha ~428/443).
- `atualizar_query`: incluir `'query_base_id'` em `ALLOWED_COLS` (linha
  ~478); rodar `_validar_query_base` quando `"query_base_id" in updates`.
- **Invalidação de cache em cascata**: hoje `atualizar_query` só invalida
  o cache da própria query quando `sql_texto`/`slug` mudam (linha
  ~530-531). Se a query editada é **base de outras** (existe alguma
  `queries.query_base_id = query_id`), mudar `sql_texto`, `ativo` ou
  `slug` dela também invalida o cache de **todas as derivadas** (elas
  dependem do SQL da base sem que o backend saiba disso só olhando o
  próprio slug). Novo helper em `query_runner.py`:
  ```python
  async def invalidar_cache_derivadas(query_id: int):
      derivadas = await query_meta("SELECT slug FROM queries WHERE query_base_id = $1", query_id)
      for d in derivadas:
          await invalidar_cache_query(d["slug"])
  ```
  Chamado em `atualizar_query` sempre que `"sql_texto" in updates or "ativo" in updates or "slug" in updates`, logo depois da invalidação já existente.
- `testar_query`: se `body.query_base_id` vier preenchido, buscar a base
  (mesma validação de existir/ativa) e compor
  `sql = f"WITH base AS ({base['sql_texto']}) {body.sql_texto}"` antes de
  chamar `query_company` (linha ~205) — `body.testar_parametros` nesse
  caso deve representar os parâmetros **da base** (o frontend monta essa
  lista a partir de `parametrosQuery(base_id)`, não dos parâmetros da
  query sendo criada).
- `duplicar_query` (linha ~542-606): incluir `query_base_id` na lista de
  colunas copiadas do `INSERT ... SELECT` — duplicar uma derivada mantém
  o vínculo com a mesma base.

### `backend/services/portabilidade.py`

Mesmo tratamento que `subquery_id` já recebe (busca por slug, resolução
em duas passadas pra não quebrar por ordem de criação):

- `_serializar_query`: adicionar
  `out["base_query_slug"] = await _nome_por_id("queries", "slug", row["query_base_id"])`
  (ao lado da linha 57, que já faz isso pra `subquery_slug`).
- `montar_bundle_painel` (BFS de dependências, linha ~146-149): mesmo
  bloco pro `query_base_id`:
  ```python
  if rowq["query_base_id"]:
      base = await query_meta("SELECT slug FROM queries WHERE id = $1", rowq["query_base_id"])
      if base:
          fila.append(base[0]["slug"])
  ```
- `_QUERY_DIFF_KEYS` (linha ~217-220): incluir `"base_query_slug"`.
- `_criar_ou_atualizar_query` (passo 1, linha ~398-418): continua **sem**
  `query_base_id` no INSERT/UPDATE inicial (evita problema de ordem —
  base pode não existir ainda na primeira passada).
- Novo passo de resolução (mirror do bloco de `subquery_id` em ~437 e
  ~581-583): depois que todas as queries do bundle foram
  criadas/atualizadas, resolver `base_query_slug` → id real e fazer
  `UPDATE queries SET query_base_id = $1 WHERE slug = $2 AND empresa_id
  IS NOT DISTINCT FROM $3` pra cada uma; se `base_query_slug` for nulo,
  `UPDATE ... SET query_base_id = NULL` (mesmo tratamento do
  `subquery_id` quando desmarcado).

## Frontend

### `frontend/src/lib/api.js`

Sem mudança — `criarQuery`/`atualizarQuery`/`testarQuery` já mandam o
form inteiro no corpo.

### `frontend/src/routes/configuracoes/queries/nova/+page.svelte` (espelhar em `[id]/+page.svelte`)

- `form.query_base_id: null` no estado inicial (junto de `subquery_id`,
  linha ~22).
- `queriesBase` derivado: `queriesDisponiveis.filter(q => !q.query_base_id && q.id !== form.id)`
  — só oferece como base queries que **não são elas mesmas derivadas**
  (reflete a regra de 1 nível só) e nunca a própria query em edição.
- Novo `<select bind:value={form.query_base_id}>` "Query base (opcional)"
  — posicionado acima do editor de SQL, com texto de apoio: *"Se
  preenchida, escreva o SELECT abaixo como se `base` já fosse uma
  tabela — sem repetir FROM/JOIN/filtros."* Mesma área visual de onde
  hoje fica o seletor de `subquery_id` (linha ~482), mas **disponível pra
  qualquer `tipo`**, não só `table_dynamic`.
- Ao mudar `form.query_base_id`: buscar `baseParams =
  await api.parametrosQuery(form.query_base_id)` (mesmo mecanismo de
  `onSubqueryChange`, linha ~139-145) e mostrar essa lista, **somente
  leitura**, como referência de quais parâmetros já estão disponíveis
  dentro da CTE (não precisa recriá-los).
- `testar()` (linha ~147-161): quando `form.query_base_id` estiver
  setado, os valores de teste (`_testar_valor`) vêm dos inputs de
  `baseParams` em vez de `params` (que fica vazio/oculto pra derivadas no
  caso comum); `testar_parametros` montado a partir de `baseParams`. O
  `sql_texto` enviado continua sendo só o texto da derivada — a
  composição da CTE acontece no backend (ver `testar_query` acima).
- `salvar()`: sem mudança de lógica — `form` já vai inteiro no payload,
  `query_base_id` incluído automaticamente.

## Migração piloto: grupo Pendência

Prova de conceito da Fase 1, aplicada nas 30 queries que já existem hoje
(`PENDENCIA`/`SEDE`/`LAVOURA` × 10 formas). **Os slugs não mudam** — só
`sql_texto`, `query_base_id` e `query_parametros` das 30 derivadas — logo
nenhum `painel_indicadores.query_slug` precisa ser tocado, os 3 painéis
(`pen_pendencias_equip`, `pen_pendencias_sede`, `pen_pendencias_lavoura`)
continuam funcionando sem qualquer mudança neles.

**Passo 1 — criar 3 queries base** (`tipo = 'table'`, `ativo = true`,
**sem vínculo com nenhum painel** — existem só como fonte pras
derivadas), uma por tipo de pendência, reaproveitando o `FROM`/`JOIN` e
os 12 parâmetros que as 10 originais já têm, com o `SELECT` expandido pra
cobrir todas as colunas que qualquer uma das 10 derivadas precisa:

```sql
SELECT
  this_.pendencia_id                          AS pendencia_id,
  this_.mob_pend_id                           AS "ID",
  upper(this_.descricao)                      AS "Descrição Pendência",
  this_.situacao_pendencia                    AS situacao_pendencia,
  tv.tip_veic_id                              AS tip_veic_id,
  tv.descricao                                AS "Tipo Veiculo",
  m.modelo_id                                 AS modelo_id,
  m.descricao                                 AS "Modelo",
  m2.marca_id                                 AS marca_id,
  m2.descricao                                AS "Marca",
  v.veiculo_id                                AS veiculo_id,
  v.placa                                     AS placa,
  v.prefixo                                   AS prefixo,
  f2.frente_trabalho_id                       AS frente_trabalho_id,
  f2.descricao                                AS frente_trabalho_descricao,
  s3.sistema_id                               AS sistema_id,
  s3.descricao                                AS sistema_descricao,
  floor((DATE_PART('DAY',(coalesce(data_realizada,now())-data_abertura))*24)
    + (extract(HOUR FROM(coalesce(data_realizada, now())-data_abertura)))
    + (extract(MINUTE FROM(coalesce(data_realizada, now())-data_abertura))/60)) AS "Horas Pendente",
  floor((DATE_PART('DAY',(coalesce(data_autorizada,now())-data_abertura))*24)
    + (extract(hour from (coalesce(data_autorizada, now())-data_abertura)))
    + (extract(MINUTE FROM (coalesce(data_autorizada, now())-data_abertura))/60)) AS "Horas Aguard. Autorização",
  floor(coalesce((DATE_PART('DAY',(coalesce(data_realizada, now())-data_autorizada))*24)
    + (extract(HOUR FROM (coalesce(data_realizada, now())-data_autorizada)))
    + (extract(MINUTE FROM (coalesce(data_realizada, now())-data_autorizada))/60),0)) AS "Horas Aguard. Manutenção"
FROM pendencia this_
left outer join pessoa p on this_.pessoa_id=p.pessoa_id
left outer join propriedade p2 on this_.propriedade_id=p2.propriedade_id
left outer join setor s on this_.setor_id=s.setor_id
left outer join sub_sistema s2 on this_.subsistema_id=s2.sub_sistema_id
left outer join sistema s3 on s2.sistema_id=s3.sistema_id
left outer join talhao t on this_.talhao_id=t.talhao_id
left outer join usuario u on this_.usuario_cadastro_id=u.usuario_id
left outer join funcionario f on u.usuario_id=f.funcionario_id
left outer join veiculo v on this_.veiculo_id=v.veiculo_id
left outer join hist_alocacao h on v.veiculo_id = h.veiculo_id
left outer join frente_trabalho f2 on h.frente_trabalho_id=f2.frente_trabalho_id
left outer join modelo m on v.modelo_id=m.modelo_id
left outer join marca m2 on m.marca_id=m2.marca_id
left outer join tipo_veiculo tv on v.tip_veic_id=tv.tip_veic_id
where cast(this_.data_abertura as DATE) between $1 and $2
and h.data_inicio<=this_.data_cadastro and (h.data_fim>=this_.data_cadastro or h.data_fim is null)
and ($3::text is null or f.funcionario_id = any(string_to_array($3, ',')::bigint[]))
and ($4::text is null or v.veiculo_id = any(string_to_array($4, ',')::bigint[]))
and ($5::text is null or tv.tip_veic_id = any(string_to_array($5, ',')::bigint[]))
and ($6::text is null or m2.marca_id = any(string_to_array($6, ',')::bigint[]))
and ($7::text is null or m.modelo_id = any(string_to_array($7, ',')::bigint[]))
and ($8::text is null or s3.sistema_id = any(string_to_array($8, ',')::bigint[]))
and ($9::text is null or s2.sub_sistema_id = any(string_to_array($9, ',')::bigint[]))
and exists (select 'x' from frente_trabalho_func c where c.frente_trabalho_id = h.frente_trabalho_id and c.funcionario_id::text = $10)
and ($11::text is null or f2.frente_trabalho_id = any(string_to_array($11, ',')::bigint[]))
and ($12::text is null or this_.situacao_pendencia = any(string_to_array($12, ',')))
and tipo = 'PENDENCIA'   -- 'SEDE' / 'LAVOURA' nas outras duas bases
```

Slugs sugeridos: `pen_pendencias_base_pendencia`, `pen_pendencias_base_sede`,
`pen_pendencias_base_lavoura` — `query_parametros` idêntico ao que as 10
originais já têm hoje (copiado de qualquer uma delas, são todos iguais).

**Passo 2 — reescrever as 30 derivadas**, apontando `query_base_id` pra
sua base correspondente, `sql_texto` reduzido ao `SELECT`/`GROUP BY`
final (mesmo texto pras 3 variantes de tipo, só a base muda), e
`query_parametros` **esvaziado** (`DELETE FROM query_parametros WHERE
query_id = ...`, já que os 12 parâmetros agora vivem só na base):

| Forma (mesmo texto nas 3 variantes) | SQL derivado |
|---|---|
| pendente/aguar_manut/finalizadas (equip.) | `SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) \|\| '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'PENDENTE'` (trocar o literal pra `'AGUARDANDO_MANUTENCAO'`/`'FINALIZADA'` nas outras duas) |
| por_frente | `SELECT frente_trabalho_id AS id, frente_trabalho_descricao AS label, count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'PENDENTE') AS valor, count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'PENDENCIA_ACOMPANHADA') AS "Pend. Acompanhada", count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'AGUARDANDO_MANUTENCAO') AS "Aguard. Manutenção", count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'FINALIZADA') AS "Finalizada" FROM base GROUP BY frente_trabalho_id, frente_trabalho_descricao` |
| percentual_sit | `SELECT situacao_pendencia, CASE WHEN situacao_pendencia = 'PENDENCIA_ACOMPANHADA' THEN 'PEND. ACOMPANHADA' WHEN situacao_pendencia = 'AGUARDANDO_MANUTENCAO' THEN 'AGUARD. MANUTENÇÃO' ELSE situacao_pendencia END AS label, ROUND(COUNT(DISTINCT pendencia_id) * 100.0 / SUM(COUNT(DISTINCT pendencia_id)) OVER (), 2) AS valor FROM base GROUP BY situacao_pendencia ORDER BY CASE situacao_pendencia WHEN 'PENDENTE' THEN 1 WHEN 'PENDENCIA_ACOMPANHADA' THEN 2 WHEN 'AGUARDANDO_MANUTENCAO' THEN 3 WHEN 'FINALIZADA' THEN 4 ELSE 99 END` |
| por_sistemas_em_aberto | `SELECT sistema_id, sistema_descricao AS label, count(distinct pendencia_id) AS valor FROM base WHERE situacao_pendencia = 'PENDENTE' GROUP BY sistema_id, sistema_descricao ORDER BY 3` |
| por_tipo (equip) | `SELECT tip_veic_id, "Tipo Veiculo" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY tip_veic_id, "Tipo Veiculo" ORDER BY 3` |
| por_tipo_marca | `SELECT marca_id, "Marca" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY marca_id, "Marca" ORDER BY 3` |
| por_tipo_modelo | `SELECT modelo_id, "Modelo" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY modelo_id, "Modelo" ORDER BY 3` |
| lançamentos | `SELECT "ID", "Descrição Pendência", "Tipo Veiculo", "Modelo", "Marca", placa, prefixo, "Horas Pendente", "Horas Aguard. Autorização", "Horas Aguard. Manutenção" FROM base` |

Cada linha da tabela acima é **um texto de SQL só**, reaproveitado nas 3
variantes (PENDENCIA/SEDE/LAVOURA) — só a base referenciada muda. Isso
reduz o grupo de **30 blocos de ~2.1KB** (JOIN completo repetido) para
**3 bases de ~2.1KB + 30 derivadas de ~150-400 bytes cada**: cai de ~70KB
pra ~13KB de SQL cadastrado, e qualquer ajuste futuro no JOIN (nova
tabela, novo filtro) passa a ser feito em **3 lugares** (um por tipo), não
30.

## Fora de escopo

- **Reduzir o número de consultas reais no Postgres** — fica pra Fase 2
  (execução compartilhada entre indicadores irmãos do mesmo
  carregamento de painel). Nesta fase, cada derivada ainda dispara sua
  própria ida ao banco, CTE incluída.
- **Migrar os grupos Perdas, EPI e Abastecimento** — só o grupo Pendência
  entra como piloto nesta entrega; os outros seguem o mesmo padrão de
  duplicação hoje e podem ser migrados depois, um de cada vez, usando o
  mesmo mecanismo (sem mudança de código necessária).
- **UI de aviso quando o SQL da derivada referencia uma coluna que a base
  não tem** — mesmo nível de confiança que `impressao_coluna`/colunas de
  agrupamento já têm hoje (erro só aparece ao clicar "Testar").
- **Validar `empresa_id` compatível entre base e derivada** — fica por
  conta de quem cadastra, mesma confiança que o resto do formulário.
- **Editar `query_base_id` de volta pra `null` via PATCH parcial** — como
  `QueryUpdate` usa `exclude_none=True` (mesma limitação que já existe
  hoje pra `subquery_id`), "desvincular" uma derivada da base exige
  recriar a query ou um endpoint dedicado — não é regressão nova, é
  padrão já existente no código.

## Verificação

- Criar uma query base de teste (`tipo = 'table'`) e uma derivada
  apontando `query_base_id` pra ela, com SQL que só faz
  `SELECT coluna, count(*) FROM base GROUP BY coluna` — "Testar" deve
  rodar e mostrar resultado agregado corretamente.
- Editar o SQL da base (mudar um filtro) e confirmar, via
  `GET /api/queries/executar/<slug-da-derivada>`, que o resultado reflete
  a mudança sem precisar tocar na derivada (prova que a cascata de cache
  funciona).
- Tentar escolher como base uma query que já é derivada de outra — deve
  retornar 400.
- Tentar escolher `query_base_id` apontando pra si mesma (em edição) —
  400.
- Migração do grupo Pendência: comparar, pra cada uma das 30 queries,
  o resultado de `resolver_query` **antes** (SQL antigo, salvo) e
  **depois** (base + derivada) com os mesmos parâmetros de teste — linhas
  e valores devem bater exatamente.
- Abrir os 3 painéis (`pen_pendencias_equip`, `pen_pendencias_sede`,
  `pen_pendencias_lavoura`) no navegador depois da migração — mesma
  aparência e mesmos dados de antes, filtro por clique continua
  funcionando (`filtro_clique_variavel_id` não muda).
- Exportar um desses painéis via portabilidade
  (`GET /api/paineis/{id}/exportar`) e conferir no JSON que as queries
  base aparecem no bundle (dependência transitiva) mesmo sem estar
  ligadas a nenhum `painel_indicadores`.
- Suíte `pytest` completa (`docker exec datahub_backend python -m pytest
  tests/ -v`) sem regressão — nenhum teste existente depende do formato
  atual de `resolver_query`/`queries.py` de um jeito que quebre com
  `query_base_id` opcional e por padrão `NULL`.
