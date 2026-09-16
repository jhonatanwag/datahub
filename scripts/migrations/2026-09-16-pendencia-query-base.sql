-- Migração piloto: grupo Pendência para query_base_id (Fase 1)
-- Ver docs/superpowers/plans/2026-09-16-query-base-reaproveitamento.md (Task 6)
-- Registrado como referência — não roda automaticamente.

\set ON_ERROR_STOP on
BEGIN;

INSERT INTO queries (slug, nome, tipo, cache_ttl, ativo, grupo_id, sql_texto)
SELECT 'pen_pendencias_base_pendencia', 'Base — Pendências (PENDENCIA)', 'table', 300, true,
       (SELECT grupo_id FROM queries WHERE slug = 'pen_pendencias_lancamentos'),
$sql$
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
and tipo = 'PENDENCIA'
$sql$
RETURNING id AS base_pendencia_id \gset

INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, param_slot)
SELECT :base_pendencia_id, nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, param_slot
FROM query_parametros WHERE query_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_lancamentos');

-- SEDE: mesmo SQL, só o literal final muda
INSERT INTO queries (slug, nome, tipo, cache_ttl, ativo, grupo_id, sql_texto)
SELECT 'pen_pendencias_base_sede', 'Base — Pendências (SEDE)', 'table', 300, true,
       (SELECT grupo_id FROM queries WHERE slug = 'pen_pendencias_lancamentos_sede'),
       replace(sql_texto, $$tipo = 'PENDENCIA'$$, $$tipo = 'SEDE'$$)
FROM queries WHERE slug = 'pen_pendencias_base_pendencia'
RETURNING id AS base_sede_id \gset

INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, param_slot)
SELECT :base_sede_id, nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, param_slot
FROM query_parametros WHERE query_id = :base_pendencia_id;

-- LAVOURA: idem
INSERT INTO queries (slug, nome, tipo, cache_ttl, ativo, grupo_id, sql_texto)
SELECT 'pen_pendencias_base_lavoura', 'Base — Pendências (LAVOURA)', 'table', 300, true,
       (SELECT grupo_id FROM queries WHERE slug = 'pen_pendencias_lancamentos_lavoura'),
       replace(sql_texto, $$tipo = 'PENDENCIA'$$, $$tipo = 'LAVOURA'$$)
FROM queries WHERE slug = 'pen_pendencias_base_pendencia'
RETURNING id AS base_lavoura_id \gset

INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, param_slot)
SELECT :base_lavoura_id, nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, param_slot
FROM query_parametros WHERE query_id = :base_pendencia_id;

COMMIT;
SELECT :base_pendencia_id AS base_pendencia_id, :base_sede_id AS base_sede_id, :base_lavoura_id AS base_lavoura_id;

\set ON_ERROR_STOP on
BEGIN;

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) || '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'PENDENTE'$$
WHERE slug = 'pen_pendencias_pendente_equip';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) || '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'AGUARDANDO_MANUTENCAO'$$
WHERE slug = 'pen_pendencias_aguar_manut_equip';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) || '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'FINALIZADA'$$
WHERE slug = 'pen_pendencias_finalizadas_equip';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT frente_trabalho_id AS id, frente_trabalho_descricao AS label,
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'PENDENTE') AS valor,
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'PENDENCIA_ACOMPANHADA') AS "Pend. Acompanhada",
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'AGUARDANDO_MANUTENCAO') AS "Aguard. Manutenção",
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'FINALIZADA') AS "Finalizada"
    FROM base GROUP BY frente_trabalho_id, frente_trabalho_descricao$$
