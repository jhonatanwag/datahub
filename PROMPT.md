# PROMPT.md — Briefing de Desenvolvimento para Claude Code
## Projeto: DataHub — Analytics Multiempresa
## Leia este arquivo inteiro antes de escrever qualquer código.

---

## REGRAS DE TRABALHO

1. **Siga a ordem exata** das fases abaixo. Não pule etapas.
2. **Pause e pergunte** sempre que ver a tag `[PERGUNTAR]`.
3. **Teste cada fase** antes de avançar para a próxima.
4. **Nunca invente** nomes de tabelas, colunas ou senhas — use placeholders explícitos quando não souber.
5. **Um arquivo de cada vez** — crie, verifique, depois avance.
6. Leia o arquivo `arquitetura-stack-final.md` como referência técnica durante todo o desenvolvimento.

---

## CONTEXTO DO PROJETO

Sistema de analytics multiempresa instalado em VPS com EasyPanel.
Cada empresa tem seu próprio banco PostgreSQL (usuário e banco separados).
Um banco central (`datahub_meta`) controla usuários, empresas e histórico.
Cache com Redis. Chatbot com Groq (LLaMA 3, gratuito). Worker assíncrono com ARQ.

**Stack:**
- Frontend: SvelteKit + ECharts + Leaflet
- Backend: Python 3.12 + FastAPI + asyncpg
- Cache: Redis
- Fila: ARQ
- IA: Groq SDK (LLaMA 3.3 70b)
- Deploy: EasyPanel (Docker)

---

## FASE 1 — ESTRUTURA DE PASTAS

Crie exatamente esta estrutura. Não crie arquivos ainda, só as pastas:

```
datahub/
├── backend/
│   ├── config/
│   ├── routes/
│   ├── middleware/
│   └── services/
└── frontend/
    └── src/
        ├── routes/
        └── lib/
            ├── components/
            ├── stores/
            └── services/
```

Após criar, liste a estrutura e confirme antes de continuar.

---

## FASE 2 — BANCO DATAHUB_META

Crie o arquivo: `backend/sql/01_datahub_meta.sql`

O arquivo deve conter, nesta ordem:
1. `CREATE DATABASE datahub_meta;`
2. `CREATE USER datahub_user WITH PASSWORD 'TROCAR_SENHA_AQUI';`
3. `GRANT ALL PRIVILEGES ON DATABASE datahub_meta TO datahub_user;`
4. Comando `\c datahub_meta`
5. Todas as tabelas na ordem: `empresas` → `usuarios` → `usuario_empresas` → `chat_historico` → `tarefas`
6. Índices de performance nas tabelas `chat_historico` e `tarefas`
7. `INSERT` de exemplo para 3 empresas com host `172.17.0.1` e senhas `TROCAR_SENHA_AQUI`
8. `INSERT` de um usuário admin de exemplo com senha hasheada (use pgcrypt ou deixe placeholder comentado)

[PERGUNTAR] Quais são os nomes reais dos bancos, usuários e empresas que devo cadastrar nos INSERTs?

Após receber a resposta, preencha os INSERTs com os dados reais e mostre o SQL completo para aprovação antes de continuar.

---

## FASE 3 — BACKEND: ARQUIVOS DE CONFIGURAÇÃO

Crie nesta ordem:

### 3.1 `backend/requirements.txt`
Copie exatamente do `arquitetura-stack-final.md`, seção requirements.txt.

### 3.2 `backend/.env.example`
```env
# Copie para .env e preencha os valores reais
JWT_SECRET=
GROQ_API_KEY=
REDIS_URL=redis://redis:6379
FRONTEND_URL=https://app.seu-dominio.com.br

META_DB_HOST=172.17.0.1
META_DB_PORT=5432
META_DB_NAME=datahub_meta
META_DB_USER=datahub_user
META_DB_PASS=
```

