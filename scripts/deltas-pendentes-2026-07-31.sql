-- =============================================================
-- DataHub — Deltas de schema pendentes em produção (2026-07-31)
-- Roda contra um banco datahub_meta que já existe (não é um CREATE
-- TABLE completo — para banco novo, usar scripts/init-meta-prod.sql).
--
-- Guarda a imagem de capa do painel direto no banco (coluna BYTEA)
-- em vez de arquivo em disco — decisão do usuário, volume pequeno
-- de imagens não justifica depender de volume persistente no VPS.
--
-- Como rodar (terminal do serviço `postgres` no EasyPanel):
--   psql -U postgres -d datahub_meta -f scripts/deltas-pendentes-2026-07-31.sql
-- Ou colar o conteúdo direto num psql já conectado em datahub_meta.
-- =============================================================

ALTER TABLE paineis ADD COLUMN IF NOT EXISTS imagem BYTEA;
ALTER TABLE paineis ADD COLUMN IF NOT EXISTS imagem_mime TEXT;

-- Verificação: as 2 colunas abaixo devem aparecer no resultado.
SELECT table_name, column_name FROM information_schema.columns
WHERE table_name = 'paineis' AND column_name IN ('imagem', 'imagem_mime')
ORDER BY column_name;
