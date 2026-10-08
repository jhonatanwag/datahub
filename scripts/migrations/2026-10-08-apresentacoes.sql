-- Apresentação de painéis (TV): sequência de painéis existentes com filtros fixos e
-- tempo por slide. Rodar no datahub_meta de cada ambiente ANTES do deploy.
CREATE TABLE IF NOT EXISTS apresentacoes (
    id                         SERIAL PRIMARY KEY,
    slug                       VARCHAR(100) UNIQUE NOT NULL,
    nome                       VARCHAR(150) NOT NULL,
    descricao                  TEXT,
    empresa_id                 INTEGER REFERENCES empresas(id),
    intervalo_atualizacao_seg  INTEGER NOT NULL DEFAULT 300,
    ativo                      BOOLEAN NOT NULL DEFAULT true,
    criado_em                  TIMESTAMP DEFAULT NOW(),
    atualizado_em              TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS apresentacao_slides (
    id              SERIAL PRIMARY KEY,
    apresentacao_id INTEGER NOT NULL REFERENCES apresentacoes(id) ON DELETE CASCADE,
    painel_id       INTEGER NOT NULL REFERENCES paineis(id) ON DELETE CASCADE,
    ordem           INTEGER NOT NULL DEFAULT 0,
    duracao_seg     INTEGER NOT NULL DEFAULT 30,
    filtros         JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_apres_slides_apres ON apresentacao_slides(apresentacao_id, ordem);

CREATE TABLE IF NOT EXISTS apresentacao_usuarios (
    apresentacao_id INTEGER NOT NULL REFERENCES apresentacoes(id) ON DELETE CASCADE,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    PRIMARY KEY (apresentacao_id, usuario_id)
);
CREATE INDEX IF NOT EXISTS idx_apres_usr_usuario ON apresentacao_usuarios(usuario_id);

DROP TRIGGER IF EXISTS trg_apresentacoes_updated ON apresentacoes;
CREATE TRIGGER trg_apresentacoes_updated
BEFORE UPDATE ON apresentacoes
FOR EACH ROW EXECUTE FUNCTION update_atualizado_em();