### 3.3 `backend/.gitignore`
```
.env
__pycache__/
*.pyc
*.pyo
.pytest_cache/
```

### 3.4 `backend/config/settings.py`
Copie do `arquitetura-stack-final.md`.

### 3.5 `backend/config/databases.py`
Copie do `arquitetura-stack-final.md`.

### 3.6 `backend/config/redis.py`
Copie do `arquitetura-stack-final.md`.

Após criar os 6 arquivos, liste-os com `ls -la backend/config/` e confirme.

---

## FASE 4 — BACKEND: SERVICES

Crie nesta ordem:

### 4.1 `backend/services/cache.py`
Copie do `arquitetura-stack-final.md`.

### 4.2 `backend/services/groq_client.py`
Copie do `arquitetura-stack-final.md`.

### 4.3 `backend/services/rag.py`
Copie do `arquitetura-stack-final.md`.

[PERGUNTAR] Quais são os nomes das tabelas e colunas principais nos bancos das empresas?
Preciso saber no mínimo:
- Nome da tabela de pedidos/vendas/transações
- Coluna de valor/preço
- Coluna de data
- Coluna de cliente (id ou nome)
- Coluna de produto/serviço (se existir)

Aguarde a resposta antes de finalizar o `rag.py`. Substitua os nomes de tabelas/colunas nos CONTEXT_QUERIES com os valores reais informados.

---

## FASE 5 — BACKEND: MIDDLEWARE

### 5.1 `backend/middleware/__init__.py`
Arquivo vazio.

### 5.2 `backend/middleware/auth.py`
Copie do `arquitetura-stack-final.md`.

---

## FASE 6 — BACKEND: ROTAS

Crie nesta ordem. Cada rota deve ter tratamento de erro com `try/except` e retornar mensagens claras.

### 6.1 `backend/routes/__init__.py`
Arquivo vazio.

### 6.2 `backend/routes/auth.py`
Implemente com:
- `POST /api/auth/login` — recebe `email`, `senha`, `company_slug`; valida no `datahub_meta`; retorna JWT com payload `{user_id, company_slug, empresa_id, role}`
- `GET /api/auth/me` — retorna dados do usuário logado (requer token)
- `POST /api/auth/logout` — invalida token no Redis (blacklist por TTL)
- Use `bcrypt` para verificar senha
- JWT expira conforme `settings.JWT_EXPIRE_MINUTES`

### 6.3 `backend/routes/charts.py`
Copie do `arquitetura-stack-final.md`.

[PERGUNTAR] Além de KPIs e receita mensal, quais outros gráficos você quer?
Exemplos: top produtos, pedidos por status, vendas por região, comparativo de metas.
Liste os gráficos desejados e as informações que cada um deve mostrar.

### 6.4 `backend/routes/tables.py`
Implemente com:
- `GET /api/tables/pedidos` — lista paginada (parâmetros: `page`, `limit`, `status`, `data_inicio`, `data_fim`)
- Ordenação por data decrescente
- Retorna `{items: [...], total: int, page: int, pages: int}`

[PERGUNTAR] Quais colunas devem aparecer na tabela de pedidos do dashboard?

### 6.5 `backend/routes/ai.py`
Copie do `arquitetura-stack-final.md`.

### 6.6 `backend/routes/reports.py`
Implemente com:
- `POST /api/reports/solicitar` — cria registro na tabela `tarefas` e enfileira no ARQ
- `GET /api/reports/status/{tarefa_id}` — retorna status da tarefa
- `GET /api/reports/resultado/{tarefa_id}` — retorna resultado quando concluído

### 6.7 `backend/main.py`
Copie do `arquitetura-stack-final.md` e adicione:
- Evento `startup` que testa conexão com Redis e `datahub_meta`
- Evento `shutdown` que fecha todos os pools asyncpg
- Log de inicialização com versão e porta

### 6.8 `backend/worker.py`
Copie do `arquitetura-stack-final.md`.

---