WHERE slug = 'pen_pendencias_por_frente';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT situacao_pendencia,
    CASE WHEN situacao_pendencia = 'PENDENCIA_ACOMPANHADA' THEN 'PEND. ACOMPANHADA'
         WHEN situacao_pendencia = 'AGUARDANDO_MANUTENCAO' THEN 'AGUARD. MANUTENÇÃO'
         ELSE situacao_pendencia END AS label,
    ROUND(COUNT(DISTINCT pendencia_id) * 100.0 / SUM(COUNT(DISTINCT pendencia_id)) OVER (), 2) AS valor
    FROM base GROUP BY situacao_pendencia
    ORDER BY CASE situacao_pendencia
      WHEN 'PENDENTE' THEN 1 WHEN 'PENDENCIA_ACOMPANHADA' THEN 2
      WHEN 'AGUARDANDO_MANUTENCAO' THEN 3 WHEN 'FINALIZADA' THEN 4 ELSE 99 END$$
WHERE slug = 'pen_pendencias_percentual_sit';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT sistema_id, sistema_descricao AS label, count(distinct pendencia_id) AS valor
    FROM base WHERE situacao_pendencia = 'PENDENTE' GROUP BY sistema_id, sistema_descricao ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_sistemas_em_aberto';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT tip_veic_id, "Tipo Veiculo" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY tip_veic_id, "Tipo Veiculo" ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_tipo_equip';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT marca_id, "Marca" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY marca_id, "Marca" ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_tipo_marca';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT modelo_id, "Modelo" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY modelo_id, "Modelo" ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_tipo_modelo';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_pendencia'),
  sql_texto = $$SELECT "ID", "Descrição Pendência", "Tipo Veiculo", "Modelo", "Marca", placa, prefixo, "Horas Pendente", "Horas Aguard. Autorização", "Horas Aguard. Manutenção" FROM base$$
WHERE slug = 'pen_pendencias_lancamentos';

DELETE FROM query_parametros WHERE query_id IN (
  SELECT id FROM queries WHERE slug IN (
    'pen_pendencias_pendente_equip', 'pen_pendencias_aguar_manut_equip', 'pen_pendencias_finalizadas_equip',
    'pen_pendencias_por_frente', 'pen_pendencias_percentual_sit', 'pen_pendencias_por_sistemas_em_aberto',
    'pen_pendencias_por_tipo_equip', 'pen_pendencias_por_tipo_marca', 'pen_pendencias_por_tipo_modelo',
    'pen_pendencias_lancamentos'
  )
);

COMMIT;

\set ON_ERROR_STOP on
BEGIN;

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_sede'),
  sql_texto = $$SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) || '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'PENDENTE'$$
WHERE slug = 'pen_pendencias_pendente_equip_sede';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_sede'),
  sql_texto = $$SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) || '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'AGUARDANDO_MANUTENCAO'$$
WHERE slug = 'pen_pendencias_aguar_manut_equip_sede';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_sede'),
  sql_texto = $$SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) || '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'FINALIZADA'$$
WHERE slug = 'pen_pendencias_finalizadas_equip_sede';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_sede'),
  sql_texto = $$SELECT frente_trabalho_id AS id, frente_trabalho_descricao AS label,
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'PENDENTE') AS valor,
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'PENDENCIA_ACOMPANHADA') AS "Pend. Acompanhada",
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'AGUARDANDO_MANUTENCAO') AS "Aguard. Manutenção",
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'FINALIZADA') AS "Finalizada"
    FROM base GROUP BY frente_trabalho_id, frente_trabalho_descricao$$
WHERE slug = 'pen_pendencias_por_frente_sede';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_sede'),
  sql_texto = $$SELECT situacao_pendencia,
    CASE WHEN situacao_pendencia = 'PENDENCIA_ACOMPANHADA' THEN 'PEND. ACOMPANHADA'
         WHEN situacao_pendencia = 'AGUARDANDO_MANUTENCAO' THEN 'AGUARD. MANUTENÇÃO'
         ELSE situacao_pendencia END AS label,
    ROUND(COUNT(DISTINCT pendencia_id) * 100.0 / SUM(COUNT(DISTINCT pendencia_id)) OVER (), 2) AS valor
    FROM base GROUP BY situacao_pendencia
    ORDER BY CASE situacao_pendencia
      WHEN 'PENDENTE' THEN 1 WHEN 'PENDENCIA_ACOMPANHADA' THEN 2
      WHEN 'AGUARDANDO_MANUTENCAO' THEN 3 WHEN 'FINALIZADA' THEN 4 ELSE 99 END$$
