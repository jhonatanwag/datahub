-- Painel "Ranking de Check Lists" (insp_ranking_checklist) — rodar no datahub_meta.
-- Idempotente: reexecutar apaga e recria o painel/queries/variável NOVOS deste script.
-- Reaproveita as variáveis periodo, var_fazenda e var_fichas.
-- Parâmetros (mesma ordem em todas as queries): $1 início, $2 fim, $3 fazenda, $4 ficha, $5 tipo de ficha.
--   "Top 10 do grupo" ignora a fazenda ($3 só é referenciado pra manter a contagem de parâmetros);
--   "Top 10 da fazenda" respeita $3 e fica vazio enquanto nenhuma fazenda é escolhida.
-- Unidade contada: lançamento de ficha (lancamento_ficha) por funcionario_id (quem apontou).
BEGIN;

DELETE FROM painel_indicadores WHERE painel_id IN (SELECT id FROM paineis WHERE slug = 'insp_ranking_checklist');
DELETE FROM painel_variaveis   WHERE painel_id IN (SELECT id FROM paineis WHERE slug = 'insp_ranking_checklist');
DELETE FROM painel_usuarios    WHERE painel_id IN (SELECT id FROM paineis WHERE slug = 'insp_ranking_checklist');
DELETE FROM paineis   WHERE slug = 'insp_ranking_checklist';
DELETE FROM queries   WHERE slug LIKE 'insp_rank_%' AND empresa_id IS NULL;
DELETE FROM variaveis WHERE slug = 'var_tipo_ficha';

INSERT INTO variaveis (slug, nome, descricao, tipo, query_fonte, ativo) VALUES (
  'var_tipo_ficha', 'Tipo de Ficha', 'Rotina, Preventiva ou Auditoria', 'multiselect',
  $q$SELECT tipo_ficha as valor, desc_tipo_ficha as label
FROM (VALUES ('ROTINA', 'Rotina / Check List'), ('PREVENTIVA', 'Preventiva / Inspeção'), ('AUDITORIA', 'Auditoria'))
  AS t(tipo_ficha, desc_tipo_ficha)$q$, true);

-- ── KPIs ──────────────────────────────────────────────────────────────
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id, kpi_cor_fonte, kpi_cor_fundo) VALUES (
  'insp_rank_kpi_total', 'Check Lists Apontados', 'Total de lançamentos de ficha no período/filtros',
  $q$select count(*) as valor, 'Check Lists Apontados' as label
from lancamento_ficha lf
join ficha fi on fi.ficha_id = lf.ficha_id
where lf.funcionario_id is not null
  and lf.data_cadastro::date between $1 and $2
  and ($3::text is null or lf.propriedade_id = any(string_to_array($3, ',')::bigint[]))
  and ($4::text is null or lf.ficha_id = any(string_to_array($4, ',')::bigint[]))
  and ($5::text is null or fi.tipo_ficha = any(string_to_array($5, ',')))$q$,
  'kpi', 300, true, (SELECT id FROM query_grupos WHERE nome = 'Inspeção'), '#F3F8F5', '#2B5A45');

INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id, kpi_cor_fonte, kpi_cor_fundo) VALUES (
  'insp_rank_kpi_colaboradores', 'Colaboradores Apontando', 'Colaboradores distintos com ao menos um check list no período/filtros',
  $q$select count(distinct lf.funcionario_id) as valor, 'Colaboradores Apontando' as label
from lancamento_ficha lf
join ficha fi on fi.ficha_id = lf.ficha_id
where lf.funcionario_id is not null
  and lf.data_cadastro::date between $1 and $2
  and ($3::text is null or lf.propriedade_id = any(string_to_array($3, ',')::bigint[]))
  and ($4::text is null or lf.ficha_id = any(string_to_array($4, ',')::bigint[]))
  and ($5::text is null or fi.tipo_ficha = any(string_to_array($5, ',')))$q$,
  'kpi', 300, true, (SELECT id FROM query_grupos WHERE nome = 'Inspeção'), '#F3F8F5', '#2B5A45');

