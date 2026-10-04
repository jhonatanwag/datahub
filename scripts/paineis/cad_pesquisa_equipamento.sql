-- Painel "Pesquisa de Equipamento" (cad_pesquisa_equipamento) — rodar no datahub_meta.
-- Idempotente: reexecutar apaga e recria o painel/queries/variáveis NOVAS deste script.
-- Requer: tipo de query `card` (CardPerfil) e endpoint /api/imagens/tipo-veiculo/{id}.
-- Reaproveita a variável existente var_tipo_equipamento.
-- Parâmetros (mesma ordem em todas as queries): $1 busca, $2 tipo (multiselect), $3 status, $4 equipamento.
-- Sem busca nem equipamento escolhido nenhuma query retorna linhas (estado vazio).
BEGIN;

DELETE FROM painel_indicadores WHERE painel_id IN (SELECT id FROM paineis WHERE slug = 'cad_pesquisa_equipamento');
DELETE FROM painel_variaveis   WHERE painel_id IN (SELECT id FROM paineis WHERE slug = 'cad_pesquisa_equipamento');
DELETE FROM painel_usuarios    WHERE painel_id IN (SELECT id FROM paineis WHERE slug = 'cad_pesquisa_equipamento');
DELETE FROM paineis   WHERE slug = 'cad_pesquisa_equipamento';
DELETE FROM queries   WHERE slug IN ('cad_equip_dados', 'cad_equip_info', 'cad_equip_obs', 'cad_equip_movimentos') AND empresa_id IS NULL;
DELETE FROM variaveis WHERE slug IN ('var_equipamento_busca', 'var_status_equipamento', 'var_equipamento_selecao');

INSERT INTO variaveis (slug, nome, descricao, tipo, ativo) VALUES
  ('var_equipamento_busca', 'Pesquisar equipamento', 'Código, nome/descrição, placa ou chassi do equipamento', 'text', true);

INSERT INTO variaveis (slug, nome, descricao, tipo, query_fonte, ativo) VALUES (
  'var_status_equipamento', 'Status', 'Situação do cadastro do equipamento', 'select',
  $q$SELECT situacao as valor, descricao as label
FROM (VALUES ('ATIVO', 'Ativo'), ('INATIVO', 'Inativo')) AS t(situacao, descricao)$q$, true);

INSERT INTO variaveis (slug, nome, descricao, tipo, query_fonte, ativo) VALUES (
  'var_equipamento_selecao', 'Equipamento', 'Seleção de um equipamento (prefixo - nome)', 'select',
  $q$select v.veiculo_id as valor, v.prefixo || ' - ' || v.descricao as label
from veiculo v
order by v.prefixo, v.descricao$q$, true);

-- Equipamento selecionado = melhor correspondência da busca (código exato primeiro).
-- O CTE `sel` se repete nas 4 queries: traz o veículo e `qtd` (quantos casaram).

-- ── Dados do equipamento (card perfil) ────────────────────────────────
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id) VALUES (
  'cad_equip_dados', 'Dados do Equipamento', 'Identificação do equipamento pesquisado (imagem do tipo)',
  $q$with sel as (
  select v.*, count(*) over () as qtd
  from veiculo v
  where (nullif(trim($1::text), '') is not null or nullif($4::text, '') is not null)
    and (nullif(trim($1::text), '') is null or v.prefixo ilike '%' || trim($1::text) || '%'
         or v.descricao ilike '%' || trim($1::text) || '%'
         or v.placa ilike '%' || trim($1::text) || '%'
         or v.chassi ilike '%' || trim($1::text) || '%'
         or v.codigo_veiculo::text = trim($1::text))
    and (nullif($2::text, '') is null or v.tip_veic_id = any(string_to_array($2, ',')::bigint[]))
    and (nullif($3::text, '') is null or v.situacao_cadastro = $3)
    and (nullif($4::text, '') is null or v.veiculo_id = nullif($4::text, '')::bigint)
  order by (v.prefixo = trim($1::text) or v.codigo_veiculo::text = trim($1::text)) desc, v.prefixo
  limit 1
)
select coalesce(s.prefixo, s.codigo_veiculo::text) as titulo,
       s.descricao || case when s.qtd > 1 then ' · +' || (s.qtd - 1) || ' outro(s) resultado(s) — refine a busca' else '' end as subtitulo,
       '/api/imagens/tipo-veiculo/' || s.tip_veic_id as imagem_url,
       coalesce(s.codigo_veiculo::text, s.prefixo) as "Código",
       t.descricao as "Tipo",
       ma.descricao as "Marca",
       m.descricao as "Modelo",
       s.situacao_cadastro as "Status"
from sel s
left join tipo_veiculo t on t.tip_veic_id = s.tip_veic_id
left join modelo m on m.modelo_id = s.modelo_id
left join marca ma on ma.marca_id = m.marca_id$q$,
  'card', 120, true, (SELECT id FROM query_grupos WHERE nome = 'Cadastro Equipamento'));

