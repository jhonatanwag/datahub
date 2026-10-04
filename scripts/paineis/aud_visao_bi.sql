-- Painel "Visão BI - Auditorias" (aud_visao_bi) — rodar no datahub_meta.
-- Requer o delta scripts/migrations/2026-10-04-faixa-cor-table-dynamic.sql (cores por faixa).
-- Idempotente: reexecutar apaga e recria o painel/queries/variável NOVOS deste script.
-- Reaproveita as variáveis periodo, var_fazenda, var_fichas e var_funcionario_lanc_ficha.
-- Parâmetros (mesma ordem em todas as queries): $1 início, $2 fim, $3 fazenda, $4 grupo de auditoria,
--   $5 ficha (auditoria), $6 funcionário (quem realizou).
-- Auditoria = lancamento_ficha de ficha com tipo_ficha = 'AUDITORIA'; nota = lancamento_ficha.nota_final.
-- Cores: até 70 vermelho, 71 a 90 amarelo, acima de 90 verde (faixa_cor_*).
BEGIN;

DELETE FROM painel_indicadores WHERE painel_id IN (SELECT id FROM paineis WHERE slug = 'aud_visao_bi');
DELETE FROM painel_variaveis   WHERE painel_id IN (SELECT id FROM paineis WHERE slug = 'aud_visao_bi');
DELETE FROM painel_usuarios    WHERE painel_id IN (SELECT id FROM paineis WHERE slug = 'aud_visao_bi');
DELETE FROM paineis   WHERE slug = 'aud_visao_bi';
DELETE FROM queries   WHERE slug LIKE 'aud_%' AND empresa_id IS NULL;
DELETE FROM variaveis WHERE slug = 'var_grupo_auditoria';

INSERT INTO variaveis (slug, nome, descricao, tipo, query_fonte, ativo) VALUES (
  'var_grupo_auditoria', 'Grupo de Auditoria', 'Grupo de ficha de inspeção (Manejo, Sede, Pulverizações...)', 'multiselect',
  $q$select g.grupofichains_id as valor, g.descricao as label
from grupofichainspecao g
where g.situacao_cadastro = 'ATIVO'
order by 2$q$, true);

-- ── KPIs ──────────────────────────────────────────────────────────────
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id, kpi_cor_fonte, kpi_cor_fundo) VALUES (
  'aud_kpi_total', 'Auditorias Realizadas', 'Quantidade de auditorias lançadas no período/filtros',
  $q$select count(*) as valor, 'Auditorias Realizadas' as label
from lancamento_ficha lf
join ficha fi on fi.ficha_id = lf.ficha_id
where fi.tipo_ficha = 'AUDITORIA' and lf.nota_final is not null
  and lf.data_cadastro::date between $1 and $2
  and ($3::text is null or lf.propriedade_id = any(string_to_array($3, ',')::bigint[]))
  and ($4::text is null or fi.grupo_ficha_inspecao = any(string_to_array($4, ',')::bigint[]))
  and ($5::text is null or lf.ficha_id = any(string_to_array($5, ',')::bigint[]))
  and ($6::text is null or lf.funcionario_id = any(string_to_array($6, ',')::bigint[]))$q$,
  'kpi', 300, true, (SELECT id FROM query_grupos WHERE nome = 'Inspeção'), '#F3F8F5', '#2B5A45');

INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id, kpi_cor_fonte, kpi_cor_fundo) VALUES (
  'aud_kpi_media', 'Nota Média', 'Média das notas das auditorias no período/filtros',
  $q$select coalesce(round(avg(lf.nota_final), 2), 0) as valor, 'Nota Média' as label
from lancamento_ficha lf
join ficha fi on fi.ficha_id = lf.ficha_id
where fi.tipo_ficha = 'AUDITORIA' and lf.nota_final is not null
  and lf.data_cadastro::date between $1 and $2
  and ($3::text is null or lf.propriedade_id = any(string_to_array($3, ',')::bigint[]))
  and ($4::text is null or fi.grupo_ficha_inspecao = any(string_to_array($4, ',')::bigint[]))
  and ($5::text is null or lf.ficha_id = any(string_to_array($5, ',')::bigint[]))
  and ($6::text is null or lf.funcionario_id = any(string_to_array($6, ',')::bigint[]))$q$,
  'kpi', 300, true, (SELECT id FROM query_grupos WHERE nome = 'Inspeção'), '#F3F8F5', '#2B5A45');