WHERE slug = 'pen_pendencias_percentual_sit_sede';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_sede'),
  sql_texto = $$SELECT sistema_id, sistema_descricao AS label, count(distinct pendencia_id) AS valor
    FROM base WHERE situacao_pendencia = 'PENDENTE' GROUP BY sistema_id, sistema_descricao ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_sistemas_em_aberto_sede';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_sede'),
  sql_texto = $$SELECT tip_veic_id, "Tipo Veiculo" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY tip_veic_id, "Tipo Veiculo" ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_tipo_equip_sede';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_sede'),
  sql_texto = $$SELECT marca_id, "Marca" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY marca_id, "Marca" ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_tipo_marca_sede';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_sede'),
  sql_texto = $$SELECT modelo_id, "Modelo" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY modelo_id, "Modelo" ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_tipo_modelo_sede';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_sede'),
  sql_texto = $$SELECT "ID", "Descrição Pendência", "Tipo Veiculo", "Modelo", "Marca", placa, prefixo, "Horas Pendente", "Horas Aguard. Autorização", "Horas Aguard. Manutenção" FROM base$$
WHERE slug = 'pen_pendencias_lancamentos_sede';

DELETE FROM query_parametros WHERE query_id IN (
  SELECT id FROM queries WHERE slug IN (
    'pen_pendencias_pendente_equip_sede', 'pen_pendencias_aguar_manut_equip_sede', 'pen_pendencias_finalizadas_equip_sede',
    'pen_pendencias_por_frente_sede', 'pen_pendencias_percentual_sit_sede', 'pen_pendencias_por_sistemas_em_aberto_sede',
    'pen_pendencias_por_tipo_equip_sede', 'pen_pendencias_por_tipo_marca_sede', 'pen_pendencias_por_tipo_modelo_sede',
    'pen_pendencias_lancamentos_sede'
  )
);

COMMIT;

\set ON_ERROR_STOP on
BEGIN;

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_sede'),
  sql_texto = $$SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) || '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'PENDENTE'$$
WHERE slug = 'pen_pendencias_pendente_sede';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_sede'),
  sql_texto = $$SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) || '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'AGUARDANDO_MANUTENCAO'$$
WHERE slug = 'pen_pendencias_aguar_manut_sede';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_sede'),
  sql_texto = $$SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) || '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'FINALIZADA'$$
WHERE slug = 'pen_pendencias_finalizadas_sede';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_sede'),
  sql_texto = $$SELECT tip_veic_id, "Tipo Veiculo" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY tip_veic_id, "Tipo Veiculo" ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_tipo_sede';

DELETE FROM query_parametros WHERE query_id IN (
  SELECT id FROM queries WHERE slug IN (
    'pen_pendencias_pendente_sede', 'pen_pendencias_aguar_manut_sede',
    'pen_pendencias_finalizadas_sede', 'pen_pendencias_por_tipo_sede'
  )
);

COMMIT;

\set ON_ERROR_STOP on
BEGIN;

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_lavoura'),
  sql_texto = $$SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) || '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'PENDENTE'$$
WHERE slug = 'pen_pendencias_pendente_lavoura';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_lavoura'),
  sql_texto = $$SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) || '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'AGUARDANDO_MANUTENCAO'$$
WHERE slug = 'pen_pendencias_aguar_manut_lavoura';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_lavoura'),
  sql_texto = $$SELECT count(distinct pendencia_id) AS valor, count(distinct veiculo_id) || '  Veículos diferentes' AS label FROM base WHERE situacao_pendencia = 'FINALIZADA'$$
