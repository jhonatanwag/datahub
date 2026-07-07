-- =============================================================
-- DataHub — Schema de produção do datahub_meta
-- Só estrutura (tabelas, índices, FKs, trigger) — sem seed de demo,
-- sem usuário admin. Rodar uma única vez, contra um banco `datahub_meta`
-- vazio já criado (o serviço postgres do EasyPanel cria o banco e o
-- usuário via POSTGRES_DB / POSTGRES_USER).
-- =============================================================

CREATE FUNCTION update_atualizado_em() RETURNS trigger AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE empresas (
    id           SERIAL PRIMARY KEY,
    slug         VARCHAR(50) UNIQUE NOT NULL,
    nome         VARCHAR(100) NOT NULL,
    db_host      VARCHAR(100) NOT NULL,
    db_port      INTEGER DEFAULT 5432,
    db_name      VARCHAR(100) NOT NULL,
    db_user      VARCHAR(100) NOT NULL,
    db_pass      VARCHAR(100) NOT NULL,
    ativo        BOOLEAN DEFAULT true,
    criado_em    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE usuarios (
    id           SERIAL PRIMARY KEY,
    nome         VARCHAR(100) NOT NULL,
    email        VARCHAR(150) UNIQUE NOT NULL,
    senha_hash   VARCHAR(255) NOT NULL,
    role         VARCHAR(20) DEFAULT 'viewer',
    ativo        BOOLEAN DEFAULT true,
    criado_em    TIMESTAMP DEFAULT NOW(),
    tema         VARCHAR(10) NOT NULL DEFAULT 'escuro'
);

CREATE TABLE usuario_empresas (
    usuario_id   INTEGER NOT NULL REFERENCES usuarios(id),
    empresa_id   INTEGER NOT NULL REFERENCES empresas(id),
    PRIMARY KEY  (usuario_id, empresa_id)
);

CREATE TABLE variaveis (
    id           SERIAL PRIMARY KEY,
    slug         VARCHAR(100) UNIQUE NOT NULL,
    nome         VARCHAR(150) NOT NULL,
    descricao    TEXT,
    tipo         VARCHAR(30) NOT NULL,
    query_fonte  TEXT,
    param_names  TEXT[],
    ativo        BOOLEAN DEFAULT true,
    criado_em    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE queries (
    id             SERIAL PRIMARY KEY,
    slug           VARCHAR(100) NOT NULL,
    nome           VARCHAR(150) NOT NULL,
    descricao      TEXT,
    sql_texto      TEXT NOT NULL,
    tipo           VARCHAR(30) NOT NULL,
    empresa_id     INTEGER REFERENCES empresas(id),
    ativo          BOOLEAN DEFAULT true,
    cache_ttl      INTEGER DEFAULT 300,
    criado_em      TIMESTAMP DEFAULT NOW(),
    atualizado_em  TIMESTAMP DEFAULT NOW(),
    kpi_cor_fonte  TEXT DEFAULT '#e6edf3',
    kpi_cor_fundo  TEXT DEFAULT '#161b22',
    UNIQUE (slug, empresa_id)
);
CREATE INDEX idx_queries_empresa ON queries(empresa_id);
CREATE INDEX idx_queries_slug ON queries(slug);

CREATE TABLE query_parametros (
    id            SERIAL PRIMARY KEY,
    query_id      INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    nome          VARCHAR(50) NOT NULL,
    tipo          VARCHAR(20) NOT NULL,
    obrigatorio   BOOLEAN DEFAULT false,
    valor_padrao  TEXT,
    descricao     TEXT,
    variavel_id   INTEGER REFERENCES variaveis(id) ON DELETE SET NULL,
    param_slot    VARCHAR(10)
);
CREATE INDEX idx_qp_query_id ON query_parametros(query_id);

CREATE TABLE paineis (
    id             SERIAL PRIMARY KEY,
    slug           VARCHAR(100) UNIQUE NOT NULL,
    nome           VARCHAR(150) NOT NULL,
    descricao      TEXT,
    icone          VARCHAR(50) DEFAULT 'chart-bar',
    colunas        INTEGER NOT NULL DEFAULT 3,
    linhas_fixas   BOOLEAN DEFAULT false,
    total_linhas   INTEGER,
    empresa_id     INTEGER REFERENCES empresas(id),
    ativo          BOOLEAN DEFAULT true,
    ordem_menu     INTEGER DEFAULT 0,
    criado_em      TIMESTAMP DEFAULT NOW(),
    atualizado_em  TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_paineis_empresa ON paineis(empresa_id);
CREATE INDEX idx_paineis_ativo ON paineis(ativo);
CREATE TRIGGER trg_paineis_updated
    BEFORE UPDATE ON paineis
    FOR EACH ROW EXECUTE FUNCTION update_atualizado_em();

CREATE TABLE painel_indicadores (
    id          SERIAL PRIMARY KEY,
    painel_id   INTEGER REFERENCES paineis(id) ON DELETE CASCADE,
    query_slug  VARCHAR(100) NOT NULL,
    titulo      VARCHAR(150),
    linha       INTEGER NOT NULL,
    coluna      INTEGER NOT NULL,
    col_span    INTEGER DEFAULT 1,
    row_span    INTEGER DEFAULT 1,
    posicao     INTEGER DEFAULT 0,
    UNIQUE (painel_id, linha, coluna)
);
CREATE INDEX idx_painel_ind_painel ON painel_indicadores(painel_id);

CREATE TABLE painel_variaveis (
    id                    SERIAL PRIMARY KEY,
    painel_id             INTEGER REFERENCES paineis(id) ON DELETE CASCADE,
    variavel_id           INTEGER REFERENCES variaveis(id),
    obrigatorio           BOOLEAN DEFAULT false,
    valor_padrao          TEXT,
    posicao               INTEGER DEFAULT 0,
    valor_padrao_inicio   TEXT,
    valor_padrao_fim      TEXT,
    UNIQUE (painel_id, variavel_id)
);
CREATE INDEX idx_painel_var_painel ON painel_variaveis(painel_id);

CREATE TABLE painel_usuarios (
    painel_id   INTEGER NOT NULL REFERENCES paineis(id) ON DELETE CASCADE,
    usuario_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    PRIMARY KEY (painel_id, usuario_id)
);
CREATE INDEX idx_painel_usr_usuario ON painel_usuarios(usuario_id);

CREATE TABLE chat_historico (
    id          SERIAL PRIMARY KEY,
    usuario_id  INTEGER REFERENCES usuarios(id),
    empresa_id  INTEGER REFERENCES empresas(id),
    pergunta    TEXT NOT NULL,
    resposta    TEXT NOT NULL,
    criado_em   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE dashboard_layout (
    id          SERIAL PRIMARY KEY,
    empresa_id  INTEGER REFERENCES empresas(id),
    query_slug  VARCHAR(100) NOT NULL,
    posicao     INTEGER NOT NULL,
    largura     VARCHAR(10) DEFAULT 'half',
    titulo      VARCHAR(150),
    visivel     BOOLEAN DEFAULT true
);
CREATE INDEX idx_layout_empresa ON dashboard_layout(empresa_id);

CREATE TABLE tarefas (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo          VARCHAR(50) NOT NULL,
    empresa_id    INTEGER REFERENCES empresas(id),
    usuario_id    INTEGER REFERENCES usuarios(id),
    status        VARCHAR(20) DEFAULT 'pendente',
    payload       JSONB,
    resultado     JSONB,
    criado_em     TIMESTAMP DEFAULT NOW(),
    concluido_em  TIMESTAMP
);