-- ── Informações adicionais (card em modo lista) ───────────────────────
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id) VALUES (
  'cad_equip_info', 'Informações adicionais', 'Ano, placa, chassi, horímetro, propriedade e frente atuais',
  $q$with sel as (
  select v.*
  from veiculo v
  where (nullif(trim($1::text), '') is not null or nullif($4::text, '') is not null)
    and (nullif(trim($1::text), '') is null or v.prefixo ilike '%' || trim($1::text) || '%'
         or v.descricao ilike '%' || trim($1::text) || '%'
         or v.placa ilike '%' || trim($1::text) || '%'
         or v.chassi ilike '%' || trim($1::text) || '%'
         or v.codigo_veiculo::text = trim($1::text))
    and (nullif($2::text, '') is null or v.tip_veic_id = any(string_to_array($2, ',')::bigint[]))
    and (nullif($3::text, '') is null or v.situacao_cadastro = $3)
    and (nullif($4::text, '') is null or v.veiculo_id = nullif($4::text, '')::bigint)
  order by (v.prefixo = trim($1::text) or v.codigo_veiculo::text = trim($1::text)) desc, v.prefixo
  limit 1
)
select s.anofabricacao as "Ano",
       s.placa as "Placa",
       s.chassi as "Chassi",
       case when s.utiliza_horimetro then to_char(s.horimetro_atual, 'FM999G999G990D0') || ' h'
            when s.utiliza_odometro  then to_char(s.odometro_atual, 'FM999G999G990D0') || ' km' end as "Horímetro/Odômetro",
       p.descricao as "Propriedade",
       ft.descricao as "Frente"
from sel s
left join propriedade p on p.propriedade_id = s.propr_atual_id
left join frente_trabalho ft on ft.frente_trabalho_id = s.frent_trab_id$q$,
  'card', 120, true, (SELECT id FROM query_grupos WHERE nome = 'Cadastro Equipamento'));

-- ── Observações (card em modo lista, 1 campo = quadro de nota) ────────
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id) VALUES (
  'cad_equip_obs', 'Observações', 'Observação do cadastro do equipamento',
  $q$with sel as (
  select v.*
  from veiculo v
  where (nullif(trim($1::text), '') is not null or nullif($4::text, '') is not null)
    and (nullif(trim($1::text), '') is null or v.prefixo ilike '%' || trim($1::text) || '%'
         or v.descricao ilike '%' || trim($1::text) || '%'
         or v.placa ilike '%' || trim($1::text) || '%'
         or v.chassi ilike '%' || trim($1::text) || '%'
         or v.codigo_veiculo::text = trim($1::text))
    and (nullif($2::text, '') is null or v.tip_veic_id = any(string_to_array($2, ',')::bigint[]))
    and (nullif($3::text, '') is null or v.situacao_cadastro = $3)
    and (nullif($4::text, '') is null or v.veiculo_id = nullif($4::text, '')::bigint)
  order by (v.prefixo = trim($1::text) or v.codigo_veiculo::text = trim($1::text)) desc, v.prefixo
  limit 1
)
select coalesce(nullif(trim(s.observacao), ''), 'Sem observações.') as "Observações"
from sel s$q$,
  'card', 120, true, (SELECT id FROM query_grupos WHERE nome = 'Cadastro Equipamento'));

-- ── Últimos movimentos (abastecimento + pendência + alocação) ─────────
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id) VALUES (
  'cad_equip_movimentos', 'Últimos Movimentos', 'Últimos 10 abastecimentos, pendências e alocações do equipamento',
  $q$with sel as (
  select v.*
  from veiculo v
  where (nullif(trim($1::text), '') is not null or nullif($4::text, '') is not null)
    and (nullif(trim($1::text), '') is null or v.prefixo ilike '%' || trim($1::text) || '%'
         or v.descricao ilike '%' || trim($1::text) || '%'
         or v.placa ilike '%' || trim($1::text) || '%'
         or v.chassi ilike '%' || trim($1::text) || '%'
         or v.codigo_veiculo::text = trim($1::text))
    and (nullif($2::text, '') is null or v.tip_veic_id = any(string_to_array($2, ',')::bigint[]))
    and (nullif($3::text, '') is null or v.situacao_cadastro = $3)
    and (nullif($4::text, '') is null or v.veiculo_id = nullif($4::text, '')::bigint)
  order by (v.prefixo = trim($1::text) or v.codigo_veiculo::text = trim($1::text)) desc, v.prefixo
  limit 1
),
mov as (
  select a.data_abastecimento as data, 'Abastecimento' as tipo,
         coalesce(a.nome_combustivel, 'Combustível') || ' - ' || trim(to_char(a.qtd, 'FM999G990D0')) || ' L' as descricao,
         ft.descricao as frente, f.nome_funcionario as operador
  from sel s
  join abastecimento a on a.veiculo_id = s.veiculo_id
  left join frente_trabalho ft on ft.frente_trabalho_id = s.frent_trab_id
  left join funcionario f on f.funcionario_id = coalesce(a.funcionario_id, a.operador_id)
  union all
  select pe.data_abertura, 'Pendência',
         coalesce(nullif(trim(pe.descricao), ''), 'Pendência ' || pe.situacao_pendencia),
         ft.descricao, f.nome_funcionario
  from sel s
  join pendencia pe on pe.veiculo_id = s.veiculo_id
  left join frente_trabalho ft on ft.frente_trabalho_id = s.frent_trab_id
  left join funcionario f on f.funcionario_id = pe.usuario_cadastro_id
  union all
  select h.data_inicio, 'Alocação',
         'Alocado' || case when h.data_fim is not null then ' até ' || to_char(h.data_fim, 'DD/MM/YYYY') else ' (em andamento)' end,
         ft.descricao, f.nome_funcionario
  from sel s
  join hist_alocacao h on h.veiculo_id = s.veiculo_id
  left join frente_trabalho ft on ft.frente_trabalho_id = h.frente_trabalho_id
  left join funcionario f on f.funcionario_id = h.funcionario_id
)
select to_char(m.data, 'DD/MM/YYYY HH24:MI') as "Data",
       m.tipo as "Tipo de Movimento",
       m.descricao as "Descrição",
       m.frente as "Frente",
       m.operador as "Operador"
from mov m
order by m.data desc
limit 10$q$,
  'table', 120, true, (SELECT id FROM query_grupos WHERE nome = 'Cadastro Equipamento'));

