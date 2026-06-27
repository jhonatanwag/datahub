-- Parâmetros posicionais das queries ($1, $2, ...)
-- A ordem de inserção define a posição (id ASC = $1, $2...)

CREATE TABLE IF NOT EXISTS query_parametros (
    id           SERIAL PRIMARY KEY,
    query_id     INTEGER NOT NULL REFERENCES queries(id) ON DELETE CASCADE,
    nome         TEXT NOT NULL,                          -- nome descritivo (ex: data_inicio)
    tipo         TEXT NOT NULL DEFAULT 'text',           -- text | date | number | date_range
    obrigatorio  BOOLEAN NOT NULL DEFAULT false,
    valor_padrao TEXT,
    descricao    TEXT,
    variavel_id  INTEGER REFERENCES variaveis(id) ON DELETE SET NULL,
    param_slot   VARCHAR(10),   -- 'inicio' | 'fim' — apenas para variaveis date_range
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qp_query_id ON query_parametros(query_id);

-- permissões
GRANT SELECT, INSERT, UPDATE, DELETE ON query_parametros TO datahub_user;
GRANT USAGE, SELECT ON SEQUENCE query_parametros_id_seq TO datahub_user;
