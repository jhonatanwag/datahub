WITH base AS (
  SELECT p.pendencia_id, p.mob_pend_id, p.tipo, p.situacao_pendencia AS situacao,
         p.tipo_prioridade AS prioridade, p.descricao, p.data_abertura, p.data_realizada,
         p.veiculo_id, p.subsistema_id, p.propriedade_id,
         (p.situacao_pendencia <> 'FINALIZADA') AS em_aberto,
         EXTRACT(EPOCH FROM (COALESCE(p.data_realizada, now()) - p.data_abertura)) / 86400.0 AS dias
  FROM pendencia p
),
tipo_sit AS (
  SELECT tipo, situacao, COUNT(*) AS qtd FROM base GROUP BY tipo, situacao ORDER BY tipo, situacao
),
mensal AS (
  SELECT to_char(data_abertura, 'YYYY-MM') AS mes,
         COUNT(*) AS abertas_no_mes,
         COUNT(*) FILTER (WHERE em_aberto) AS ainda_em_aberto
  FROM base
  GROUP BY 1 ORDER BY 1 DESC LIMIT 12
),
resolucao AS (
  SELECT tipo, COUNT(*) AS finalizadas,
         ROUND(AVG(dias)::numeric, 1) AS dias_medio_resolucao
  FROM base WHERE NOT em_aberto GROUP BY tipo ORDER BY tipo
),
por_sistema AS (
  SELECT COALESCE(s.descricao, 'Sem sistema') AS sistema, COUNT(*) AS qtd_em_aberto
  FROM base b
  LEFT JOIN sub_sistema ss ON ss.sub_sistema_id = b.subsistema_id
  LEFT JOIN sistema s ON s.sistema_id = ss.sistema_id
  WHERE b.em_aberto
  GROUP BY 1 ORDER BY 2 DESC LIMIT 10
),
por_frente AS (
  SELECT COALESCE(ft.descricao, 'Sem frente') AS frente, COUNT(*) AS qtd_em_aberto
  FROM base b
  LEFT JOIN LATERAL (
    SELECT h.frente_trabalho_id FROM hist_alocacao h
    WHERE h.veiculo_id = b.veiculo_id AND h.data_inicio <= b.data_abertura
      AND (h.data_fim IS NULL OR h.data_fim >= b.data_abertura)
    ORDER BY h.data_inicio DESC LIMIT 1
  ) h ON true
  LEFT JOIN frente_trabalho ft ON ft.frente_trabalho_id = h.frente_trabalho_id
  WHERE b.em_aberto AND b.tipo = 'PENDENCIA'
  GROUP BY 1 ORDER BY 2 DESC LIMIT 10
),
por_equip AS (
  SELECT COALESCE(v.prefixo, '') || ' - ' || COALESCE(v.descricao, v.placa, '') AS equipamento,
         COUNT(*) FILTER (WHERE b.em_aberto) AS em_aberto,
         COUNT(*) AS total_historico
  FROM base b
  JOIN veiculo v ON v.veiculo_id = b.veiculo_id
  GROUP BY v.prefixo, v.descricao, v.placa
  HAVING COUNT(*) FILTER (WHERE b.em_aberto) > 0
  ORDER BY em_aberto DESC, total_historico DESC LIMIT 15
),
antigas AS (
  SELECT b.mob_pend_id AS id, b.tipo, b.situacao, b.prioridade,
         to_char(b.data_abertura, 'YYYY-MM-DD') AS aberta_em,
         ROUND(b.dias::numeric, 0) AS dias_em_aberto,
         COALESCE(v.prefixo || ' - ' || COALESCE(v.descricao, v.placa, ''), '') AS equipamento,
         LEFT(b.descricao, 70) AS descricao
  FROM base b
  LEFT JOIN veiculo v ON v.veiculo_id = b.veiculo_id
  WHERE b.em_aberto
  ORDER BY b.data_abertura LIMIT 10
),
por_prioridade AS (
  SELECT tipo, COALESCE(prioridade, 'Não informada') AS prioridade,
         COUNT(*) AS total, COUNT(*) FILTER (WHERE em_aberto) AS em_aberto
  FROM base WHERE tipo IN ('SEDE', 'LAVOURA')
  GROUP BY 1, 2 ORDER BY 1, 2
)
SELECT 'pendencias' AS secao, json_build_object(
  'observacao', 'Pendências por tipo: PENDENCIA = equipamento/veículo (maioria), SEDE e LAVOURA = pendências de estrutura/campo. Situações: PENDENTE, AGUARDANDO_MANUTENCAO e PENDENCIA_ACOMPANHADA contam como EM ABERTO; FINALIZADA = concluída. Todo o histórico está em resumo_geral/por_tipo_situacao; evolucao_mensal_12m cobre só os últimos 12 meses COM aberturas (por mês de abertura; mês ausente = nenhuma pendência aberta); rankings de sistema/frente/equipamento consideram só o que está em aberto (top 10/15). "Equipamento" e "veículo" são o mesmo conceito.',
  'resumo_geral', (SELECT json_build_object(
      'total_pendencias', COUNT(*),
      'em_aberto', COUNT(*) FILTER (WHERE em_aberto),
      'finalizadas', COUNT(*) FILTER (WHERE NOT em_aberto),
      'periodo_inicio', to_char(MIN(data_abertura), 'YYYY-MM-DD'),
      'periodo_fim', to_char(MAX(data_abertura), 'YYYY-MM-DD')
    ) FROM base),
  'por_tipo_situacao', (SELECT json_agg(tipo_sit) FROM tipo_sit),
  'tempo_resolucao_por_tipo', (SELECT json_agg(resolucao) FROM resolucao),
  'evolucao_mensal_12m', (SELECT json_agg(mensal ORDER BY mes) FROM mensal),
  'por_prioridade_sede_lavoura', (SELECT json_agg(por_prioridade) FROM por_prioridade),
  'em_aberto_por_sistema_top10', (SELECT json_agg(por_sistema) FROM por_sistema),
  'em_aberto_por_frente_top10', (SELECT json_agg(por_frente) FROM por_frente),
  'equipamentos_com_mais_pendencias_em_aberto_top15', (SELECT json_agg(por_equip) FROM por_equip),
  'mais_antigas_em_aberto_top10', (SELECT json_agg(antigas) FROM antigas)
) AS dados
