-- =============================================================
-- DataHub — Script de inicialização local
-- Cria bancos, usuários e popula com dados fictícios realistas
-- =============================================================

-- ── 1. Bancos e usuários das empresas ──────────────────────

CREATE USER alpha_user WITH PASSWORD 'alpha123';
CREATE USER beta_user  WITH PASSWORD 'beta123';
CREATE USER gamma_user WITH PASSWORD 'gamma123';
CREATE USER datahub_user WITH PASSWORD 'datahub123';

CREATE DATABASE alpha_db  OWNER alpha_user;
CREATE DATABASE beta_db   OWNER beta_user;
CREATE DATABASE gamma_db  OWNER gamma_user;
CREATE DATABASE datahub_meta OWNER datahub_user;

-- ── 2. Banco datahub_meta ───────────────────────────────────

\c datahub_meta

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
    criado_em    TIMESTAMP DEFAULT NOW(),
    sso_api_key_hash VARCHAR(255),
    sso_query_acesso TEXT,
    url_impressao_base TEXT
);

CREATE TABLE usuarios (
    id           SERIAL PRIMARY KEY,
    nome         VARCHAR(100) NOT NULL,
    email        VARCHAR(150) UNIQUE NOT NULL,
    senha_hash   VARCHAR(255) NOT NULL,
    role         VARCHAR(20) DEFAULT 'viewer',
    ativo        BOOLEAN DEFAULT true,
    tema         VARCHAR(10) NOT NULL DEFAULT 'escuro',
    criado_em    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE usuario_empresas (
    usuario_id             INTEGER REFERENCES usuarios(id),
    empresa_id             INTEGER REFERENCES empresas(id),
    codigo_usuario_externo TEXT,
    PRIMARY KEY  (usuario_id, empresa_id)
);

CREATE TABLE chat_historico (
    id           SERIAL PRIMARY KEY,
    usuario_id   INTEGER REFERENCES usuarios(id),
    empresa_id   INTEGER REFERENCES empresas(id),
    pergunta     TEXT NOT NULL,
    resposta     TEXT NOT NULL,
    criado_em    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE tarefas (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo         VARCHAR(50) NOT NULL,
    empresa_id   INTEGER REFERENCES empresas(id),
    usuario_id   INTEGER REFERENCES usuarios(id),
    status       VARCHAR(20) DEFAULT 'pendente',
    payload      JSONB,
    resultado    JSONB,
    criado_em    TIMESTAMP DEFAULT NOW(),
    concluido_em TIMESTAMP
);

CREATE TABLE queries (
    id            SERIAL PRIMARY KEY,
    slug          VARCHAR(100) NOT NULL,
    nome          VARCHAR(150) NOT NULL,
    descricao     TEXT,
    sql_texto     TEXT NOT NULL,
    tipo          VARCHAR(30) NOT NULL,
    empresa_id    INTEGER REFERENCES empresas(id) NULL,
    ativo         BOOLEAN DEFAULT true,
    cache_ttl     INTEGER DEFAULT 300,
    criado_em     TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW(),
    mapa_camada   VARCHAR(20) DEFAULT 'padrao',
    chart_fonte_tamanho   INTEGER DEFAULT 12,
    chart_truncar_label   BOOLEAN DEFAULT false,
    chart_truncar_tamanho INTEGER DEFAULT 15,
    chart_mostrar_valor   BOOLEAN DEFAULT false,
    chart_valor_label     VARCHAR(50),
    impressao_habilitada  BOOLEAN DEFAULT false,
    impressao_caminho     TEXT,
    impressao_coluna      TEXT,
    UNIQUE (slug, empresa_id)
);

CREATE TABLE query_parametros (
    id           SERIAL PRIMARY KEY,
    query_id     INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    nome         VARCHAR(50) NOT NULL,
    tipo         VARCHAR(20) NOT NULL,
    obrigatorio  BOOLEAN DEFAULT false,
    valor_padrao TEXT,
    descricao    TEXT
);

CREATE TABLE dashboard_layout (
    id           SERIAL PRIMARY KEY,
    empresa_id   INTEGER REFERENCES empresas(id) NULL,
    query_slug   VARCHAR(100) NOT NULL,
    posicao      INTEGER NOT NULL,
    largura      VARCHAR(10) DEFAULT 'half',
    titulo       VARCHAR(150),
    visivel      BOOLEAN DEFAULT true
);

-- Índices
CREATE INDEX idx_queries_slug    ON queries(slug);
CREATE INDEX idx_queries_empresa ON queries(empresa_id);
CREATE INDEX idx_layout_empresa  ON dashboard_layout(empresa_id);

-- Empresas (host = postgres = nome do serviço Docker)
INSERT INTO empresas (slug, nome, db_host, db_name, db_user, db_pass) VALUES
  ('alpha', 'Empresa Alpha Ltda',  'postgres', 'alpha_db', 'alpha_user', 'alpha123'),
  ('beta',  'Beta Comércio S.A.',  'postgres', 'beta_db',  'beta_user',  'beta123'),
  ('gamma', 'Gamma Tech ME',       'postgres', 'gamma_db', 'gamma_user', 'gamma123');

-- Usuário admin (senha: admin123 — hash bcrypt)
INSERT INTO usuarios (nome, email, senha_hash, role) VALUES
  ('Administrador', 'admin@datahub.local',
   '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TiGmiR7lDaqDlnFRMlcR1RnQLT6e',
   'admin');

-- Acesso do admin a todas as empresas
INSERT INTO usuario_empresas (usuario_id, empresa_id) VALUES
  (1, 1), (1, 2), (1, 3);

-- Queries globais padrão
INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl) VALUES
(
  'kpi_receita', 'Receita Total (30d)',
  'Soma da receita nos últimos 30 dias',
  'SELECT COALESCE(SUM(valor), 0) AS valor, ''Receita Total'' AS label, ''R$'' AS prefixo FROM pedidos WHERE data >= NOW() - INTERVAL ''30 days''',
  'kpi', 300
),
(
  'kpi_pedidos', 'Total de Pedidos (30d)',
  'Contagem de pedidos nos últimos 30 dias',
  'SELECT COUNT(*)::numeric AS valor, ''Pedidos'' AS label, '''' AS prefixo FROM pedidos WHERE data >= NOW() - INTERVAL ''30 days''',
  'kpi', 300
),
(
  'kpi_ticket_medio', 'Ticket Médio (30d)',
  'Valor médio por pedido',
  'SELECT COALESCE(AVG(valor), 0) AS valor, ''Ticket Médio'' AS label, ''R$'' AS prefixo FROM pedidos WHERE data >= NOW() - INTERVAL ''30 days''',
  'kpi', 300
),
(
  'kpi_clientes', 'Clientes Ativos (30d)',
  'Clientes distintos no período',
  'SELECT COUNT(DISTINCT cliente_nome)::numeric AS valor, ''Clientes Ativos'' AS label, '''' AS prefixo FROM pedidos WHERE data >= NOW() - INTERVAL ''30 days''',
  'kpi', 300
),
(
  'chart_receita_mensal', 'Receita Mensal',
  'Evolução da receita mês a mês',
  'SELECT TO_CHAR(data, ''Mon'') AS label, EXTRACT(MONTH FROM data)::int AS mes_num, COALESCE(SUM(valor), 0) AS valor FROM pedidos WHERE data >= NOW() - INTERVAL ''12 months'' GROUP BY 1, 2 ORDER BY 2',
  'chart_line', 600
),
(
  'chart_pedidos_status', 'Pedidos por Status',
  'Distribuição por status',
  'SELECT status AS label, COUNT(*)::numeric AS valor FROM pedidos WHERE data >= NOW() - INTERVAL ''30 days'' GROUP BY status ORDER BY valor DESC',
  'chart_bar_horizontal', 600
),
(
  'chart_canal_vendas', 'Canal de Vendas',
  'Distribuição por canal',
  'SELECT canal AS label, COUNT(*)::numeric AS valor FROM pedidos WHERE data >= NOW() - INTERVAL ''30 days'' GROUP BY canal ORDER BY valor DESC',
  'chart_doughnut', 600
),
(
  'table_pedidos_recentes', 'Pedidos Recentes',
  'Últimos 50 pedidos',
  'SELECT id, cliente_nome, produto, valor, status, canal, TO_CHAR(data, ''DD/MM/YYYY'') AS data FROM pedidos ORDER BY data DESC LIMIT 50',
  'table', 120
),
(
  'rag_contexto_principal', 'Contexto Principal para IA',
  'Dados injetados no chatbot',
  'SELECT ''resumo_30d'' AS secao, json_build_object(''receita_total'', SUM(valor), ''total_pedidos'', COUNT(*), ''ticket_medio'', ROUND(AVG(valor)::numeric, 2), ''clientes_ativos'', COUNT(DISTINCT cliente_nome)) AS dados FROM pedidos WHERE data >= NOW() - INTERVAL ''30 days''',
  'rag_context', 600
);

-- Layout padrão global
INSERT INTO dashboard_layout (empresa_id, query_slug, posicao, largura) VALUES
  (NULL, 'kpi_receita',           1, 'quarter'),
  (NULL, 'kpi_pedidos',           2, 'quarter'),
  (NULL, 'kpi_ticket_medio',      3, 'quarter'),
  (NULL, 'kpi_clientes',          4, 'quarter'),
  (NULL, 'chart_receita_mensal',  5, 'half'),
  (NULL, 'chart_pedidos_status',  6, 'half'),
  (NULL, 'chart_canal_vendas',    7, 'half'),
  (NULL, 'table_pedidos_recentes',8, 'full');

-- ── 3. Banco alpha_db ───────────────────────────────────────

\c alpha_db

CREATE TABLE pedidos (
    id           SERIAL PRIMARY KEY,
    cliente_nome VARCHAR(100) NOT NULL,
    produto      VARCHAR(100) NOT NULL,
    valor        NUMERIC(10,2) NOT NULL,
    status       VARCHAR(30) NOT NULL DEFAULT 'concluido',
    canal        VARCHAR(30) NOT NULL DEFAULT 'ecommerce',
    data         TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Dados fictícios Alpha (12 meses, ~500 pedidos)
INSERT INTO pedidos (cliente_nome, produto, valor, status, canal, data)
SELECT
  (ARRAY['João Silva','Maria Costa','Pedro Lima','Ana Souza','Lucas Ramos',
         'Fernanda Dias','Carlos Mendes','Juliana Pinto','Rafael Cruz','Bianca Leal',
         'Diego Mota','Larissa Faria','Bruno Alves','Camila Reis','Thiago Neto'])[floor(random()*15+1)::int],
  (ARRAY['Notebook Pro','Mouse Gamer','Teclado RGB','Monitor 4K','Headset BT',
         'Webcam HD','SSD 1TB','Memória RAM','Placa de Vídeo','Roteador WiFi'])[floor(random()*10+1)::int],
  ROUND((random() * 2800 + 200)::numeric, 2),
  (ARRAY['concluido','concluido','concluido','pendente','cancelado'])[floor(random()*5+1)::int],
  (ARRAY['ecommerce','ecommerce','loja_fisica','whatsapp','revendas'])[floor(random()*5+1)::int],
  NOW() - (random() * 365 || ' days')::interval
FROM generate_series(1, 520);

GRANT SELECT ON ALL TABLES IN SCHEMA public TO alpha_user;

-- ── 4. Banco beta_db ────────────────────────────────────────

\c beta_db

CREATE TABLE pedidos (
    id           SERIAL PRIMARY KEY,
    cliente_nome VARCHAR(100) NOT NULL,
    produto      VARCHAR(100) NOT NULL,
    valor        NUMERIC(10,2) NOT NULL,
    status       VARCHAR(30) NOT NULL DEFAULT 'concluido',
    canal        VARCHAR(30) NOT NULL DEFAULT 'ecommerce',
    data         TIMESTAMP NOT NULL DEFAULT NOW()
);

INSERT INTO pedidos (cliente_nome, produto, valor, status, canal, data)
SELECT
  (ARRAY['Roberto Neto','Camila Rios','Marcos Alves','Patrícia Gomes','Felipe Santos',
         'Aline Ferreira','Eduardo Costa','Vanessa Lima','Anderson Rocha','Priscila Melo'])[floor(random()*10+1)::int],
  (ARRAY['Consultoria TI','Suporte Mensal','Desenvolvimento Web','App Mobile',
         'Hospedagem Cloud','Backup Gerenciado','Segurança Digital','Treinamento'])[floor(random()*8+1)::int],
  ROUND((random() * 3500 + 500)::numeric, 2),
  (ARRAY['concluido','concluido','pendente','cancelado'])[floor(random()*4+1)::int],
  (ARRAY['ecommerce','whatsapp','loja_fisica','revendas'])[floor(random()*4+1)::int],
  NOW() - (random() * 365 || ' days')::interval
FROM generate_series(1, 280);

GRANT SELECT ON ALL TABLES IN SCHEMA public TO beta_user;

-- ── 5. Banco gamma_db ───────────────────────────────────────

\c gamma_db

CREATE TABLE pedidos (
    id           SERIAL PRIMARY KEY,
    cliente_nome VARCHAR(100) NOT NULL,
    produto      VARCHAR(100) NOT NULL,
    valor        NUMERIC(10,2) NOT NULL,
    status       VARCHAR(30) NOT NULL DEFAULT 'concluido',
    canal        VARCHAR(30) NOT NULL DEFAULT 'ecommerce',
    data         TIMESTAMP NOT NULL DEFAULT NOW()
);

INSERT INTO pedidos (cliente_nome, produto, valor, status, canal, data)
SELECT
  (ARRAY['Startup Alpha','Empresa XYZ','Negócios ME','Tech Corp','Inovação SA',
         'Soluções Ltda','Digital Hub','Smart Systems'])[floor(random()*8+1)::int],
  (ARRAY['Plano Básico','Plano Pro','Plano Enterprise','Add-on Analytics',
         'Add-on IA','Suporte Premium','Onboarding','Treinamento'])[floor(random()*8+1)::int],
  ROUND((random() * 1500 + 99)::numeric, 2),
  (ARRAY['concluido','concluido','concluido','pendente'])[floor(random()*4+1)::int],
  (ARRAY['ecommerce','ecommerce','whatsapp','revendas'])[floor(random()*4+1)::int],
  NOW() - (random() * 365 || ' days')::interval
FROM generate_series(1, 150);

GRANT SELECT ON ALL TABLES IN SCHEMA public TO gamma_user;
