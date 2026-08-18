# DataHub — Analytics Multiempresa

Sistema de analytics configurável para múltiplas empresas. Cada empresa tem seu próprio banco PostgreSQL; um banco central controla usuários, permissões e histórico de chat. O dashboard é totalmente dinâmico: os widgets são definidos por queries SQL cadastradas no painel de configurações.

Desenvolvido com FastAPI + asyncpg + Redis + SvelteKit + ECharts + Groq LLaMA 3.3 70B.

## Pré-requisitos

- Docker + Docker Compose
- Node.js 20+ (apenas para dev local sem Docker)
- Conta gratuita no [Groq Console](https://console.groq.com) para obter `GROQ_API_KEY`

## Rodando localmente

```bash
# 1. Clone e configure variáveis
cp backend/.env.example backend/.env.dev
# Edite backend/.env.dev com sua GROQ_API_KEY e um JWT_SECRET de 32+ chars

# 2. Suba o stack completo
docker compose -f docker-compose.dev.yml up --build

# 3. Acesse
# Frontend:  http://localhost:3000
# API Docs:  http://localhost:3001/docs
# Login:     admin@datahub.local / admin123 / empresa: alpha
```

## Variáveis de ambiente (backend)

| Variável          | Descrição                              |
|-------------------|----------------------------------------|
| `JWT_SECRET`      | String aleatória 32+ caracteres        |
| `GROQ_API_KEY`    | Chave da API Groq (console.groq.com)   |
| `REDIS_URL`       | URL do Redis (redis://redis:6379)      |
| `META_DB_HOST`    | Host do PostgreSQL (postgres em Docker)|
| `META_DB_NAME`    | datahub_meta                           |
| `META_DB_USER`    | datahub_user                           |
| `META_DB_PASS`    | Senha do usuário datahub_user          |
| `FRONTEND_URL`    | URL do frontend (para CORS)            |

## Adicionar nova empresa

```sql
-- No banco datahub_meta
INSERT INTO empresas (slug, nome, db_host, db_name, db_user, db_pass)
VALUES ('nova', 'Empresa Nova', 'postgres', 'nova_db', 'nova_user', 'senha');

INSERT INTO usuario_empresas (usuario_id, empresa_id)
VALUES (1, (SELECT id FROM empresas WHERE slug = 'nova'));
```
Não é necessário reiniciar o backend — o pool é criado sob demanda.

## Migrações de banco

Não há um framework de migrations neste projeto — `scripts/init-db.sql` só roda automaticamente em um volume Postgres novo (instalação do zero). Para aplicar mudanças de schema em um banco `datahub_meta` já existente (staging/produção), rode o `ALTER TABLE` correspondente manualmente.

Mudanças aplicadas até agora:

```sql
-- Preferência de tema (claro/escuro) por usuário
ALTER TABLE usuarios ADD COLUMN tema VARCHAR(10) NOT NULL DEFAULT 'escuro';
```

## Deploy no EasyPanel

Pré-requisito: VPS com EasyPanel instalado e um PostgreSQL **nativo**
(fora de container) já rodando os bancos das empresas reais — esse
Postgres nativo não faz parte deste deploy, só precisa ficar acessível
pela rede interna do EasyPanel (ver passo 3).

### 1. Serviços a criar no projeto EasyPanel

| Serviço | Origem | Exposição |
|---|---|---|
| `postgres` | imagem `postgres:16-alpine` | interna |
| `redis` | imagem `redis:7-alpine` | interna |
| `backend` | `backend/Dockerfile` | interna |
| `worker` | mesma imagem do `backend`, comando sobrescrito: `python -m arq worker.WorkerSettings` | interna |
| `frontend` | `frontend/Dockerfile` | **pública**, domínio configurado no EasyPanel |

Só o `frontend` precisa de domínio público — o `nginx.conf` dele já faz
proxy de `/api/` para `backend:3001` internamente, então `backend` e
`worker` ficam só na rede interna do projeto. **O nome do serviço backend
no EasyPanel precisa ser `backend`** (é o hostname que o `nginx.conf`
resolve).

No serviço `postgres`, definir `POSTGRES_DB` como `datahub_meta`. Na
prática, o `POSTGRES_USER` não costuma ficar como `datahub_user` — o
deploy real neste projeto ficou só com a role padrão da imagem
`postgres:16-alpine`, que é **`postgres`**. Confirme com `\du` dentro do
terminal do serviço antes de assumir o nome da role.

### 2. Aplicar o schema no `datahub_meta`

Com o serviço `postgres` no ar, rodar `scripts/init-meta-prod.sql` contra
ele (via terminal do EasyPanel ou `psql` apontando pro serviço):

```bash
psql -U postgres -d datahub_meta -f scripts/init-meta-prod.sql
```

Esse script só cria a estrutura — sem empresas de demo, sem usuário.

**Importante se o banco `datahub_meta` já existe** (deploy anterior, banco
já em uso): `init-meta-prod.sql` é um `CREATE TABLE` completo — só ajuda
banco **novo**. Colunas adicionadas depois em dev (via `ALTER TABLE`
manual, refletido no script mas não em bancos de produção já criados)
precisam ser aplicadas manualmente. Ver "Deltas de schema pendentes"
abaixo antes de seguir pro passo 3.

#### Deltas de schema pendentes (aplicar se o banco já existe)

Rodar contra `datahub_meta` (via terminal do serviço `postgres` no
EasyPanel — `psql -U postgres -d datahub_meta` — ou `psql` externo
apontando pro serviço) qualquer item abaixo cuja coluna ainda não exista.
Verificar antes de aplicar:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'queries'
  AND column_name IN ('mapa_camada', 'chart_fonte_tamanho', 'chart_truncar_label', 'chart_truncar_tamanho', 'chart_mostrar_valor', 'chart_valor_label', 'impressao_habilitada', 'impressao_caminho', 'impressao_coluna', 'meta_habilitada', 'meta_coluna_valor', 'meta_coluna_inicio', 'meta_coluna_fim', 'meta_cor_dentro', 'meta_cor_fora', 'subquery_id');

SELECT column_name FROM information_schema.columns
WHERE table_name = 'empresas'
  AND column_name IN ('sso_api_key_hash', 'sso_query_acesso', 'url_impressao_base');

SELECT column_name FROM information_schema.columns
WHERE table_name = 'usuario_empresas'
  AND column_name = 'codigo_usuario_externo';

SELECT column_name FROM information_schema.columns
WHERE table_name = 'paineis'
  AND column_name IN ('imagem', 'imagem_mime');

SELECT table_name FROM information_schema.tables
WHERE table_name IN ('query_agrupamentos', 'query_agregacoes', 'query_subquery_parametros');
```

Rodar os itens abaixo cuja coluna não apareceu no resultado:

```sql
-- 2026-07-08 — tipo de camada do mapa (padrão/satélite) por query
ALTER TABLE queries ADD COLUMN mapa_camada VARCHAR(20) DEFAULT 'padrao';

-- 2026-07-08 — configuração de gráfico (fonte, truncar rótulo, mostrar valor) por query
ALTER TABLE queries ADD COLUMN chart_fonte_tamanho INTEGER DEFAULT 12;
ALTER TABLE queries ADD COLUMN chart_truncar_label BOOLEAN DEFAULT false;
ALTER TABLE queries ADD COLUMN chart_truncar_tamanho INTEGER DEFAULT 15;
ALTER TABLE queries ADD COLUMN chart_mostrar_valor BOOLEAN DEFAULT false;

-- 2026-07-08 — nome de exibição customizado pra série "valor" no gráfico
ALTER TABLE queries ADD COLUMN chart_valor_label VARCHAR(50);

-- 2026-07-26 — botão de impressão opcional em queries tipo table (link pro sistema legado de relatórios)
ALTER TABLE queries ADD COLUMN impressao_habilitada BOOLEAN DEFAULT false;
ALTER TABLE queries ADD COLUMN impressao_caminho TEXT;
ALTER TABLE queries ADD COLUMN impressao_coluna TEXT;

-- 2026-07-27 — coloração condicional de uma coluna por meta (início/fim), queries tipo table
ALTER TABLE queries ADD COLUMN meta_habilitada BOOLEAN DEFAULT false;
ALTER TABLE queries ADD COLUMN meta_coluna_valor TEXT;
ALTER TABLE queries ADD COLUMN meta_coluna_inicio TEXT;
ALTER TABLE queries ADD COLUMN meta_coluna_fim TEXT;
ALTER TABLE queries ADD COLUMN meta_cor_dentro TEXT DEFAULT '#3fb950';
ALTER TABLE queries ADD COLUMN meta_cor_fora TEXT DEFAULT '#f85149';

-- 2026-07-13 — hash da API key de SSO por empresa (app externo -> painel sem login)
ALTER TABLE empresas ADD COLUMN sso_api_key_hash VARCHAR(255);

-- 2026-07-13 — query configurável de acesso SSO por empresa (codigo_usuario -> lista de painel_slug)
ALTER TABLE empresas ADD COLUMN sso_query_acesso TEXT;

-- 2026-07-26 — URL base do sistema legado de impressão de relatórios, por empresa
ALTER TABLE empresas ADD COLUMN url_impressao_base TEXT;

-- 2026-07-16 — código do usuário no sistema da empresa, por vínculo usuário+empresa
-- (aplica o mesmo filtro codigo_usuario_externo do SSO pra usuários logados normalmente)
ALTER TABLE usuario_empresas ADD COLUMN codigo_usuario_externo TEXT;

-- 2026-07-31 — imagem de capa do painel guardada no banco (BYTEA), não em arquivo
ALTER TABLE paineis ADD COLUMN imagem BYTEA;
ALTER TABLE paineis ADD COLUMN imagem_mime TEXT;

-- 2026-08-18 — query tipo table_dynamic (agrupamento, agregação, subconsulta drill-down)
ALTER TABLE queries ADD COLUMN subquery_id INTEGER REFERENCES queries(id) ON DELETE SET NULL;

CREATE TABLE query_agrupamentos (
    id        SERIAL PRIMARY KEY,
    query_id  INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    coluna    TEXT NOT NULL,
    ordem     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qagrup_query_id ON query_agrupamentos(query_id);

CREATE TABLE query_agregacoes (
    id        SERIAL PRIMARY KEY,
    query_id  INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    coluna    TEXT NOT NULL,
    funcao    VARCHAR(10) NOT NULL,
    label     TEXT,
    ordem     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qagreg_query_id ON query_agregacoes(query_id);

CREATE TABLE query_subquery_parametros (
    id                SERIAL PRIMARY KEY,
    query_id          INTEGER REFERENCES queries(id) ON DELETE CASCADE,
    coluna_origem     TEXT NOT NULL,
    parametro_destino TEXT NOT NULL,
    ordem             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qsqp_query_id ON query_subquery_parametros(query_id);
```

Ao adicionar uma nova coluna em `queries` (ou outra tabela) no futuro,
inclua aqui o `ALTER TABLE` correspondente além de atualizar
`scripts/init-meta-prod.sql` — bancos de produção já criados só recebem a
mudança se alguém rodar isso manualmente.

### 3. Liberar o Postgres nativo do VPS para a rede do EasyPanel

Passo manual no VPS, fora do repositório:

1. `docker network inspect <rede-do-projeto-easypanel> | grep Subnet` —
   descobrir o subnet real (varia por instalação).
2. Confirmar que `listen_addresses` do Postgres nativo já aceita conexões
   nessa interface (provavelmente já inclui `*`, já que aceita conexão
   externa hoje).
3. Adicionar uma linha em `pg_hba.conf` liberando esse subnet
   especificamente (`scram-sha-256`) — **sem** abrir a porta 5432 pra
   internet além do IP fixo de manutenção já existente.
4. `systemctl restart postgresql` (ou reload).
5. Validar de dentro de um container do EasyPanel antes de seguir —
   regras de firewall (ufw) e o iptables do Docker podem se comportar
   diferente do esperado; testar com `psql` é a única forma de confirmar.

### 4. Variáveis de ambiente

**`backend` / `worker`:**

| Variável | Valor |
|---|---|
| `JWT_SECRET` | novo valor forte, gerado só para produção |
| `GROQ_API_KEY` | chave de produção |
| `REDIS_URL` | `redis://redis:6379` |
| `FRONTEND_URL` | `https://<seu-dominio>` |
| `META_DB_HOST` | `postgres` |
| `META_DB_PORT` | `5432` |
| `META_DB_NAME` | `datahub_meta` |
| `META_DB_USER` | `postgres` (role padrão da imagem — ver nota no passo 1) |
| `META_DB_PASS` | senha definida no serviço `postgres` |

**`frontend`:** não definir `VITE_API_URL` no build — fica vazio, e
`frontend/src/lib/api.js` usa caminhos relativos (`/api/...`), resolvidos
pelo `nginx.conf` do próprio container.

### 5. Confirmar que o backend subiu corretamente

Antes de criar o usuário admin, validar que o backend iniciou sem erros:

```bash
docker logs <container-do-backend>
```

Procurar pelas linhas (devem estar no final da saída):
```
✓ Conectado ao datahub_meta
✓ Conectado ao Redis
```

Alternativa ou complemento — testar o endpoint de health:
```bash
curl https://<seu-dominio>/api/health
```

Deve retornar `{"ok":true,"version":"1.0.0"}`. Se alguma dessas verificações falhar, revisar as variáveis de ambiente (passo 4), especialmente `META_DB_*` e `REDIS_URL`.

### 6. Criar o primeiro usuário admin

Com `backend` no ar:

```bash
docker exec <container-do-backend> python scripts/create_admin.py \
  --nome "Seu Nome" --email voce@empresa.com --senha "sua-senha-forte"
```

**Nota:** esse é um passo one-time de bootstrap. A senha será visível em shell history e process listings (`ps`, `docker top`, logs do EasyPanel); se o acesso ao VPS/EasyPanel é compartilhado, considere limpar o histórico do shell ou rotacionar a senha do admin após este passo inicial.

Rodar uma única vez. Rodar de novo com o mesmo email não duplica nem
sobrescreve (o script verifica antes de inserir).

### 7. Subir o frontend e cadastrar as empresas reais

Subir o serviço `frontend` com o domínio configurado (EasyPanel cuida do
SSL via Let's Encrypt automaticamente). Fazer login com o admin criado no
passo anterior e cadastrar as empresas reais (`prats`,
`vitoria-agronegocios` etc.) em `/configuracoes/empresas`, apontando pro
Postgres nativo do VPS (passo 3).
