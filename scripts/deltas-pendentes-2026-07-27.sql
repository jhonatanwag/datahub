-- =============================================================
-- DataHub — Deltas de schema pendentes em produção (2026-07-27)
-- Roda contra um banco datahub_meta que já existe (não é um CREATE
-- TABLE completo — para banco novo, usar scripts/init-meta-prod.sql).
--
-- Cobre as duas features mergeadas em 2026-07-26/27 que ainda não
-- foram aplicadas em produção (última sincronização confirmada:
-- 2026-07-20). Usa IF NOT EXISTS em cada coluna, então é seguro rodar
-- de novo mesmo que alguma coluna já exista.
--
-- Como rodar (terminal do serviço `postgres` no EasyPanel):
--   psql -U postgres -d datahub_meta -f scripts/deltas-pendentes-2026-07-27.sql
-- Ou colar o conteúdo direto num psql já conectado em datahub_meta.
-- =============================================================

-- 2026-07-26 — botão de impressão opcional em queries tipo table (link pro sistema legado de relatórios)
ALTER TABLE queries ADD COLUMN IF NOT EXISTS impressao_habilitada BOOLEAN DEFAULT false;
ALTER TABLE queries ADD COLUMN IF NOT EXISTS impressao_caminho TEXT;
ALTER TABLE queries ADD COLUMN IF NOT EXISTS impressao_coluna TEXT;

-- 2026-07-26 — URL base do sistema legado de impressão de relatórios, por empresa
ALTER TABLE empresas ADD COLUMN IF NOT EXISTS url_impressao_base TEXT;

-- 2026-07-27 — coloração condicional de uma coluna por meta (início/fim), queries tipo table
ALTER TABLE queries ADD COLUMN IF NOT EXISTS meta_habilitada BOOLEAN DEFAULT false;
ALTER TABLE queries ADD COLUMN IF NOT EXISTS meta_coluna_valor TEXT;
ALTER TABLE queries ADD COLUMN IF NOT EXISTS meta_coluna_inicio TEXT;
ALTER TABLE queries ADD COLUMN IF NOT EXISTS meta_coluna_fim TEXT;
ALTER TABLE queries ADD COLUMN IF NOT EXISTS meta_cor_dentro TEXT DEFAULT '#3fb950';
ALTER TABLE queries ADD COLUMN IF NOT EXISTS meta_cor_fora TEXT DEFAULT '#f85149';

-- Verificação: as 9 colunas abaixo devem aparecer no resultado.
SELECT table_name, column_name FROM information_schema.columns
WHERE (table_name = 'queries' AND column_name IN (
         'impressao_habilitada', 'impressao_caminho', 'impressao_coluna',
         'meta_habilitada', 'meta_coluna_valor', 'meta_coluna_inicio',
         'meta_coluna_fim', 'meta_cor_dentro', 'meta_cor_fora'
       ))
   OR (table_name = 'empresas' AND column_name = 'url_impressao_base')
ORDER BY table_name, column_name;
