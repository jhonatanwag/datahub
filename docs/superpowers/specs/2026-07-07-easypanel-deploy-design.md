# Design: Deploy do DataHub num VPS com EasyPanel

**Data:** 2026-07-07

## Problema

O projeto hoje só roda via `docker-compose.dev.yml` (hot-reload, bind-mount
do código, `Dockerfile.dev` sem `COPY`). Não há um caminho de produção
completo: falta Dockerfile de produção do backend, o schema SQL usado pra
inicializar o `datahub_meta` (`scripts/init-db.sql`) está desatualizado, e o
README tem só um esboço de 5 linhas do deploy no EasyPanel que assume peças
que não existem ainda.

## Ambiente de destino (confirmado com o usuário)

- VPS já tem EasyPanel instalado, acessível em `IP:3000` (porta do painel
  administrativo do EasyPanel — não conflita com os serviços do projeto).
- Porta 80 do host já é usada por um Apache pra outro serviço; a instalação
  do EasyPanel já foi feita de forma a não conflitar (Traefik do EasyPanel
  roteia por domínio/rede interna, não por porta fixa do host — fora do
  escopo deste documento).
- Existe um **PostgreSQL nativo no VPS** (fora de qualquer container) que já
  hospeda os bancos reais das empresas (`prats`, `vitoria_agro` etc.) — ver
  `empresas reais` em memória de projeto. Porta 5432 já exposta à internet,
  mas restrita por firewall a um IP fixo de manutenção; possivelmente também
  liberada localmente. Esses bancos **continuam onde estão** — não fazem
  parte deste deploy.
- O banco `datahub_meta` (painéis, usuários, queries do próprio sistema)
  **não existe em produção ainda** — vai ser um Postgres novo, gerenciado
  como serviço dentro do EasyPanel.
- Domínio único já disponível (não um IP nem subdomínio grátis) — vai
  servir tanto o frontend quanto, via proxy interno do nginx, a API.

## Escopo

Dentro do repositório, este trabalho cria/corrige:

1. `backend/Dockerfile` — build de produção (novo arquivo; hoje só existe
   `Dockerfile.dev`).
2. `scripts/init-meta-prod.sql` — schema **correto e atual** do
   `datahub_meta`, sem seed de demo (`alpha`/`beta`/`gamma`), gerado a partir
   do dump real do banco em dev (que inclui tabelas que `init-db.sql` nunca
   teve: `paineis`, `painel_indicadores`, `painel_variaveis`,
   `painel_usuarios`, `variaveis`).
3. `scripts/create_admin.py` — bootstrap do primeiro usuário admin em
   produção (hash bcrypt gerado localmente, sem senha fixa no SQL).
4. Atualização da seção "Deploy no EasyPanel" do `README.md`.

Fora do repositório (passos manuais no VPS, documentados mas não
automatizáveis por código):

- Criar os serviços no EasyPanel (postgres, redis, backend, worker,
  frontend) e configurar variáveis de ambiente.
- Ajustar `pg_hba.conf`/`listen_addresses` do Postgres nativo do VPS pra
  aceitar conexões da rede interna do Docker/EasyPanel.
- Configurar o domínio no serviço `frontend`.

Fora de escopo (não faz parte deste deploy):
- Migrar ou tocar nos bancos das empresas (`prats`, `vitoria_agro`) — eles
  já existem e continuam onde estão.
- Backup/monitoramento do Postgres novo — pode ser tratado depois, como
  melhoria separada.
- CI/CD automatizado (o deploy inicial é manual via UI do EasyPanel).

## Arquitetura

5 serviços dentro de um projeto `datahub` no EasyPanel:

| Serviço | Origem | Exposição |
|---|---|---|
| `postgres` | imagem `postgres:16-alpine`, volume próprio | interna (só `datahub_meta`) |
| `redis` | imagem `redis:7-alpine` | interna |
| `backend` | `backend/Dockerfile` (novo, produção) | interna |
| `worker` | mesma imagem do backend, comando sobrescrito (`python -m arq worker.WorkerSettings`) | interna |
| `frontend` | `frontend/Dockerfile` (já existe: build + nginx) | **pública**, domínio único |

O `frontend/nginx.conf` já faz `proxy_pass /api/ → backend:3001` — por isso
só o `frontend` precisa de domínio/SSL configurado no EasyPanel; `backend` e
`worker` ficam apenas na rede interna do projeto. Isso elimina CORS (mesma
origem) e mantém a superfície pública mínima.

**Premissa a validar no deploy:** o nome do serviço backend no EasyPanel
precisa ser exatamente `backend` (ou o `nginx.conf` precisa ser ajustado pra
bater com o nome real que o EasyPanel atribuir), já que o proxy resolve esse
hostname via DNS interno do Docker/Swarm.

## `backend/Dockerfile` (novo)

Baseado no `Dockerfile.dev`, removendo o hot-reload e adicionando `COPY` do
código (já que não há bind-mount em produção):

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

