WITH lanc AS (
  SELECT lf.lancamentoficha_id, lf.data_cadastro, lf.nota_final, lf.propriedade_id,
         lf.veiculo_id1 AS veiculo_id, lf.operador_id, f.ficha_id, f.descricao AS ficha, f.tipo_ficha
  FROM lancamento_ficha lf
  JOIN ficha f ON f.ficha_id = lf.ficha_id
),
-- respostas só dos últimos 12 meses (calendário) — o histórico inteiro tem ~900 mil linhas
resp AS (
  SELECT l.*, rf.descricao AS resposta, rf.nao_se_aplica, pf.pergunta_id
  FROM lanc l
  JOIN respostas_ficha rf ON rf.lancamento_ficha_id = l.lancamentoficha_id
  JOIN perguntas_ficha pf ON pf.perguntas_ficha_id = rf.perguntas_ficha_id
  WHERE l.data_cadastro >= date_trunc('month', now()) - interval '11 months'
),
por_tipo AS (
  SELECT tipo_ficha, COUNT(*) AS lancamentos, COUNT(DISTINCT ficha_id) AS fichas_distintas,
         ROUND(AVG(nota_final) FILTER (WHERE tipo_ficha <> 'ROTINA')::numeric, 1) AS nota_media,
         to_char(MIN(data_cadastro), 'YYYY-MM-DD') AS primeiro_lancamento,
         to_char(MAX(data_cadastro), 'YYYY-MM-DD') AS ultimo_lancamento
  FROM lanc GROUP BY tipo_ficha ORDER BY tipo_ficha
),
resp_tipo AS (
  SELECT tipo_ficha,
         COUNT(*) FILTER (WHERE resposta = 'SIM') AS respostas_sim,
         COUNT(*) FILTER (WHERE resposta = 'NAO') AS respostas_nao,
         ROUND(100.0 * COUNT(*) FILTER (WHERE resposta = 'NAO') / NULLIF(COUNT(*),0), 2) AS pct_nao
  FROM resp GROUP BY tipo_ficha ORDER BY tipo_ficha
),
mensal AS (
  SELECT to_char(l.data_cadastro, 'YYYY-MM') AS mes,
         COUNT(*) FILTER (WHERE l.tipo_ficha = 'ROTINA') AS rotina,
         COUNT(*) FILTER (WHERE l.tipo_ficha = 'AUDITORIA') AS auditoria,
         COUNT(*) FILTER (WHERE l.tipo_ficha = 'PREVENTIVA') AS preventiva,
         ROUND(AVG(l.nota_final) FILTER (WHERE l.tipo_ficha = 'AUDITORIA')::numeric, 1) AS nota_media_auditoria,
         ROUND(AVG(l.nota_final) FILTER (WHERE l.tipo_ficha = 'PREVENTIVA')::numeric, 1) AS nota_media_preventiva
  FROM lanc l
  WHERE l.data_cadastro >= date_trunc('month', now()) - interval '11 months'
  GROUP BY 1
),
nao_mensal AS (
  SELECT to_char(data_cadastro, 'YYYY-MM') AS mes, COUNT(*) AS respostas_nao
  FROM resp WHERE resposta = 'NAO' GROUP BY 1
),
evolucao AS (
  SELECT m.*, COALESCE(n.respostas_nao, 0) AS respostas_nao
  FROM mensal m LEFT JOIN nao_mensal n USING (mes)
),
top_pergunta AS (
  SELECT LEFT(p.descricao, 90) AS pergunta, MIN(r.ficha) AS ficha_exemplo, COUNT(*) AS qtd_nao
  FROM resp r JOIN pergunta p ON p.pergunta_id = r.pergunta_id
  WHERE r.resposta = 'NAO'
  GROUP BY p.pergunta_id, p.descricao ORDER BY qtd_nao DESC LIMIT 15
),
top_equip AS (
  SELECT COALESCE(v.prefixo, '') || ' - ' || COALESCE(v.descricao, v.placa, '') AS equipamento, COUNT(*) AS qtd_nao
  FROM resp r JOIN veiculo v ON v.veiculo_id = r.veiculo_id
  WHERE r.resposta = 'NAO'
  GROUP BY v.prefixo, v.descricao, v.placa ORDER BY qtd_nao DESC LIMIT 10
),
top_operador AS (
  SELECT fu.nome_funcionario AS operador, COUNT(*) AS qtd_nao
  FROM resp r JOIN funcionario fu ON fu.funcionario_id = r.operador_id
  WHERE r.resposta = 'NAO'
  GROUP BY fu.funcionario_id, fu.nome_funcionario ORDER BY qtd_nao DESC LIMIT 10
),
por_fazenda AS (
  SELECT COALESCE(p.descricao, 'Sem propriedade') AS propriedade,
         COUNT(DISTINCT r.lancamentoficha_id) AS lancamentos, COUNT(*) FILTER (WHERE r.resposta = 'NAO') AS qtd_nao
  FROM resp r LEFT JOIN propriedade p ON p.propriedade_id = r.propriedade_id
  GROUP BY p.descricao ORDER BY qtd_nao DESC LIMIT 8
),
por_ficha AS (
  SELECT ficha, tipo_ficha, COUNT(*) AS lancamentos, ROUND(AVG(nota_final) FILTER (WHERE tipo_ficha <> 'ROTINA')::numeric, 1) AS nota_media
  FROM lanc WHERE data_cadastro >= date_trunc('month', now()) - interval '11 months'
  GROUP BY ficha, tipo_ficha ORDER BY lancamentos DESC LIMIT 12
)
SELECT 'inspecoes' AS secao, json_build_object(
  'observacao', 'Inspeções = lançamentos de fichas (checklists) de 3 tipos: ROTINA (checklist diário do operador, sem nota), AUDITORIA e PREVENTIVA (com nota_final). "Irregularidade"/"negativa" = resposta NAO a uma pergunta da ficha. por_tipo_ficha_historico_completo cobre TODO o histórico; todo o resto (evolução mensal, respostas SIM/NAO, rankings de perguntas, equipamentos, operadores, propriedades e fichas) cobre só os últimos 12 meses do calendário (mês ausente = sem lançamentos). Nota média só faz sentido para AUDITORIA/PREVENTIVA; em ROTINA use qtd/percentual de respostas NAO. "Equipamento" e "veículo" são o mesmo conceito.',
  'por_tipo_ficha_historico_completo', (SELECT json_agg(por_tipo) FROM por_tipo),
  'respostas_12m_por_tipo', (SELECT json_agg(resp_tipo) FROM resp_tipo),
  'evolucao_mensal_12m', (SELECT json_agg(evolucao ORDER BY mes) FROM evolucao),
  'perguntas_com_mais_nao_12m_top15', (SELECT json_agg(top_pergunta) FROM top_pergunta),
  'equipamentos_com_mais_nao_12m_top10', (SELECT json_agg(top_equip) FROM top_equip),
  'operadores_com_mais_nao_12m_top10', (SELECT json_agg(top_operador) FROM top_operador),
  'propriedades_12m_top8', (SELECT json_agg(por_fazenda) FROM por_fazenda),
  'fichas_mais_lancadas_12m_top12', (SELECT json_agg(por_ficha) FROM por_ficha)
) AS dados
