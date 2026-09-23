-- IDs estáveis (faixa 6000-6999) do script de permissões do PSOEDUCARE.
-- Um seq por painel / grupo, alocado na primeira geração e mantido para sempre.
-- Seguro rodar mais de uma vez.
\set ON_ERROR_STOP on
BEGIN;

CREATE TABLE IF NOT EXISTS permissao_ids (
    tipo    VARCHAR(10) NOT NULL,   -- 'painel' | 'grupo'
    ref_id  INTEGER     NOT NULL,   -- paineis.id ou painel_grupos.id
    seq     INTEGER     NOT NULL,
    PRIMARY KEY (tipo, ref_id),
    UNIQUE (tipo, seq)
);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'datahub_user') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON permissao_ids TO datahub_user;
    END IF;
END $$;

COMMIT;