-- ── Top 10 colaboradores — GRUPO (todas as fazendas) ──────────────────
-- Rótulo = colaborador + fazenda onde mais apontou (como no layout de referência).
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id,
                     chart_mostrar_valor, chart_truncar_label, chart_fonte_tamanho) VALUES (
  'insp_rank_top10_grupo', 'Top 10 Colaboradores - Grupo', 'Ranking de check lists apontados por colaborador, somando todas as fazendas',
  $q$with base as (
  select lf.funcionario_id, lf.propriedade_id
  from lancamento_ficha lf
  join ficha fi on fi.ficha_id = lf.ficha_id
  where lf.funcionario_id is not null
    and lf.data_cadastro::date between $1 and $2
    and ($3::text is null or true)
    and ($4::text is null or lf.ficha_id = any(string_to_array($4, ',')::bigint[]))
    and ($5::text is null or fi.tipo_ficha = any(string_to_array($5, ',')))
),
top10 as (
  select funcionario_id, count(*) as qtd from base group by 1 order by 2 desc limit 10
),
faz as (
  select distinct on (b.funcionario_id) b.funcionario_id, p.descricao
  from base b
  join propriedade p on p.propriedade_id = b.propriedade_id
  where b.funcionario_id in (select funcionario_id from top10)
  group by b.funcionario_id, p.descricao
  order by b.funcionario_id, count(*) desc
)
select trim(f.nome_funcionario) || coalesce(' - ' || z.descricao, '') as label, t.qtd as valor
from top10 t
join funcionario f on f.funcionario_id = t.funcionario_id
left join faz z on z.funcionario_id = t.funcionario_id
order by t.qtd desc, 1$q$,
  'chart_bar', 300, true, (SELECT id FROM query_grupos WHERE nome = 'Inspeção'), true, false, 9);

-- ── Top 10 colaboradores — FAZENDA selecionada ────────────────────────
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id,
                     chart_mostrar_valor, chart_truncar_label, chart_fonte_tamanho) VALUES (
  'insp_rank_top10_fazenda', 'Top 10 Colaboradores - Fazenda', 'Ranking de check lists por colaborador apenas nas fazendas selecionadas (vazio sem fazenda)',
  $q$with base as (
  select lf.funcionario_id, lf.propriedade_id
  from lancamento_ficha lf
  join ficha fi on fi.ficha_id = lf.ficha_id
  where lf.funcionario_id is not null
    and $3::text is not null
    and lf.data_cadastro::date between $1 and $2
    and lf.propriedade_id = any(string_to_array($3, ',')::bigint[])
    and ($4::text is null or lf.ficha_id = any(string_to_array($4, ',')::bigint[]))
    and ($5::text is null or fi.tipo_ficha = any(string_to_array($5, ',')))
),
top10 as (
  select funcionario_id, count(*) as qtd from base group by 1 order by 2 desc limit 10
),
faz as (
  select distinct on (b.funcionario_id) b.funcionario_id, p.descricao
  from base b
  join propriedade p on p.propriedade_id = b.propriedade_id
  where b.funcionario_id in (select funcionario_id from top10)
  group by b.funcionario_id, p.descricao
  order by b.funcionario_id, count(*) desc
)
select trim(f.nome_funcionario) || coalesce(' - ' || z.descricao, '') as label, t.qtd as valor
from top10 t
join funcionario f on f.funcionario_id = t.funcionario_id
left join faz z on z.funcionario_id = t.funcionario_id
order by t.qtd desc, 1$q$,
  'chart_bar', 300, true, (SELECT id FROM query_grupos WHERE nome = 'Inspeção'), true, false, 9);

-- ── Top 10 frotas (equipamento 1 do lançamento) ───────────────────────
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id,
                     chart_mostrar_valor, chart_truncar_label, chart_fonte_tamanho) VALUES (
  'insp_rank_top10_frotas', 'Top 10 Frotas', 'Equipamentos com mais check lists apontados',
  $q$select trim(coalesce(v.prefixo, '') || ' - ' || v.descricao) as label, count(*) as valor
from lancamento_ficha lf
join ficha fi on fi.ficha_id = lf.ficha_id
join veiculo v on v.veiculo_id = lf.veiculo_id1
where lf.funcionario_id is not null
  and lf.data_cadastro::date between $1 and $2
  and ($3::text is null or lf.propriedade_id = any(string_to_array($3, ',')::bigint[]))
  and ($4::text is null or lf.ficha_id = any(string_to_array($4, ',')::bigint[]))
  and ($5::text is null or fi.tipo_ficha = any(string_to_array($5, ',')))
group by v.veiculo_id, v.prefixo, v.descricao
order by 2 desc, 1
limit 10$q$,
  'chart_bar', 300, true, (SELECT id FROM query_grupos WHERE nome = 'Inspeção'), true, false, 9);

-- ── Total por data ────────────────────────────────────────────────────
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id,
                     chart_mostrar_valor, chart_truncar_label, chart_fonte_tamanho) VALUES (
  'insp_rank_por_data', 'Total por Data', 'Check lists apontados por dia',
  $q$select to_char(d.dia, 'DD/MM/YYYY') as label, d.qtd as valor
from (
  select lf.data_cadastro::date as dia, count(*) as qtd
  from lancamento_ficha lf
  join ficha fi on fi.ficha_id = lf.ficha_id
  where lf.funcionario_id is not null
    and lf.data_cadastro::date between $1 and $2
    and ($3::text is null or lf.propriedade_id = any(string_to_array($3, ',')::bigint[]))
    and ($4::text is null or lf.ficha_id = any(string_to_array($4, ',')::bigint[]))
    and ($5::text is null or fi.tipo_ficha = any(string_to_array($5, ',')))
  group by 1
) d
order by d.dia$q$,
  'chart_line', 300, true, (SELECT id FROM query_grupos WHERE nome = 'Inspeção'), true, false, 10);

