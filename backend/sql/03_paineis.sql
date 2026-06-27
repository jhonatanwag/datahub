-- ── Variáveis (filtros reutilizáveis) ─────────────────────────

CREATE TABLE variaveis (
    id            SERIAL PRIMARY KEY,
    slug          VARCHAR(100) UNIQUE NOT NULL,
    nome          VARCHAR(150) NOT NULL,
    descricao     TEXT,
    tipo          VARCHAR(30) NOT NULL,
    query_fonte   TEXT,
    param_names   TEXT[],
    ativo         BOOLEAN DEFAULT true,
    criado_em     TIMESTAMP DEFAULT NOW()
);

-- ── Painéis ───────────────────────────────────────────────────

CREATE TABLE paineis (
    id            SERIAL PRIMARY KEY,
    slug          VARCHAR(100) UNIQUE NOT NULL,
    nome          VARCHAR(150) NOT NULL,
    descricao     TEXT,
    icone         VARCHAR(50) DEFAULT 'chart-bar',
    colunas       INTEGER NOT NULL DEFAULT 3,
    linhas_fixas  BOOLEAN DEFAULT false,
    total_linhas  INTEGER,
    empresa_id    INTEGER REFERENCES empresas(id) NULL,
    ativo         BOOLEAN DEFAULT true,
    ordem_menu    INTEGER DEFAULT 0,
    criado_em     TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);

-- ── Indicadores dentro do painel ─────────────────────────────

CREATE TABLE painel_indicadores (
    id              SERIAL PRIMARY KEY,
    painel_id       INTEGER REFERENCES paineis(id) ON DELETE CASCADE,
    query_slug      VARCHAR(100) NOT NULL,
    titulo          VARCHAR(150),
    linha           INTEGER NOT NULL,
    coluna          INTEGER NOT NULL,
    col_span        INTEGER DEFAULT 1,
    row_span        INTEGER DEFAULT 1,
    posicao         INTEGER DEFAULT 0,
    UNIQUE (painel_id, linha, coluna)
);

-- ── Variáveis ativas em cada painel (filtros) ─────────────────

CREATE TABLE painel_variaveis (
    id            SERIAL PRIMARY KEY,
    painel_id     INTEGER REFERENCES paineis(id) ON DELETE CASCADE,
    variavel_id   INTEGER REFERENCES variaveis(id),
    obrigatorio   BOOLEAN DEFAULT false,
    valor_padrao  TEXT,
    posicao       INTEGER DEFAULT 0,
    UNIQUE (painel_id, variavel_id)
);

-- ── Acesso de usuários aos painéis ───────────────────────────

CREATE TABLE painel_usuarios (
    painel_id     INTEGER REFERENCES paineis(id) ON DELETE CASCADE,
    usuario_id    INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    PRIMARY KEY   (painel_id, usuario_id)
);

-- ── Índices ──────────────────────────────────────────────────

CREATE INDEX idx_paineis_empresa    ON paineis(empresa_id);
CREATE INDEX idx_paineis_ativo      ON paineis(ativo);
CREATE INDEX idx_painel_ind_painel  ON painel_indicadores(painel_id);
CREATE INDEX idx_painel_var_painel  ON painel_variaveis(painel_id);
CREATE INDEX idx_painel_usr_usuario ON painel_usuarios(usuario_id);

-- ── Trigger atualizado_em ─────────────────────────────────────

CREATE TRIGGER trg_paineis_updated
BEFORE UPDATE ON paineis
FOR EACH ROW EXECUTE FUNCTION update_atualizado_em();

-- ── Seeds: variáveis padrão ───────────────────────────────────

INSERT INTO variaveis (slug, nome, descricao, tipo, param_names) VALUES
(
  'periodo',
  'Período',
  'Filtro de intervalo de datas',
  'date_range',
  ARRAY['data_inicio', 'data_fim']
),
(
  'data_unica',
  'Data',
  'Filtro de data única',
  'date',
  ARRAY['data']
),
(
  'texto_livre',
  'Busca',
  'Campo de texto livre para busca',
  'text',
  ARRAY['busca']
);

-- ── Seeds: painel de exemplo ──────────────────────────────────

INSERT INTO paineis (slug, nome, descricao, colunas, linhas_fixas, empresa_id, ordem_menu)
VALUES ('visao_geral', 'Visão Geral', 'Dashboard principal com KPIs', 4, false, NULL, 1);

INSERT INTO painel_indicadores (painel_id, query_slug, linha, coluna, col_span, titulo)
VALUES
  (1, 'kpi_receita',           1, 1, 1, NULL),
  (1, 'kpi_pedidos',           1, 2, 1, NULL),
  (1, 'kpi_ticket_medio',      1, 3, 1, NULL),
  (1, 'kpi_clientes',          1, 4, 1, NULL),
  (1, 'chart_receita_mensal',  2, 1, 2, NULL),
  (1, 'chart_pedidos_status',  2, 3, 2, NULL),
  (1, 'table_pedidos_recentes',3, 1, 4, NULL);

INSERT INTO painel_variaveis (painel_id, variavel_id, obrigatorio, posicao)
VALUES (1, 1, false, 1);

INSERT INTO painel_usuarios (painel_id, usuario_id) VALUES (1, 1);