-- ── Matriz Fazenda x Grupo de Auditoria (célula = nota média, com cores) ──
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id,
                     pivot_coluna, pivot_ordem_coluna, pivot_total,
                     faixa_cor_habilitada, faixa_cor_ate_vermelho, faixa_cor_ate_amarelo) VALUES (
  'aud_matriz_grupo', 'Auditorias por Fazenda e Grupo', 'Nota média por propriedade (linhas) e grupo de auditoria (colunas); ao expandir, as auditorias',
  $q$select p.descricao as "Propriedade",
       coalesce(g.descricao, '(sem grupo)') as "Grupo de Auditoria",
       dense_rank() over (order by coalesce(g.descricao, '(sem grupo)')) as "Ordem Grupo",
       lf.nota_final as "Nota"
from lancamento_ficha lf
join ficha fi on fi.ficha_id = lf.ficha_id
left join grupofichainspecao g on g.grupofichains_id = fi.grupo_ficha_inspecao
left join propriedade p on p.propriedade_id = lf.propriedade_id
where fi.tipo_ficha = 'AUDITORIA' and lf.nota_final is not null
  and lf.data_cadastro::date between $1 and $2
  and ($3::text is null or lf.propriedade_id = any(string_to_array($3, ',')::bigint[]))
  and ($4::text is null or fi.grupo_ficha_inspecao = any(string_to_array($4, ',')::bigint[]))
  and ($5::text is null or lf.ficha_id = any(string_to_array($5, ',')::bigint[]))
  and ($6::text is null or lf.funcionario_id = any(string_to_array($6, ',')::bigint[]))
order by p.descricao$q$,
  'table_dynamic', 300, true, (SELECT id FROM query_grupos WHERE nome = 'Inspeção'),
  'Grupo de Auditoria', 'Ordem Grupo', true, true, 70, 90);

-- ── Matriz Fazenda x Auditoria (tipo da ficha) ────────────────────────
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id,
                     pivot_coluna, pivot_ordem_coluna, pivot_total,
                     faixa_cor_habilitada, faixa_cor_ate_vermelho, faixa_cor_ate_amarelo) VALUES (
  'aud_matriz_auditoria', 'Auditorias por Fazenda e Tipo', 'Nota média por propriedade (linhas) e auditoria/ficha (colunas)',
  $q$select p.descricao as "Propriedade",
       fi.descricao as "Auditoria",
       dense_rank() over (order by fi.descricao) as "Ordem Auditoria",
       lf.nota_final as "Nota"
from lancamento_ficha lf
join ficha fi on fi.ficha_id = lf.ficha_id
left join grupofichainspecao g on g.grupofichains_id = fi.grupo_ficha_inspecao
left join propriedade p on p.propriedade_id = lf.propriedade_id
where fi.tipo_ficha = 'AUDITORIA' and lf.nota_final is not null
  and lf.data_cadastro::date between $1 and $2
  and ($3::text is null or lf.propriedade_id = any(string_to_array($3, ',')::bigint[]))
  and ($4::text is null or fi.grupo_ficha_inspecao = any(string_to_array($4, ',')::bigint[]))
  and ($5::text is null or lf.ficha_id = any(string_to_array($5, ',')::bigint[]))
  and ($6::text is null or lf.funcionario_id = any(string_to_array($6, ',')::bigint[]))
order by p.descricao$q$,
  'table_dynamic', 300, true, (SELECT id FROM query_grupos WHERE nome = 'Inspeção'),
  'Auditoria', 'Ordem Auditoria', true, true, 70, 90);

-- ── Detalhe: quem fez + impressão da ficha ────────────────────────────
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id,
                     impressao_habilitada, impressao_caminho, impressao_coluna) VALUES (
  'aud_detalhe', 'Detalhe das Auditorias', 'Auditorias realizadas: data, fazenda, grupo, ficha, quem realizou, nota e impressão da ficha',
  $q$select lf.lancamentoficha_id as id,
       to_char(lf.data_cadastro, 'DD/MM/YYYY HH24:MI') as "Data",
       p.descricao as "Propriedade",
       coalesce(g.descricao, '(sem grupo)') as "Grupo de Auditoria",
       fi.descricao as "Auditoria",
       coalesce(f.nome_funcionario, '-') as "Realizada por",
       lf.nota_final as "Nota"
from lancamento_ficha lf
join ficha fi on fi.ficha_id = lf.ficha_id
left join grupofichainspecao g on g.grupofichains_id = fi.grupo_ficha_inspecao
left join propriedade p on p.propriedade_id = lf.propriedade_id
left join funcionario f on f.funcionario_id = lf.funcionario_id
where fi.tipo_ficha = 'AUDITORIA' and lf.nota_final is not null
  and lf.data_cadastro::date between $1 and $2
  and ($3::text is null or lf.propriedade_id = any(string_to_array($3, ',')::bigint[]))
  and ($4::text is null or fi.grupo_ficha_inspecao = any(string_to_array($4, ',')::bigint[]))
  and ($5::text is null or lf.ficha_id = any(string_to_array($5, ',')::bigint[]))
  and ($6::text is null or lf.funcionario_id = any(string_to_array($6, ',')::bigint[]))
order by lf.data_cadastro desc$q$,
  'table', 300, true, (SELECT id FROM query_grupos WHERE nome = 'Inspeção'),
  true, 'relatorioAuditoria/ImpressaoWeb.xhtml?lancamentoFichaId=', 'id');