## FASE 7 — BACKEND: DOCKERFILE

### 7.1 `backend/Dockerfile`
Copie do `arquitetura-stack-final.md`.

### 7.2 Teste local do backend (se tiver Python instalado):
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 3001
```
Acesse `http://localhost:3001/docs` — a documentação automática deve aparecer.
Se der erro de conexão com banco/Redis, é esperado neste momento. O que não pode dar erro: importações e inicialização da aplicação.

---

## FASE 8 — FRONTEND: SVELTEKIT

### 8.1 Inicializar o projeto
```bash
cd frontend
npm create svelte@latest . -- --template skeleton --types none --no-prettier --no-eslint
npm install
npm install echarts leaflet
```

### 8.2 `frontend/.env.example`
```env
VITE_API_URL=https://api.seu-dominio.com.br
```

### 8.3 `frontend/src/lib/api.js`
Copie do `arquitetura-stack-final.md`.

### 8.4 `frontend/src/lib/stores/company.js`
Copie do `arquitetura-stack-final.md`.

### 8.5 `frontend/src/app.css`
Implemente as variáveis CSS e estilos base:
- Background: `#0d1117`
- Surface: `#161b22`
- Border: `#21262d`
- Text: `#e6edf3`
- Muted: `#7d8590`
- Accent principal: `#f78166`
- Accent azul: `#79c0ff`
- Accent verde: `#56d364`
- Accent roxo: `#d2a8ff`
- Fonte display: IBM Plex Mono (Google Fonts)
- Fonte corpo: Inter (Google Fonts)

### 8.6 Componentes — criar nesta ordem:

**`frontend/src/lib/components/KPICards.svelte`**
- Recebe prop `kpis: {receita, pedidos, ticket_medio, clientes}`
- 4 cards em grid, cada um com label, valor formatado e delta colorido
- Valores monetários: `Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'})`

**`frontend/src/lib/components/ChartPanel.svelte`**
- Recebe prop `tipo: string` e `dados: array`
- Usa ECharts
- Suporta tipos: `line`, `bar`, `bar-horizontal`, `doughnut`
- Tema escuro (background transparente, cores do design system)

**`frontend/src/lib/components/MapPanel.svelte`**
- Usa Leaflet
- Tile escuro: `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png`
- Recebe prop `pontos: [{lat, lng, valor, label}]`
- Marcadores circulares com tamanho proporcional ao valor

**`frontend/src/lib/components/DataTable.svelte`**
- Recebe props: `colunas: array`, `dados: array`, `total: int`, `page: int`
- Paginação simples (anterior / próxima)
- Emite evento `on:page` ao mudar página
- Suporte a slot para células customizadas (status com dot colorido)

**`frontend/src/lib/components/AIChat.svelte`**
- Input de pergunta + botão enviar
- Histórico de mensagens (usuário + assistente) exibido acima
- Estado de loading com texto animado
- Chama `api.perguntarIA(pergunta)`
- Salva histórico no `localStorage` como fallback

### 8.7 `frontend/src/routes/+layout.svelte`
Implemente:
- Sidebar com navegação (Dashboard, Gráficos, Mapa, Relatórios, IA)
- Seletor de empresa no topo da sidebar (lê do store `empresa`)
- Topbar com título da página e botão de período (7d, 30d, 90d, 1a)
- Guard de autenticação: redireciona para `/login` se não houver token
- Responsivo: sidebar colapsável em telas menores

### 8.8 `frontend/src/routes/+page.svelte`
Dashboard principal:
- Carrega KPIs, receita mensal e pedidos recentes ao montar
- Usa `KPICards`, `ChartPanel` (line + bar), `MapPanel`, `DataTable`
- Skeleton loading enquanto dados carregam
- Tratamento de erro com mensagem amigável

