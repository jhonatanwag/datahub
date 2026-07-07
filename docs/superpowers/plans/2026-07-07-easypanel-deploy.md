# Deploy no EasyPanel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar as peças de produção que faltam pra rodar o DataHub no
EasyPanel — Dockerfile de produção do backend, schema SQL correto e atual
do `datahub_meta`, script de bootstrap do admin, e documentação atualizada
do processo de deploy.

**Architecture:** 3 artefatos novos (`backend/Dockerfile`,
`scripts/init-meta-prod.sql`, `backend/scripts/create_admin.py`) + 1 seção
do README reescrita. Cada artefato é testado localmente com containers
Docker efêmeros antes de ser considerado pronto — nenhuma mudança depende
de acesso ao VPS real.

**Tech Stack:** Python 3.12 (FastAPI, asyncpg, bcrypt — já em
`backend/requirements.txt`), PostgreSQL 16, Docker.

## Global Constraints

- Não reaproveitar `JWT_SECRET` nem senhas de dev em produção (ver spec).
- `scripts/init-meta-prod.sql` não pode conter seed de demo (`alpha`/`beta`/`gamma`)
  nem usuário admin — só schema.
- `backend/scripts/create_admin.py` não grava senha em texto puro em lugar
  nenhum (só o hash bcrypt).
- `frontend` não deve ter `VITE_API_URL` setado no build de produção (ver spec) —
  isso já é verdade hoje (não é uma mudança deste plano, é uma constatação
  a documentar no README).
- Todo teste deste plano roda contra containers Docker locais e efêmeros —
  nada toca o VPS real nem os containers de dev (`datahub_backend`,
  `datahub_postgres` etc.) além de leitura.

---

### Task 1: `backend/Dockerfile` de produção

**Files:**
- Create: `backend/Dockerfile`

**Interfaces:**
- Produces: imagem Docker que expõe a porta `3001` e roda
  `uvicorn main:app --host 0.0.0.0 --port 3001` (sem `--reload`), consumida
  pelo serviço `backend` e pelo serviço `worker` (com comando sobrescrito)
  no EasyPanel. Task 3 reusa essa mesma imagem pra rodar
  `create_admin.py` dentro dela.

- [ ] **Step 1: Criar o Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3001"]
```

- [ ] **Step 2: Buildar a imagem localmente**

Run: `docker build -t datahub-backend-prod -f backend/Dockerfile backend`

Expected: build termina com `Successfully tagged datahub-backend-prod:latest`
(ou linha equivalente do BuildKit), sem erros de `pip install`.

- [ ] **Step 3: Rodar a imagem conectada à rede de dev e checar o health**

O stack de dev (`docker-compose.dev.yml`) já expõe `postgres` e `redis` por
esses nomes de serviço na rede `datahub_default`. Reaproveitar essa rede pra
testar a imagem nova sem subir infraestrutura extra:

Run:
```bash
docker run -d --name datahub_backend_prod_test \
  --network datahub_default \
  --env-file backend/.env.dev \
  -p 3011:3001 \
  datahub-backend-prod
```

Aguardar a subida (o `uvicorn` sem `--reload` inicia em poucos segundos):

Run: `docker logs datahub_backend_prod_test`

Expected: linhas `✓ Conectado ao datahub_meta`, `✓ Conectado ao Redis`,
`DataHub API v1.0.0 rodando na porta 3001` — **sem** nenhuma linha
mencionando "reloader" ou "watchfiles" (confirma que não há hot-reload
ativo, diferente do `Dockerfile.dev`).

- [ ] **Step 4: Checar o endpoint de health**

Run: `curl -s http://localhost:3011/api/health`

Expected: `{"ok":true,"version":"1.0.0"}`

- [ ] **Step 5: Limpar o container de teste**

Run: `docker rm -f datahub_backend_prod_test`

- [ ] **Step 6: Commit**

```bash
git add backend/Dockerfile
git commit -m "feat: add production Dockerfile for backend"
```

---

### Task 2: `scripts/init-meta-prod.sql` — schema de produção do `datahub_meta`

**Files:**
- Create: `scripts/init-meta-prod.sql`

**Interfaces:**
- Produces: script SQL idempotente-por-execução-única (não usa
  `IF NOT EXISTS`, assume banco vazio) que cria as 11 tabelas atuais do
  `datahub_meta` num banco `datahub_meta` já existente (criado pelas
  variáveis `POSTGRES_USER`/`POSTGRES_DB` do serviço `postgres` no
  EasyPanel — não cria usuário nem database).
- Consumido manualmente (via `psql -f`) na Task 3 (que aplica esse mesmo
  schema pra testar `create_admin.py`) e no passo 2 da ordem de deploy da
  spec.

- [ ] **Step 1: Criar o arquivo de schema**

```sql
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
```

- [ ] **Step 2: Subir um Postgres efêmero pra testar o script**

Run:
```bash
docker run -d --name datahub_meta_schema_test \
  -e POSTGRES_USER=datahub_user \
  -e POSTGRES_PASSWORD=test123 \
  -e POSTGRES_DB=datahub_meta \
  postgres:16-alpine
```

