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

1. Criar projeto `datahub` no EasyPanel
2. Adicionar serviços: `redis` (imagem Redis), `backend` e `worker` (Dockerfile do /backend), `frontend` (Dockerfile do /frontend)
3. No serviço `worker`, sobrescrever comando: `python -m arq worker.WorkerSettings`
4. Configurar variáveis de ambiente no EasyPanel (não usar .env em produção)
5. Liberar acesso Docker no pg_hba.conf do PostgreSQL do VPS (range 172.17.0.0/16)
