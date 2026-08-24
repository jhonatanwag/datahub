-- =============================================================
-- DataHub — Deltas de schema pendentes em produção (2026-08-24)
-- Roda contra um banco datahub_meta que já existe (não é um CREATE
-- TABLE completo — para banco novo, usar scripts/init-meta-prod.sql).
--
-- Grupo de painéis (mesmo padrão de query_grupos): tabela nova
-- painel_grupos + paineis.grupo_id, pra organizar painéis por
-- categoria (ex: "Exportação", "Perdas") no cadastro, no menu
-- lateral e no dashboard.
--
-- Como rodar (terminal do serviço `postgres` no EasyPanel):
--   psql -U postgres -d datahub_meta -f scripts/deltas-pendentes-2026-08-24.sql
-- Ou colar o conteúdo direto num psql já conectado em datahub_meta.
-- =============================================================

CREATE TABLE IF NOT EXISTS painel_grupos (
    id        SERIAL PRIMARY KEY,
    nome      TEXT NOT NULL UNIQUE,
    criado_em TIMESTAMP DEFAULT NOW()
);

ALTER TABLE paineis ADD COLUMN IF NOT EXISTS grupo_id INTEGER REFERENCES painel_grupos(id) ON DELETE SET NULL;

-- Verificação: a tabela e a coluna abaixo devem aparecer no resultado.
SELECT table_name FROM information_schema.tables WHERE table_name = 'painel_grupos';
SELECT column_name FROM information_schema.columns
WHERE table_name = 'paineis' AND column_name = 'grupo_id';