Aguardar o container ficar pronto (checagem em loop, não `sleep` cego):

Run:
```bash
for i in $(seq 1 15); do
  docker exec datahub_meta_schema_test pg_isready -U datahub_user -d datahub_meta && break
  sleep 1
done
```

Expected: eventualmente imprime `... - accepting connections`.

- [ ] **Step 3: Aplicar o schema**

Run:
```bash
docker cp scripts/init-meta-prod.sql datahub_meta_schema_test:/tmp/init-meta-prod.sql
docker exec datahub_meta_schema_test psql -U datahub_user -d datahub_meta -f /tmp/init-meta-prod.sql
```

Expected: sequência de `CREATE FUNCTION`, `CREATE TABLE`, `CREATE INDEX`,
`CREATE TRIGGER` sem nenhum `ERROR`.

- [ ] **Step 4: Confirmar as 11 tabelas**

Run:
```bash
docker exec datahub_meta_schema_test psql -U datahub_user -d datahub_meta -c "\dt" -t | wc -l
```

Expected: `11`.

- [ ] **Step 5: Confirmar que a trigger existe e funciona**

Run:
```bash
docker exec datahub_meta_schema_test psql -U datahub_user -d datahub_meta -c "
INSERT INTO paineis (slug, nome) VALUES ('teste', 'Teste');
SELECT atualizado_em = criado_em AS igual_na_criacao FROM paineis WHERE slug = 'teste';
UPDATE paineis SET nome = 'Teste 2' WHERE slug = 'teste';
SELECT atualizado_em > criado_em AS mudou_apos_update FROM paineis WHERE slug = 'teste';
"
```

Expected: primeira consulta retorna `t` (igual na criação), segunda
retorna `t` (mudou após update) — confirma que
`trg_paineis_updated` está disparando.

- [ ] **Step 6: Limpar o container de teste**

Run: `docker rm -f datahub_meta_schema_test`

- [ ] **Step 7: Commit**

```bash
git add scripts/init-meta-prod.sql
git commit -m "feat: add production schema script for datahub_meta"
```

---

### Task 3: `backend/scripts/create_admin.py` — bootstrap do usuário admin

**Files:**
- Create: `backend/scripts/create_admin.py`

**Interfaces:**
- Consumes: `config.settings.settings` (Task já existente em
  `backend/config/settings.py` — campos `META_DB_HOST`, `META_DB_PORT`,
  `META_DB_NAME`, `META_DB_USER`, `META_DB_PASS`), tabela `usuarios`
  criada pela Task 2 (`scripts/init-meta-prod.sql`), imagem
  `datahub-backend-prod` da Task 1 (é onde o script roda em produção via
  `docker exec`).
- Produces: script de linha de comando
  `python scripts/create_admin.py --nome NOME --email EMAIL --senha SENHA`
  (executado com `WORKDIR /app` = raiz do backend dentro do container).

- [ ] **Step 1: Criar o script**

```python
import argparse
import asyncio

import asyncpg
import bcrypt

from config.settings import settings


async def criar_admin(nome: str, email: str, senha: str) -> None:
    conn = await asyncpg.connect(
        host=settings.META_DB_HOST,
        port=settings.META_DB_PORT,
        database=settings.META_DB_NAME,
        user=settings.META_DB_USER,
        password=settings.META_DB_PASS,
    )
    try:
        existente = await conn.fetchrow(
            "SELECT id FROM usuarios WHERE email = $1", email
        )
        if existente:
            print(f"Usuário com email '{email}' já existe (id={existente['id']}). Nada foi alterado.")
            return

        senha_hash = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
        row = await conn.fetchrow(
            """
            INSERT INTO usuarios (nome, email, senha_hash, role)
            VALUES ($1, $2, $3, 'admin')
            RETURNING id
            """,
            nome, email, senha_hash,
        )
        print(f"Usuário admin '{email}' criado com id={row['id']}.")
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Cria o usuário admin inicial do DataHub em produção."
    )
    parser.add_argument("--nome", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--senha", required=True)
    args = parser.parse_args()

    asyncio.run(criar_admin(args.nome, args.email, args.senha))
```

- [ ] **Step 2: Subir um Postgres efêmero com o schema aplicado**

Run:
```bash
docker network create datahub_admin_test_net

docker run -d --name datahub_meta_admin_test \
  --network datahub_admin_test_net \
  -e POSTGRES_USER=datahub_user \
  -e POSTGRES_PASSWORD=test123 \
  -e POSTGRES_DB=datahub_meta \
  postgres:16-alpine

for i in $(seq 1 15); do
  docker exec datahub_meta_admin_test pg_isready -U datahub_user -d datahub_meta && break
  sleep 1
done

docker cp scripts/init-meta-prod.sql datahub_meta_admin_test:/tmp/init-meta-prod.sql
docker exec datahub_meta_admin_test psql -U datahub_user -d datahub_meta -f /tmp/init-meta-prod.sql
```

Expected: mesmo resultado do Step 3 da Task 2 (schema aplicado sem erro).

- [ ] **Step 3: Buildar a imagem do backend com o script incluído**