### 8.9 `frontend/src/routes/login/+page.svelte`
Página de login:
- Campos: email, senha, empresa (dropdown)
- Chama `api.login()`, salva token no `localStorage` e no store
- Redireciona para `/` após login
- Mensagem de erro se credenciais inválidas

### 8.10 `frontend/src/routes/ai/+page.svelte`
Página dedicada ao chatbot:
- Usa `AIChat.svelte`
- Mostra histórico das últimas 20 perguntas (carrega de `api.historicoIA()`)

---

## FASE 9 — FRONTEND: DOCKERFILE

### 9.1 `frontend/Dockerfile`
Copie do `arquitetura-stack-final.md`.

### 9.2 `frontend/nginx.conf`
Copie do `arquitetura-stack-final.md`.

### 9.3 Teste local do frontend:
```bash
cd frontend
npm run dev
```
Acesse `http://localhost:5173` — a tela de login deve aparecer.

---

## FASE 10 — DOCKER COMPOSE (DESENVOLVIMENTO LOCAL)

Crie `datahub/docker-compose.dev.yml` para rodar tudo localmente:

```yaml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  backend:
    build: ./backend
    ports: ["3001:3001"]
    env_file: ./backend/.env
    depends_on: [redis]
    volumes:
      - ./backend:/app  # hot reload em dev

  worker:
    build: ./backend
    command: python -m arq worker.WorkerSettings
    env_file: ./backend/.env
    depends_on: [redis]

  frontend:
    build: ./frontend
    ports: ["3000:80"]
    depends_on: [backend]
```

Teste com:
```bash
docker compose -f docker-compose.dev.yml up --build
```

---

## FASE 11 — GITIGNORE RAIZ

Crie `datahub/.gitignore`:
```
# Env
**/.env
!**/.env.example

# Python
__pycache__/
*.pyc
.pytest_cache/

# Node
node_modules/
frontend/build/
frontend/.svelte-kit/

# Docker
*.log
```

---

## FASE 12 — README.md DO PROJETO

Crie `datahub/README.md` com:
1. Descrição do projeto (2 parágrafos)
2. Pré-requisitos (Docker, EasyPanel, Groq API key)
3. Como rodar localmente (comandos exatos)
4. Como fazer deploy no EasyPanel (resumo das fases 7 e 8 do `arquitetura-stack-final.md`)
5. Como adicionar nova empresa (copie do `arquitetura-stack-final.md`, seção 9)
6. Variáveis de ambiente necessárias (lista completa)

---

## PONTOS DE PARADA OBRIGATÓRIOS

Antes de finalizar o desenvolvimento, pergunte sobre:

```
[PERGUNTAR 1] — FASE 2
Nomes reais das empresas, bancos e usuários PostgreSQL.

[PERGUNTAR 2] — FASE 4
Nomes das tabelas e colunas nos bancos das empresas
(tabela de pedidos, colunas de valor, data, cliente, produto).

[PERGUNTAR 3] — FASE 6.3
Quais gráficos adicionais além de KPIs e receita mensal.

[PERGUNTAR 4] — FASE 6.4
Quais colunas mostrar na tabela de pedidos.
```

---

## CHECKLIST FINAL

Antes de considerar o desenvolvimento concluído, verifique:

- [ ] `datahub/.gitignore` — `.env` está listado
- [ ] `backend/.env.example` existe e `.env` NÃO está no git
- [ ] Todas as rotas têm `try/except` com log do erro
- [ ] `rag.py` usa nomes de tabelas/colunas reais (não placeholders)
- [ ] `docker-compose.dev.yml` sobe sem erros
- [ ] `http://localhost:3001/docs` abre a documentação FastAPI
- [ ] `http://localhost:5173` abre a tela de login
- [ ] Login funciona e redireciona para o dashboard
- [ ] KPIs carregam (mesmo que zerados, sem erro 500)
- [ ] Chatbot responde (mesmo sem dados, sem erro 500)
- [ ] `README.md` tem todos os comandos necessários para outro dev subir o projeto
