WITH base AS (
  SELECT p.perda_id, pl.perda_lancamento_id, p.data_cadastro,
         pl.resultado, COALESCE(mp.sub_titulo, 'Sem unidade') AS unidade,
         o.nome AS operacao, pr.descricao AS propriedade, t.descricao AS talhao,
         fu.nome_funcionario AS operador,
         CASE WHEN v.veiculo_id IS NULL THEN NULL
              ELSE COALESCE(v.prefixo, '') || ' - ' || COALESCE(v.descricao, v.placa, '') END AS equipamento
  FROM perda p
  JOIN perda_lancamento pl ON pl.perda_id = p.perda_id
  LEFT JOIN metodo_perda mp ON mp.metodo_perda_id = p.metodo_perda_id
  LEFT JOIN operacao o ON o.operacao_id = p.operacao_id
  LEFT JOIN propriedade pr ON pr.propriedade_id = p.propriedade_id
  LEFT JOIN talhao t ON t.talhao_id = pl.talhao_id
  LEFT JOIN funcionario fu ON fu.funcionario_id = p.funcionario_id
  LEFT JOIN veiculo v ON v.veiculo_id = p.veiculo_id
),
por_unidade AS (
  SELECT unidade, COUNT(DISTINCT perda_id) AS perdas, COUNT(*) AS amostras,
         ROUND(AVG(resultado)::numeric, 2) AS media,
         ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY resultado))::numeric, 2) AS mediana,
         ROUND(MIN(resultado)::numeric, 2) AS minimo, ROUND(MAX(resultado)::numeric, 2) AS maximo,
         to_char(MIN(data_cadastro), 'YYYY-MM-DD') AS primeira, to_char(MAX(data_cadastro), 'YYYY-MM-DD') AS ultima
  FROM base GROUP BY unidade ORDER BY unidade
),
por_operacao AS (
  SELECT operacao, unidade, COUNT(*) AS amostras, ROUND(AVG(resultado)::numeric, 2) AS media,
         ROUND(MAX(resultado)::numeric, 2) AS maximo
  FROM base GROUP BY operacao, unidade ORDER BY unidade, media DESC
),
mensal AS (
  SELECT to_char(data_cadastro, 'YYYY-MM') AS mes, unidade, COUNT(*) AS amostras,
         ROUND(AVG(resultado)::numeric, 2) AS media
  FROM base GROUP BY 1, 2 ORDER BY 1 DESC, 2 LIMIT 24
),
rk_fazenda AS (
  SELECT unidade, propriedade, COUNT(*) AS amostras, ROUND(AVG(resultado)::numeric, 2) AS media,
         ROW_NUMBER() OVER (PARTITION BY unidade ORDER BY AVG(resultado) DESC) AS rn
  FROM base GROUP BY unidade, propriedade
),
rk_operador AS (
  SELECT unidade, operador, COUNT(*) AS amostras, ROUND(AVG(resultado)::numeric, 2) AS media,
         ROW_NUMBER() OVER (PARTITION BY unidade ORDER BY AVG(resultado) DESC) AS rn
  FROM base GROUP BY unidade, operador
),
rk_talhao AS (
  SELECT unidade, talhao, propriedade, COUNT(*) AS amostras, ROUND(AVG(resultado)::numeric, 2) AS media,
         ROW_NUMBER() OVER (PARTITION BY unidade ORDER BY AVG(resultado) DESC) AS rn
  FROM base GROUP BY unidade, talhao, propriedade
),
rk_equip AS (
  SELECT unidade, equipamento, COUNT(*) AS amostras, ROUND(AVG(resultado)::numeric, 2) AS media,
         ROW_NUMBER() OVER (PARTITION BY unidade ORDER BY AVG(resultado) DESC) AS rn
  FROM base WHERE equipamento IS NOT NULL GROUP BY unidade, equipamento
),
maiores AS (
  SELECT unidade, resultado, data, operacao, propriedade, talhao, operador, equipamento FROM (
    SELECT unidade, ROUND(resultado::numeric, 2) AS resultado, to_char(data_cadastro, 'YYYY-MM-DD') AS data,
           operacao, propriedade, talhao, operador, equipamento,
           ROW_NUMBER() OVER (PARTITION BY unidade ORDER BY resultado DESC) AS rn
    FROM base
  ) x WHERE rn <= 5
)
SELECT 'perdas' AS secao, json_build_object(
  'observacao', 'Perdas de colheita medidas em campo. Cada "amostra" é um lançamento de perda (resultado) num talhão. ATENÇÃO: o resultado tem UNIDADES DIFERENTES conforme o método — "PERDAS SACAS/HA" (soja, sorgo, feijão) e "@/HA" (algodão) — então NUNCA some nem compare valores de unidades diferentes; todos os rankings abaixo vêm separados por unidade e ordenados da MAIOR para a menor média de perda. O histórico inteiro está aqui (dados só a partir de mai/2026), sem corte por período. Os valores de @/HA têm outliers muito altos, por isso a mediana é informada além da média. "Equipamento" e "veículo" são o mesmo conceito; equipamento pode faltar em algumas perdas.',
  'resumo_geral', (SELECT json_build_object(
      'perdas_com_amostras', COUNT(DISTINCT perda_id),
      'total_amostras', COUNT(*),
      'operadores_distintos', COUNT(DISTINCT operador),
      'propriedades_distintas', COUNT(DISTINCT propriedade),
      'talhoes_distintos', COUNT(DISTINCT talhao),
      'periodo_inicio', to_char(MIN(data_cadastro), 'YYYY-MM-DD'),
      'periodo_fim', to_char(MAX(data_cadastro), 'YYYY-MM-DD')
    ) FROM base),
  'por_unidade', (SELECT json_agg(por_unidade) FROM por_unidade),
  'por_operacao_e_unidade', (SELECT json_agg(por_operacao) FROM por_operacao),
  'evolucao_mensal_por_unidade', (SELECT json_agg(mensal ORDER BY mes, unidade) FROM mensal),
  'propriedades_maior_perda_media_top5_por_unidade', (SELECT json_agg(json_build_object('unidade', unidade, 'propriedade', propriedade, 'amostras', amostras, 'media', media) ORDER BY unidade, rn) FROM rk_fazenda WHERE rn <= 5),
  'operadores_maior_perda_media_top5_por_unidade', (SELECT json_agg(json_build_object('unidade', unidade, 'operador', operador, 'amostras', amostras, 'media', media) ORDER BY unidade, rn) FROM rk_operador WHERE rn <= 5),
  'talhoes_maior_perda_media_top5_por_unidade', (SELECT json_agg(json_build_object('unidade', unidade, 'talhao', talhao, 'propriedade', propriedade, 'amostras', amostras, 'media', media) ORDER BY unidade, rn) FROM rk_talhao WHERE rn <= 5),
  'equipamentos_maior_perda_media_top5_por_unidade', (SELECT json_agg(json_build_object('unidade', unidade, 'equipamento', equipamento, 'amostras', amostras, 'media', media) ORDER BY unidade, rn) FROM rk_equip WHERE rn <= 5),
  'maiores_perdas_individuais_top5_por_unidade', (SELECT json_agg(maiores ORDER BY unidade, resultado DESC) FROM maiores)
) AS dados
