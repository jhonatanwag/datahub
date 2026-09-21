-- Queries RAG (tipo rag_context, globais) de Pendências, Inspeções, Entregas de EPI e Perdas.
-- Idempotente: atualiza se o slug global já existir, senão insere. O grupo é buscado pelo nome
-- (fica NULL se não existir no banco). Fonte dos SQLs: scripts/rag-queries/*.sql
-- Nota: as tabelas do negócio (pendencia, lancamento_ficha, req_estoque, perda...) são as do banco da
-- empresa (ex: vitoria_agro); este script roda no banco de METADADOS (datahub_meta).

-- rag_contexto_pendencias
UPDATE queries SET nome = 'Contexto Pendências para IA', descricao = 'Pendências (equipamento, sede e lavoura) resumidas: totais por tipo/situação, tempo médio de resolução, evolução mensal (últimos 12 meses com aberturas), em aberto por sistema/frente, top 15 equipamentos com mais pendências em aberto e as 10 mais antigas em aberto — tamanho ajustado pro limite de tokens/minuto da conta Groq', sql_texto = $rag$WITH base AS (
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
) AS dados$rag$,
  tipo = 'rag_context', cache_ttl = 600, ativo = true, grupo_id = (SELECT id FROM query_grupos WHERE nome = 'Pendência' ORDER BY id LIMIT 1), atualizado_em = now()
WHERE slug = 'rag_contexto_pendencias' AND empresa_id IS NULL;
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, empresa_id, cache_ttl, grupo_id)
SELECT 'rag_contexto_pendencias', 'Contexto Pendências para IA', 'Pendências (equipamento, sede e lavoura) resumidas: totais por tipo/situação, tempo médio de resolução, evolução mensal (últimos 12 meses com aberturas), em aberto por sistema/frente, top 15 equipamentos com mais pendências em aberto e as 10 mais antigas em aberto — tamanho ajustado pro limite de tokens/minuto da conta Groq', $rag$WITH base AS (
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
) AS dados$rag$, 'rag_context', NULL, 600, (SELECT id FROM query_grupos WHERE nome = 'Pendência' ORDER BY id LIMIT 1)
WHERE NOT EXISTS (SELECT 1 FROM queries WHERE slug = 'rag_contexto_pendencias' AND empresa_id IS NULL);

-- rag_contexto_inspecoes
UPDATE queries SET nome = 'Contexto Inspeções para IA', descricao = 'Inspeções (fichas/checklists ROTINA, AUDITORIA e PREVENTIVA) resumidas: histórico por tipo, últimos 12 meses de lançamentos e respostas NAO (irregularidades), top 15 perguntas, top 10 equipamentos/operadores, propriedades e fichas mais lançadas — tamanho ajustado pro limite de tokens/minuto da conta Groq', sql_texto = $rag$WITH lanc AS (
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
) AS dados$rag$,
  tipo = 'rag_context', cache_ttl = 600, ativo = true, grupo_id = (SELECT id FROM query_grupos WHERE nome = 'Inspeção' ORDER BY id LIMIT 1), atualizado_em = now()
WHERE slug = 'rag_contexto_inspecoes' AND empresa_id IS NULL;
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, empresa_id, cache_ttl, grupo_id)
SELECT 'rag_contexto_inspecoes', 'Contexto Inspeções para IA', 'Inspeções (fichas/checklists ROTINA, AUDITORIA e PREVENTIVA) resumidas: histórico por tipo, últimos 12 meses de lançamentos e respostas NAO (irregularidades), top 15 perguntas, top 10 equipamentos/operadores, propriedades e fichas mais lançadas — tamanho ajustado pro limite de tokens/minuto da conta Groq', $rag$WITH lanc AS (
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
) AS dados$rag$, 'rag_context', NULL, 600, (SELECT id FROM query_grupos WHERE nome = 'Inspeção' ORDER BY id LIMIT 1)
WHERE NOT EXISTS (SELECT 1 FROM queries WHERE slug = 'rag_contexto_inspecoes' AND empresa_id IS NULL);

-- rag_contexto_epi
UPDATE queries SET nome = 'Contexto Entregas de EPI para IA', descricao = 'Entregas de EPI resumidas: totais gerais, por tipo de entrega (recebimento/trocas), evolução mensal (últimos 12 meses com entregas), por propriedade, top 10 produtos e colaboradores, e situação dos CA (vencidos, a vencer, entregas com CA vencido) — tamanho ajustado pro limite de tokens/minuto da conta Groq', sql_texto = $rag$WITH itens AS (
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
) AS dados$rag$,
  tipo = 'rag_context', cache_ttl = 600, ativo = true, grupo_id = (SELECT id FROM query_grupos WHERE nome = 'EPI' ORDER BY id LIMIT 1), atualizado_em = now()
WHERE slug = 'rag_contexto_epi' AND empresa_id IS NULL;
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, empresa_id, cache_ttl, grupo_id)
SELECT 'rag_contexto_epi', 'Contexto Entregas de EPI para IA', 'Entregas de EPI resumidas: totais gerais, por tipo de entrega (recebimento/trocas), evolução mensal (últimos 12 meses com entregas), por propriedade, top 10 produtos e colaboradores, e situação dos CA (vencidos, a vencer, entregas com CA vencido) — tamanho ajustado pro limite de tokens/minuto da conta Groq', $rag$WITH itens AS (
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
) AS dados$rag$, 'rag_context', NULL, 600, (SELECT id FROM query_grupos WHERE nome = 'EPI' ORDER BY id LIMIT 1)
WHERE NOT EXISTS (SELECT 1 FROM queries WHERE slug = 'rag_contexto_epi' AND empresa_id IS NULL);

-- rag_contexto_perdas
UPDATE queries SET nome = 'Contexto Perdas para IA', descricao = 'Perdas de colheita resumidas por unidade (sacas/ha e @/ha, nunca misturadas): totais, média/mediana/máximo, por operação, evolução mensal, top 5 propriedades/operadores/talhões/equipamentos com maior perda média e as 5 maiores perdas individuais — tamanho ajustado pro limite de tokens/minuto da conta Groq', sql_texto = $rag$WITH base AS (
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
) AS dados$rag$,
  tipo = 'rag_context', cache_ttl = 600, ativo = true, grupo_id = (SELECT id FROM query_grupos WHERE nome = 'Perda' ORDER BY id LIMIT 1), atualizado_em = now()
WHERE slug = 'rag_contexto_perdas' AND empresa_id IS NULL;
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, empresa_id, cache_ttl, grupo_id)
SELECT 'rag_contexto_perdas', 'Contexto Perdas para IA', 'Perdas de colheita resumidas por unidade (sacas/ha e @/ha, nunca misturadas): totais, média/mediana/máximo, por operação, evolução mensal, top 5 propriedades/operadores/talhões/equipamentos com maior perda média e as 5 maiores perdas individuais — tamanho ajustado pro limite de tokens/minuto da conta Groq', $rag$WITH base AS (
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
) AS dados$rag$, 'rag_context', NULL, 600, (SELECT id FROM query_grupos WHERE nome = 'Perda' ORDER BY id LIMIT 1)
WHERE NOT EXISTS (SELECT 1 FROM queries WHERE slug = 'rag_contexto_perdas' AND empresa_id IS NULL);