O `backend/Dockerfile` da Task 1 já faz `COPY . .`, então
`backend/scripts/create_admin.py` entra automaticamente na imagem:

Run: `docker build -t datahub-backend-prod -f backend/Dockerfile backend`

Expected: build com sucesso (mesma expectativa da Task 1, Step 2).

- [ ] **Step 4: Rodar o script contra o Postgres efêmero**

Run:
```bash
docker run --rm \
  --network datahub_admin_test_net \
  -e JWT_SECRET=teste_apenas_para_este_teste_local_32chars \
  -e GROQ_API_KEY=x \
  -e META_DB_HOST=datahub_meta_admin_test \
  -e META_DB_PORT=5432 \
  -e META_DB_NAME=datahub_meta \
  -e META_DB_USER=datahub_user \
  -e META_DB_PASS=test123 \
  datahub-backend-prod \
  python scripts/create_admin.py --nome "Admin Teste" --email admin@teste.local --senha senha_forte_123
```

Expected: `Usuário admin 'admin@teste.local' criado com id=1.`

- [ ] **Step 5: Confirmar o hash bcrypt é válido e a senha em claro não foi gravada**

Run:
```bash
docker exec datahub_meta_admin_test psql -U datahub_user -d datahub_meta -t -c \
  "SELECT senha_hash FROM usuarios WHERE email = 'admin@teste.local'"
```

Expected: uma string começando com `$2b$` (formato bcrypt), **diferente**
de `senha_forte_123` em texto puro.

- [ ] **Step 6: Confirmar idempotência (rodar de novo com o mesmo email)**

Run:
```bash
docker run --rm \
  --network datahub_admin_test_net \
  -e JWT_SECRET=teste_apenas_para_este_teste_local_32chars \
  -e GROQ_API_KEY=x \
  -e META_DB_HOST=datahub_meta_admin_test \
  -e META_DB_PORT=5432 \
  -e META_DB_NAME=datahub_meta \
  -e META_DB_USER=datahub_user \
  -e META_DB_PASS=test123 \
  datahub-backend-prod \
  python scripts/create_admin.py --nome "Admin Teste" --email admin@teste.local --senha outra_senha
```

Expected: `Usuário com email 'admin@teste.local' já existe (id=1). Nada foi alterado.`
— confirma que rodar o script duas vezes por engano não duplica nem
sobrescreve o usuário.

- [ ] **Step 7: Limpar containers e rede de teste**

Run:
```bash
docker rm -f datahub_meta_admin_test
docker network rm datahub_admin_test_net
```

- [ ] **Step 8: Commit**

```bash
git add backend/scripts/create_admin.py
git commit -m "feat: add production admin bootstrap script"
```

---

### Task 4: Atualizar a seção "Deploy no EasyPanel" do README

**Files:**
- Modify: `README.md` (seção "Deploy no EasyPanel", ao final do arquivo)

**Interfaces:**
- Consumes: os 3 artefatos das Tasks 1–3 (`backend/Dockerfile`,
  `scripts/init-meta-prod.sql`, `backend/scripts/create_admin.py`) — a
  documentação referencia os caminhos exatos.

- [ ] **Step 1: Substituir a seção existente**

A seção atual (5 linhas, no fim do `README.md`) assume peças que não
existiam. Substituir por:

```markdown
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

No serviço `postgres`, definir `POSTGRES_USER` e `POSTGRES_DB` como
`datahub_user` / `datahub_meta` — a própria imagem cria o banco e o
usuário na primeira subida.

### 2. Aplicar o schema no `datahub_meta`

Com o serviço `postgres` no ar, rodar `scripts/init-meta-prod.sql` contra
ele (via terminal do EasyPanel ou `psql` apontando pro serviço). Esse
script só cria a estrutura — sem empresas de demo, sem usuário.

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
| `META_DB_USER` | `datahub_user` |
| `META_DB_PASS` | senha definida no serviço `postgres` |

**`frontend`:** não definir `VITE_API_URL` no build — fica vazio, e
`frontend/src/lib/api.js` usa caminhos relativos (`/api/...`), resolvidos
pelo `nginx.conf` do próprio container.

### 5. Criar o primeiro usuário admin

Com `backend` no ar:

```bash
docker exec <container-do-backend> python scripts/create_admin.py \
  --nome "Seu Nome" --email voce@empresa.com --senha "sua-senha-forte"
```

Rodar uma única vez. Rodar de novo com o mesmo email não duplica nem
sobrescreve (o script verifica antes de inserir).

### 6. Subir o frontend e cadastrar as empresas reais

Subir o serviço `frontend` com o domínio configurado (EasyPanel cuida do
SSL via Let's Encrypt automaticamente). Fazer login com o admin criado no
passo anterior e cadastrar as empresas reais (`prats`,
`vitoria-agronegocios` etc.) em `/configuracoes/empresas`, apontando pro
Postgres nativo do VPS (passo 3).
```

- [ ] **Step 2: Conferir que os blocos de código fecham corretamente**

Run: `grep -c '```' README.md`

Expected: número par (cada bloco aberto tem um fechamento correspondente).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document full EasyPanel production deploy process"
```
