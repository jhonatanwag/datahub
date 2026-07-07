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