WHERE slug = 'pen_pendencias_finalizadas_lavoura';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_lavoura'),
  sql_texto = $$SELECT frente_trabalho_id AS id, frente_trabalho_descricao AS label,
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'PENDENTE') AS valor,
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'PENDENCIA_ACOMPANHADA') AS "Pend. Acompanhada",
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'AGUARDANDO_MANUTENCAO') AS "Aguard. Manutenção",
    count(distinct pendencia_id) FILTER (WHERE situacao_pendencia = 'FINALIZADA') AS "Finalizada"
    FROM base GROUP BY frente_trabalho_id, frente_trabalho_descricao$$
WHERE slug = 'pen_pendencias_por_frente_lavoura';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_lavoura'),
  sql_texto = $$SELECT situacao_pendencia,
    CASE WHEN situacao_pendencia = 'PENDENCIA_ACOMPANHADA' THEN 'PEND. ACOMPANHADA'
         WHEN situacao_pendencia = 'AGUARDANDO_MANUTENCAO' THEN 'AGUARD. MANUTENÇÃO'
         ELSE situacao_pendencia END AS label,
    ROUND(COUNT(DISTINCT pendencia_id) * 100.0 / SUM(COUNT(DISTINCT pendencia_id)) OVER (), 2) AS valor
    FROM base GROUP BY situacao_pendencia
    ORDER BY CASE situacao_pendencia
      WHEN 'PENDENTE' THEN 1 WHEN 'PENDENCIA_ACOMPANHADA' THEN 2
      WHEN 'AGUARDANDO_MANUTENCAO' THEN 3 WHEN 'FINALIZADA' THEN 4 ELSE 99 END$$
WHERE slug = 'pen_pendencias_percentual_sit_lavoura';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_lavoura'),
  sql_texto = $$SELECT sistema_id, sistema_descricao AS label, count(distinct pendencia_id) AS valor
    FROM base WHERE situacao_pendencia = 'PENDENTE' GROUP BY sistema_id, sistema_descricao ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_sistemas_em_aberto_lavoura';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_lavoura'),
  sql_texto = $$SELECT tip_veic_id, "Tipo Veiculo" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY tip_veic_id, "Tipo Veiculo" ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_tipo_lavoura';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_lavoura'),
  sql_texto = $$SELECT marca_id, "Marca" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY marca_id, "Marca" ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_tipo_marca_lavoura';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_lavoura'),
  sql_texto = $$SELECT modelo_id, "Modelo" AS label, count(distinct pendencia_id) AS valor FROM base GROUP BY modelo_id, "Modelo" ORDER BY 3$$
WHERE slug = 'pen_pendencias_por_tipo_modelo_lavoura';

UPDATE queries SET
  query_base_id = (SELECT id FROM queries WHERE slug = 'pen_pendencias_base_lavoura'),
  sql_texto = $$SELECT "ID", "Descrição Pendência", "Tipo Veiculo", "Modelo", "Marca", placa, prefixo, "Horas Pendente", "Horas Aguard. Autorização", "Horas Aguard. Manutenção" FROM base$$
WHERE slug = 'pen_pendencias_lancamentos_lavoura';

DELETE FROM query_parametros WHERE query_id IN (
  SELECT id FROM queries WHERE slug IN (
    'pen_pendencias_pendente_lavoura', 'pen_pendencias_aguar_manut_lavoura', 'pen_pendencias_finalizadas_lavoura',
    'pen_pendencias_por_frente_lavoura', 'pen_pendencias_percentual_sit_lavoura', 'pen_pendencias_por_sistemas_em_aberto_lavoura',
    'pen_pendencias_por_tipo_lavoura', 'pen_pendencias_por_tipo_marca_lavoura', 'pen_pendencias_por_tipo_modelo_lavoura',
    'pen_pendencias_lancamentos_lavoura'
  )
);

COMMIT;
