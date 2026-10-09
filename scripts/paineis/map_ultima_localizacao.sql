-- Painel "Última Localização dos Equipamentos" (map_ultima_localizacao) — rodar no datahub_meta.
-- Idempotente: reexecutar apaga e recria o painel/query NOVOS deste script.
-- Mostra, num mapa, a última posição conhecida de cada equipamento ATIVO, com a FOTO do tipo de
-- equipamento como marcador (coluna `tip_veic_id` → /api/imagens/tipo-veiculo/{id}).
-- A posição vem de eventos lançados pelo app móvel (não há rastreamento GPS): vale a de DATA MAIS RECENTE entre
--   Pendência (data_abertura), Abastecimento (data_abastecimento) e Perda (perda_lancamento.data_cadastro).
-- Requer: MapPanel com suporte a `tip_veic_id`/`detalhe` e as variáveis existentes
--   var_tipo_equipamento ($1), var_equipamento ($2) e var_fazenda ($3 — propriedade atual do equipamento).
BEGIN;

DO $$
BEGIN
  IF (SELECT count(*) FROM variaveis WHERE slug IN ('var_tipo_equipamento', 'var_equipamento', 'var_fazenda')) < 3 THEN
    RAISE EXCEPTION 'Faltam variáveis: este painel usa var_tipo_equipamento, var_equipamento e var_fazenda.';
  END IF;
END $$;

DELETE FROM painel_indicadores WHERE painel_id IN (SELECT id FROM paineis WHERE slug = 'map_ultima_localizacao');
DELETE FROM painel_variaveis   WHERE painel_id IN (SELECT id FROM paineis WHERE slug = 'map_ultima_localizacao');
DELETE FROM painel_usuarios    WHERE painel_id IN (SELECT id FROM paineis WHERE slug = 'map_ultima_localizacao');
DELETE FROM paineis WHERE slug = 'map_ultima_localizacao';
DELETE FROM queries WHERE slug = 'map_ultima_localizacao_equip' AND empresa_id IS NULL;

INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, mapa_camada, cache_ttl, ativo, grupo_id) VALUES (
  'map_ultima_localizacao_equip', 'Última localização por equipamento',
  'Última posição de cada equipamento (pendência, abastecimento ou perda — vale a mais recente), com a foto do tipo',
  $q$with posicoes as (
  select p.veiculo_id, p.pos_latitude as lat, p.pos_longitude as lng,
         coalesce(p.data_abertura, p.data_cadastro) as quando, 'Pendência' as fonte
  from pendencia p
  where p.veiculo_id is not null and p.pos_latitude is not null and p.pos_longitude is not null
  union all
  select a.veiculo_id, a.pos_latitude, a.pos_longitude, a.data_abastecimento, 'Abastecimento'
  from abastecimento a
  where a.veiculo_id is not null and a.pos_latitude is not null and a.pos_longitude is not null
  union all
  select pe.veiculo_id, pl.pos_latitude, pl.pos_longitude, coalesce(pl.data_cadastro, pe.data_cadastro), 'Perda'
  from perda_lancamento pl
  join perda pe on pe.perda_id = pl.perda_id
  where pe.veiculo_id is not null and pl.pos_latitude is not null and pl.pos_longitude is not null
),
ultima as (
  select distinct on (veiculo_id) veiculo_id, lat, lng, quando, fonte
  from posicoes
  where quando is not null
  order by veiculo_id, quando desc
)
select u.lat as lat,
       u.lng as lng,
       v.prefixo || ' - ' || v.descricao as label,
       case when current_date - u.quando::date <= 0 then 'hoje'
            when current_date - u.quando::date = 1 then 'há 1 dia'
            else 'há ' || (current_date - u.quando::date) || ' dias' end as valor,
       v.tip_veic_id as tip_veic_id,
       u.fonte || ' em ' || to_char(u.quando, 'DD/MM/YYYY HH24:MI')
         || coalesce(' · ' || t.descricao, '') as detalhe
from ultima u
join veiculo v on v.veiculo_id = u.veiculo_id
left join tipo_veiculo t on t.tip_veic_id = v.tip_veic_id
where v.situacao_cadastro = 'ATIVO'
  and (nullif($1::text, '') is null or v.tip_veic_id  = any(string_to_array($1, ',')::bigint[]))
  and (nullif($2::text, '') is null or v.veiculo_id   = any(string_to_array($2, ',')::bigint[]))
  and (nullif($3::text, '') is null or v.propr_atual_id = any(string_to_array($3, ',')::bigint[]))
order by u.quando desc
$q$,
  'map', 'satelite', 300, true, (SELECT id FROM query_grupos WHERE nome = 'Cadastro Equipamento'));

-- Parâmetros na ordem $1,$2,$3 (o runner usa ORDER BY id).
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id)
SELECT q.id, v.slug, 'text', false, v.id
FROM queries q, variaveis v
WHERE q.slug = 'map_ultima_localizacao_equip' AND q.empresa_id IS NULL AND v.slug = 'var_tipo_equipamento';
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id)
SELECT q.id, v.slug, 'text', false, v.id
FROM queries q, variaveis v
WHERE q.slug = 'map_ultima_localizacao_equip' AND q.empresa_id IS NULL AND v.slug = 'var_equipamento';
INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id)
SELECT q.id, v.slug, 'text', false, v.id
FROM queries q, variaveis v
WHERE q.slug = 'map_ultima_localizacao_equip' AND q.empresa_id IS NULL AND v.slug = 'var_fazenda';

INSERT INTO paineis (slug, nome, descricao, icone, colunas, ativo, ordem_menu) VALUES (
  'map_ultima_localizacao', 'Última Localização dos Equipamentos',
  'Mapa com a última posição conhecida de cada equipamento, identificado pela foto do tipo.', 'map', 1, true, 5);

-- row_span 2 = mapa com o dobro da altura padrão (600 px).
INSERT INTO painel_indicadores (painel_id, query_slug, titulo, linha, coluna, col_span, row_span, posicao, imprimir)
SELECT p.id, 'map_ultima_localizacao_equip', 'Última localização por equipamento', 1, 1, 1, 2, 0, true
FROM paineis p WHERE p.slug = 'map_ultima_localizacao';

INSERT INTO painel_variaveis (painel_id, variavel_id, obrigatorio, posicao)
SELECT p.id, v.id, false, x.pos
FROM paineis p,
     (VALUES ('var_fazenda', 0), ('var_tipo_equipamento', 1), ('var_equipamento', 2)) AS x(slug, pos)
JOIN variaveis v ON v.slug = x.slug
WHERE p.slug = 'map_ultima_localizacao';

-- Acesso: libera para os administradores; vincule os demais usuários pela tela do painel.
INSERT INTO painel_usuarios (painel_id, usuario_id)
SELECT p.id, u.id FROM paineis p, usuarios u WHERE p.slug = 'map_ultima_localizacao' AND u.role = 'admin' AND u.ativo = true;

COMMIT;