-- A ordem de inserção define $1, $2, $3 (o runner lê query_parametros ORDER BY id):
-- um INSERT por parâmetro, na ordem busca → tipo → status.
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id)
SELECT q.id, v.slug, 'text', false, v.id
FROM queries q, variaveis v
WHERE q.slug IN ('cad_equip_dados', 'cad_equip_info', 'cad_equip_obs', 'cad_equip_movimentos') AND q.empresa_id IS NULL
  AND v.slug = 'var_equipamento_busca'
ORDER BY q.id;
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id)
SELECT q.id, v.slug, 'text', false, v.id
FROM queries q, variaveis v
WHERE q.slug IN ('cad_equip_dados', 'cad_equip_info', 'cad_equip_obs', 'cad_equip_movimentos') AND q.empresa_id IS NULL
  AND v.slug = 'var_tipo_equipamento'
ORDER BY q.id;
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id)
SELECT q.id, v.slug, 'text', false, v.id
FROM queries q, variaveis v
WHERE q.slug IN ('cad_equip_dados', 'cad_equip_info', 'cad_equip_obs', 'cad_equip_movimentos') AND q.empresa_id IS NULL
  AND v.slug = 'var_status_equipamento'
ORDER BY q.id;
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id)
SELECT q.id, v.slug, 'text', false, v.id
FROM queries q, variaveis v
WHERE q.slug IN ('cad_equip_dados', 'cad_equip_info', 'cad_equip_obs', 'cad_equip_movimentos') AND q.empresa_id IS NULL
  AND v.slug = 'var_equipamento_selecao'
ORDER BY q.id;

INSERT INTO paineis (slug, nome, descricao, icone, colunas, ativo, ordem_menu) VALUES (
  'cad_pesquisa_equipamento', 'Pesquisa de Equipamento',
  'Busque um equipamento pelo código, nome ou descrição e visualize suas informações.', 'search', 3, true, 4);

INSERT INTO painel_indicadores (painel_id, query_slug, titulo, linha, coluna, col_span, row_span, posicao, imprimir)
SELECT p.id, x.slug, x.titulo, x.linha, x.coluna, x.col_span, 1, x.pos, true
FROM paineis p,
     (VALUES ('cad_equip_dados',      'Dados do Equipamento',   1, 1, 2, 1),
             ('cad_equip_info',       'Informações adicionais', 1, 3, 1, 2),
             ('cad_equip_movimentos', 'Últimos Movimentos',     2, 1, 2, 3),
             ('cad_equip_obs',        'Observações',            2, 3, 1, 4)) AS x(slug, titulo, linha, coluna, col_span, pos)
WHERE p.slug = 'cad_pesquisa_equipamento';

INSERT INTO painel_variaveis (painel_id, variavel_id, obrigatorio, posicao)
SELECT p.id, v.id, false, x.pos
FROM paineis p,
     (VALUES ('var_equipamento_selecao', 0), ('var_equipamento_busca', 1), ('var_tipo_equipamento', 2), ('var_status_equipamento', 3)) AS x(slug, pos)
JOIN variaveis v ON v.slug = x.slug
WHERE p.slug = 'cad_pesquisa_equipamento';

-- Acesso: libera para os administradores; vincule os demais usuários pela tela do painel.
INSERT INTO painel_usuarios (painel_id, usuario_id)
SELECT p.id, u.id FROM paineis p, usuarios u WHERE p.slug = 'cad_pesquisa_equipamento' AND u.role = 'admin' AND u.ativo = true;

COMMIT;