-- ── Parâmetros: um INSERT por posição (o runner lê ORDER BY id) ───────
-- $1/$2 período
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id, param_slot)
SELECT q.id, 'periodo_inicio', 'date_range', true, v.id, 'inicio'
FROM queries q, variaveis v WHERE q.slug LIKE 'insp_rank_%' AND q.empresa_id IS NULL AND v.slug = 'periodo' ORDER BY q.id;
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id, param_slot)
SELECT q.id, 'periodo_fim', 'date_range', true, v.id, 'fim'
FROM queries q, variaveis v WHERE q.slug LIKE 'insp_rank_%' AND q.empresa_id IS NULL AND v.slug = 'periodo' ORDER BY q.id;
-- $3 fazenda, $4 ficha, $5 tipo de ficha
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id)
SELECT q.id, v.slug, 'multiselect', false, v.id
FROM queries q, variaveis v WHERE q.slug LIKE 'insp_rank_%' AND q.empresa_id IS NULL AND v.slug = 'var_fazenda' ORDER BY q.id;
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id)
SELECT q.id, v.slug, 'multiselect', false, v.id
FROM queries q, variaveis v WHERE q.slug LIKE 'insp_rank_%' AND q.empresa_id IS NULL AND v.slug = 'var_fichas' ORDER BY q.id;
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id)
SELECT q.id, v.slug, 'multiselect', false, v.id
FROM queries q, variaveis v WHERE q.slug LIKE 'insp_rank_%' AND q.empresa_id IS NULL AND v.slug = 'var_tipo_ficha' ORDER BY q.id;

-- ── Painel (grid de 4 colunas) ────────────────────────────────────────
INSERT INTO paineis (slug, nome, descricao, icone, colunas, ativo, ordem_menu) VALUES (
  'insp_ranking_checklist', 'Ranking de Check Lists',
  'Top 10 de colaboradores e frotas por quantidade de check lists apontados — total do grupo ou por fazenda.',
  'chart', 4, true, 5);

INSERT INTO painel_indicadores (painel_id, query_slug, titulo, linha, coluna, col_span, row_span, posicao, imprimir)
SELECT p.id, x.slug, x.titulo, x.linha, x.coluna, x.col_span, 1, x.pos, true
FROM paineis p,
     (VALUES ('insp_rank_kpi_total',        'Check Lists Apontados',                    1, 1, 2, 1),
             ('insp_rank_kpi_colaboradores','Colaboradores Apontando',                  1, 3, 2, 2),
             ('insp_rank_top10_grupo',      'Top 10 Colaboradores - Total do Grupo',    2, 1, 4, 3),
             ('insp_rank_top10_fazenda',    'Top 10 Colaboradores - Fazenda Selecionada', 3, 1, 4, 4),
             ('insp_rank_top10_frotas',     'Top 10 Frotas',                            4, 1, 4, 5),
             ('insp_rank_por_data',         'Total por Data',                           5, 1, 4, 6)) AS x(slug, titulo, linha, coluna, col_span, pos)
WHERE p.slug = 'insp_ranking_checklist';

-- Variáveis: entidades primeiro, período por último (obrigatório, mês atual)
INSERT INTO painel_variaveis (painel_id, variavel_id, obrigatorio, posicao, valor_padrao_inicio, valor_padrao_fim)
SELECT p.id, v.id, x.obrig, x.pos, x.ini, x.fim
FROM paineis p,
     (VALUES ('var_fazenda', false, 0, NULL, NULL),
             ('var_fichas', false, 1, NULL, NULL),
             ('var_tipo_ficha', false, 2, NULL, NULL),
             ('periodo', true, 3, 'mes_atual_inicio', 'mes_atual_fim')) AS x(slug, obrig, pos, ini, fim)
JOIN variaveis v ON v.slug = x.slug
WHERE p.slug = 'insp_ranking_checklist';

-- Acesso: libera para os administradores; vincule os demais usuários pela tela do painel.
INSERT INTO painel_usuarios (painel_id, usuario_id)
SELECT p.id, u.id FROM paineis p, usuarios u WHERE p.slug = 'insp_ranking_checklist' AND u.role = 'admin' AND u.ativo = true;

COMMIT;
