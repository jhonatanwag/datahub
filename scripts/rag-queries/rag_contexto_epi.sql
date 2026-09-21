WITH itens AS (
  SELECT re.req_estoque_id, re.data_entrega, re.func_recebeu_id, re.propriedade_id,
         rei.req_estoque_item_id, rei.qtd_item, rei.tipo_entrega_epi,
         COALESCE(rei.produto_id, pc.produto_id) AS produto_id,
         pc.prod_ca_id, pc.codigo_ca, pc.data_vencimento AS ca_vencimento,
         (pc.data_vencimento < re.data_entrega::date) AS ca_vencido_na_entrega
  FROM req_estoque re
  JOIN req_estoque_item rei ON rei.rec_estoque_id = re.req_estoque_id
  LEFT JOIN produto_ca pc ON pc.prod_ca_id = rei.produto_ca_id
),
por_tipo AS (
  SELECT CASE tipo_entrega_epi
           WHEN 'SUBST_TROCA_POR_PERDA' THEN 'Substituição por perda'
           WHEN 'SUBST_TROCA_POR_DANO' THEN 'Substituição por dano'
           WHEN 'SUBST_TROCA_POR_DESGASTE' THEN 'Substituição por desgaste'
           WHEN 'RECEBIMENTO' THEN 'Recebimento'
           WHEN 'DEVOLUCAO' THEN 'Devolução'
           ELSE COALESCE(tipo_entrega_epi, 'Não informado') END AS tipo_entrega,
         COUNT(*) AS itens, ROUND(SUM(qtd_item), 0) AS qtd_total
  FROM itens GROUP BY tipo_entrega_epi ORDER BY qtd_total DESC NULLS LAST
),
mensal_bruto AS (
  SELECT to_char(data_entrega, 'YYYY-MM') AS mes,
         COUNT(DISTINCT req_estoque_id) AS entregas, COUNT(*) AS itens,
         ROUND(SUM(qtd_item), 0) AS qtd_total, COUNT(DISTINCT func_recebeu_id) AS colaboradores
  FROM itens GROUP BY 1
),
mensal AS (SELECT * FROM mensal_bruto ORDER BY mes DESC LIMIT 12),
por_fazenda AS (
  SELECT COALESCE(p.descricao, 'Sem propriedade') AS propriedade,
         COUNT(DISTINCT i.req_estoque_id) AS entregas, ROUND(SUM(i.qtd_item), 0) AS qtd_total,
         COUNT(DISTINCT i.func_recebeu_id) AS colaboradores
  FROM itens i LEFT JOIN propriedade p ON p.propriedade_id = i.propriedade_id
  GROUP BY p.descricao ORDER BY qtd_total DESC NULLS LAST LIMIT 8
),
top_produto AS (
  SELECT pr.descricao AS produto, ROUND(SUM(i.qtd_item), 0) AS qtd_total,
         COUNT(*) FILTER (WHERE i.tipo_entrega_epi LIKE 'SUBST%') AS itens_de_substituicao
  FROM itens i JOIN produto pr ON pr.produto_id = i.produto_id
  GROUP BY pr.produto_id, pr.descricao ORDER BY qtd_total DESC NULLS LAST LIMIT 10
),
top_colab AS (
  SELECT fu.nome_funcionario AS colaborador, ROUND(SUM(i.qtd_item), 0) AS qtd_total,
         COUNT(DISTINCT i.req_estoque_id) AS entregas,
         COUNT(*) FILTER (WHERE i.tipo_entrega_epi LIKE 'SUBST%') AS itens_de_substituicao
  FROM itens i JOIN funcionario fu ON fu.funcionario_id = i.func_recebeu_id
  GROUP BY fu.funcionario_id, fu.nome_funcionario ORDER BY qtd_total DESC NULLS LAST LIMIT 10
),
ca_problema AS (
  SELECT pc.codigo_ca, pr.descricao AS produto, to_char(pc.data_vencimento, 'YYYY-MM-DD') AS vencimento,
         CASE WHEN pc.data_vencimento < current_date THEN 'VENCIDO' ELSE 'A_VENCER_90_DIAS' END AS situacao
  FROM produto_ca pc JOIN produto pr ON pr.produto_id = pc.produto_id
  WHERE pc.data_vencimento < current_date + 90
  ORDER BY pc.data_vencimento LIMIT 15
),
-- mesma regra do KPI "CA Vencidos" do painel: só a ÚLTIMA entrega de cada produto por colaborador conta
ultimas AS (
  SELECT DISTINCT ON (func_recebeu_id, produto_id) func_recebeu_id, produto_id, ca_vencimento
  FROM itens
  ORDER BY func_recebeu_id, produto_id, data_entrega DESC, req_estoque_item_id DESC
),
entregas_ca_vencido AS (
  SELECT pr.descricao AS produto, COUNT(*) AS itens_entregues_com_ca_vencido
  FROM itens i JOIN produto pr ON pr.produto_id = i.produto_id
  WHERE i.ca_vencido_na_entrega
  GROUP BY pr.produto_id, pr.descricao ORDER BY 2 DESC LIMIT 5
)
SELECT 'epi' AS secao, json_build_object(
  'observacao', 'Entregas de EPI (equipamento de proteção individual) a colaboradores. "Entrega" = um boletim (req_estoque); "item" = uma linha do boletim; qtd_total soma as unidades. resumo_geral, por_tipo_entrega, situacao_ca, por_propriedade, top_produtos e top_colaboradores cobrem TODO o histórico; evolucao_mensal_12m cobre só os últimos 12 meses com entregas (mês ausente = sem entregas). CA = Certificado de Aprovação do EPI, com data de vencimento. Os tipos de entrega "Substituição por perda/dano/desgaste" são trocas; "Recebimento" é a entrega inicial.',
  'resumo_geral', (SELECT json_build_object(
      'total_entregas', COUNT(DISTINCT req_estoque_id),
      'total_itens', COUNT(*),
      'total_unidades', ROUND(COALESCE(SUM(qtd_item), 0), 0),
      'colaboradores_atendidos', COUNT(DISTINCT func_recebeu_id),
      'media_unidades_por_colaborador', ROUND((SUM(qtd_item) / NULLIF(COUNT(DISTINCT func_recebeu_id), 0))::numeric, 2),
      'periodo_inicio', to_char(MIN(data_entrega), 'YYYY-MM-DD'),
      'periodo_fim', to_char(MAX(data_entrega), 'YYYY-MM-DD')
    ) FROM itens),
  'por_tipo_entrega', (SELECT json_agg(por_tipo) FROM por_tipo),
  'evolucao_mensal_12m', (SELECT json_agg(mensal ORDER BY mes) FROM mensal),
  'por_propriedade_top8', (SELECT json_agg(por_fazenda) FROM por_fazenda),
  'top_produtos_entregues_top10', (SELECT json_agg(top_produto) FROM top_produto),
  'colaboradores_que_mais_receberam_top10', (SELECT json_agg(top_colab) FROM top_colab),
  'situacao_ca', (SELECT json_build_object(
      'total_ca_cadastrados', COUNT(*),
      'ca_vencidos', COUNT(*) FILTER (WHERE data_vencimento < current_date),
      'ca_a_vencer_90_dias', COUNT(*) FILTER (WHERE data_vencimento >= current_date AND data_vencimento < current_date + 90),
      'ultimas_entregas_com_ca_vencido', (SELECT COUNT(*) FROM ultimas WHERE ca_vencimento < current_date),
      'itens_entregues_ja_com_ca_vencido_na_data_da_entrega', (SELECT COUNT(*) FROM itens WHERE ca_vencido_na_entrega),
      'ca_vencidos_ou_a_vencer_90d', (SELECT json_agg(ca_problema) FROM ca_problema),
      'produtos_entregues_com_ca_vencido_top5', (SELECT json_agg(entregas_ca_vencido) FROM entregas_ca_vencido)
    ) FROM produto_ca)
) AS dados