O serviço `worker` no EasyPanel usa essa mesma imagem, só sobrescrevendo o
`command` — sem Dockerfile próprio, igual ao que já está esboçado no README.

## `scripts/init-meta-prod.sql` (novo)

Schema-only do `datahub_meta`, extraído via `pg_dump --schema-only` do banco
de dev atual (fonte da verdade, já que reflete as migrações manuais
aplicadas depois do `init-db.sql`). Inclui as 11 tabelas atuais (`empresas`,
`usuarios`, `usuario_empresas`, `chat_historico`, `dashboard_layout`,
`queries`, `query_parametros`, `paineis`, `painel_indicadores`,
`painel_variaveis`, `painel_usuarios`, `variaveis`), sequences, índices,
foreign keys e a trigger `update_atualizado_em`. **Sem** `INSERT` de seed —
nem empresas demo, nem usuário admin (isso é papel do `create_admin.py`).

## `scripts/create_admin.py` (novo)

Script standalone (usa `bcrypt`, já em `requirements.txt`) que:
1. Pede nome, email e senha via input (ou argumentos de linha de comando).
2. Gera o hash bcrypt.
3. Conecta no `datahub_meta` de produção (via variáveis de ambiente
   `META_DB_*`, as mesmas que o backend usa) e insere o usuário com
   `role='admin'`.

Roda uma única vez, via `docker exec` no container do `backend` já em
produção, depois do schema estar aplicado.

## Rede: backend → Postgres nativo do VPS

Passo manual, documentado no README, **não automatizável** sem acesso ao
VPS:

1. Descobrir o subnet real da rede interna do EasyPanel:
   `docker network inspect <rede-easypanel> | grep Subnet`.
2. Confirmar `listen_addresses` do Postgres nativo (provavelmente já inclui
   `*`, já que aceita conexão externa hoje — só confirmar, não assumir).
3. Adicionar uma linha nova em `pg_hba.conf` liberando esse subnet
   especificamente (`scram-sha-256`), **sem** abrir a porta 5432 pro
   subnet inteiro via firewall público — só o `pg_hba.conf` do lado do
   Postgres.
4. `systemctl restart postgresql` (ou reload, se só mudou `pg_hba.conf`).
5. **Verificação obrigatória antes de seguir**: testar `psql` de dentro de
   um container do EasyPanel contra o IP do host — a regra de firewall do
   IP fixo de manutenção e o comportamento do Docker com iptables podem
   fazer esse acesso já funcionar, ou não; não dá pra confirmar sem testar
   no ambiente real.

## Variáveis de ambiente (configuradas na UI do EasyPanel, não em `.env`)

**`backend` / `worker`:**
- `JWT_SECRET` — novo valor forte, gerado especificamente pra produção
  (não reaproveitar o de dev)
- `GROQ_API_KEY`
- `REDIS_URL=redis://redis:6379`
- `FRONTEND_URL=https://<dominio-de-producao>`
- `META_DB_HOST=postgres` (nome do serviço novo no EasyPanel)
- `META_DB_PORT=5432`
- `META_DB_NAME=datahub_meta`
- `META_DB_USER` / `META_DB_PASS` (definidos na criação do serviço `postgres`)

**`frontend`:**
- **Não definir** `VITE_API_URL` no build — fica vazio, então
  `frontend/src/lib/api.js` (`BASE = import.meta.env.VITE_API_URL || ''`)
  usa caminhos relativos (`/api/...`), resolvidos pelo `nginx.conf` do
  próprio container.

## Ordem de deploy

1. Subir `postgres` + `redis` no EasyPanel.
2. Rodar `init-meta-prod.sql` no `postgres` novo (schema vazio).
3. Ajustar `pg_hba.conf`/`listen_addresses` no Postgres nativo do VPS;
   validar conexão de dentro de um container (ver seção de rede acima).
4. Subir `backend` + `worker`; checar `GET /api/health`.
5. Rodar `create_admin.py` uma vez.
6. Subir `frontend` com o domínio configurado no EasyPanel (SSL automático
   via Let's Encrypt).
7. Login com o admin recém-criado → cadastrar as empresas reais (`prats`,
   `vitoria-agronegocios`) na tela `/configuracoes/empresas`, apontando pro
   Postgres nativo do VPS.

## Testes / verificação

Sem framework de testes automatizado pra infraestrutura (consistente com o
resto do projeto — só `pytest` no backend, nada pra deploy). Verificação
manual, na ordem do deploy acima:

- `curl https://<dominio>/api/health` → `{"ok": true, ...}`.
- Login com o admin criado por `create_admin.py`, seleção de empresa.
- Cadastrar `prats` em `/configuracoes/empresas`, testar conexão (botão já
  existe no CRUD), abrir um painel e confirmar que os dados reais aparecem.
- Confirmar que `docker logs` do `worker` mostra o processo `arq` rodando
  sem erro de conexão com Redis/Postgres.
