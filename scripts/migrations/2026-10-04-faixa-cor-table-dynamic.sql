-- Faixas de cor automáticas nas células agregadas do table_dynamic (ex.: nota de auditoria:
-- até 70 vermelho, 71 a 90 amarelo, acima de 90 verde). Rodar no datahub_meta de cada ambiente.
ALTER TABLE queries ADD COLUMN IF NOT EXISTS faixa_cor_habilitada BOOLEAN DEFAULT false;
ALTER TABLE queries ADD COLUMN IF NOT EXISTS faixa_cor_ate_vermelho NUMERIC DEFAULT 70;
ALTER TABLE queries ADD COLUMN IF NOT EXISTS faixa_cor_ate_amarelo  NUMERIC DEFAULT 90;