-- ── Agrupamento / agregação dos table_dynamic ─────────────────────────
INSERT INTO query_agrupamentos (query_id, coluna, ordem)
SELECT id, 'Propriedade', 0 FROM queries WHERE slug IN ('aud_matriz_grupo', 'aud_matriz_auditoria') AND empresa_id IS NULL;
INSERT INTO query_agregacoes (query_id, coluna, funcao, label, ordem)
SELECT id, 'Nota', 'media', 'Nota', 0 FROM queries WHERE slug IN ('aud_matriz_grupo', 'aud_matriz_auditoria') AND empresa_id IS NULL;

-- ── Parâmetros: um INSERT por posição (o runner lê ORDER BY id) ───────
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id, param_slot)
SELECT q.id, 'periodo_inicio', 'date_range', true, v.id, 'inicio'
FROM queries q, variaveis v WHERE q.slug LIKE 'aud_%' AND q.empresa_id IS NULL AND v.slug = 'periodo' ORDER BY q.id;
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id, param_slot)
SELECT q.id, 'periodo_fim', 'date_range', true, v.id, 'fim'
FROM queries q, variaveis v WHERE q.slug LIKE 'aud_%' AND q.empresa_id IS NULL AND v.slug = 'periodo' ORDER BY q.id;
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id)
SELECT q.id, v.slug, 'multiselect', false, v.id
FROM queries q, variaveis v WHERE q.slug LIKE 'aud_%' AND q.empresa_id IS NULL AND v.slug = 'var_fazenda' ORDER BY q.id;
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id)
SELECT q.id, v.slug, 'multiselect', false, v.id
FROM queries q, variaveis v WHERE q.slug LIKE 'aud_%' AND q.empresa_id IS NULL AND v.slug = 'var_grupo_auditoria' ORDER BY q.id;
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id)
SELECT q.id, v.slug, 'multiselect', false, v.id
FROM queries q, variaveis v WHERE q.slug LIKE 'aud_%' AND q.empresa_id IS NULL AND v.slug = 'var_fichas' ORDER BY q.id;
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id)
SELECT q.id, v.slug, 'multiselect', false, v.id
FROM queries q, variaveis v WHERE q.slug LIKE 'aud_%' AND q.empresa_id IS NULL AND v.slug = 'var_funcionario_lanc_ficha' ORDER BY q.id;

-- ── Painel (4 colunas, PDF em paisagem por causa das matrizes largas) ─
INSERT INTO paineis (slug, nome, descricao, icone, colunas, ativo, ordem_menu, impressao_orientacao) VALUES (
  'aud_visao_bi', 'Visão BI - Auditorias',
  'Notas das auditorias por fazenda, por grupo de auditoria e por auditoria (até 70 vermelho, 71 a 90 amarelo, acima de 90 verde), com quem realizou e impressão da ficha.',
  'chart', 4, true, 6, 'paisagem');

INSERT INTO painel_indicadores (painel_id, query_slug, titulo, linha, coluna, col_span, row_span, posicao, imprimir)
SELECT p.id, x.slug, x.titulo, x.linha, x.coluna, x.col_span, 1, x.pos, true
FROM paineis p,
     (VALUES ('aud_kpi_total',          'Auditorias Realizadas',                    1, 1, 2, 1),
             ('aud_kpi_media',          'Nota Média',                               1, 3, 2, 2),
             ('aud_matriz_grupo',       'Auditorias por Fazenda e Grupo de Auditoria', 2, 1, 4, 3),
             ('aud_matriz_auditoria',   'Auditorias por Fazenda e Tipo de Auditoria',  3, 1, 4, 4),
             ('aud_detalhe',            'Detalhe das Auditorias',                   4, 1, 4, 5)) AS x(slug, titulo, linha, coluna, col_span, pos)
WHERE p.slug = 'aud_visao_bi';

-- Variáveis: entidades primeiro, período por último ("até o momento" = do início do ano até hoje)
INSERT INTO painel_variaveis (painel_id, variavel_id, obrigatorio, posicao, valor_padrao_inicio, valor_padrao_fim)
SELECT p.id, v.id, x.obrig, x.pos, x.ini, x.fim
FROM paineis p,
     (VALUES ('var_fazenda', false, 0, NULL, NULL),
             ('var_grupo_auditoria', false, 1, NULL, NULL),
             ('var_fichas', false, 2, NULL, NULL),
             ('var_funcionario_lanc_ficha', false, 3, NULL, NULL),
             ('periodo', true, 4, 'ano_atual_inicio', 'hoje')) AS x(slug, obrig, pos, ini, fim)
JOIN variaveis v ON v.slug = x.slug
WHERE p.slug = 'aud_visao_bi';

-- Acesso: libera para os administradores; vincule os demais usuários pela tela do painel.
INSERT INTO painel_usuarios (painel_id, usuario_id)
SELECT p.id, u.id FROM paineis p, usuarios u WHERE p.slug = 'aud_visao_bi' AND u.role = 'admin' AND u.ativo = true;

COMMIT;
