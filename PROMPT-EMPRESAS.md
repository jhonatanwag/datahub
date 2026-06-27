# PROMPT-EMPRESAS.md — Implementação do Fluxo de Empresas
## Leia este arquivo inteiro antes de escrever qualquer código.

---

## CONTEXTO

O projeto DataHub já tem estrutura base criada.
O banco `datahub_meta` já existe com dados fictícios.
O que falta implementar é o fluxo completo de autenticação
e seleção de empresa, além da tela de configurações para o admin.

---

## REGRAS

1. Não apague código que já está funcionando.
2. Siga a ordem exata das fases.
3. Pause e pergunte se encontrar algo diferente do esperado.
4. Teste cada fase antes de avançar.

---

## FLUXO OBRIGATÓRIO DO SISTEMA

```
[1] Tela de Login
    usuário digita e-mail + senha
          ↓
[2] Backend valida no datahub_meta
    busca o usuário e verifica senha (bcrypt)
          ↓
[3] Tela de Seleção de Empresa
    mostra APENAS as empresas vinculadas ao usuário
    (tabela usuario_empresas)
    usuário NÃO vê empresas de outros usuários
          ↓
[4] Usuário clica em uma empresa
    backend gera JWT com {user_id, empresa_id, company_slug}
          ↓
[5] Dashboard
    carrega dados do banco da empresa selecionada
```

---

## FASE 1 — VERIFICAR O QUE JÁ EXISTE

Antes de criar qualquer arquivo, execute:

```bash
# Ver estrutura atual do projeto
find . -type f -name "*.py" | head -30
find . -type f -name "*.svelte" | head -30

# Ver tabelas do datahub_meta
docker exec -it datahub_postgres psql -U postgres -d datahub_meta -c "\dt"

# Ver dados existentes
docker exec -it datahub_postgres psql -U postgres -d datahub_meta -c "SELECT * FROM empresas;"
docker exec -it datahub_postgres psql -U postgres -d datahub_meta -c "SELECT id, nome, email, role FROM usuarios;"
docker exec -it datahub_postgres psql -U postgres -d datahub_meta -c "SELECT * FROM usuario_empresas;"
```

Mostre o resultado antes de continuar.

[PERGUNTAR] O que já existe implementado no backend (rotas) e no frontend (páginas)?
Liste os arquivos encontrados para eu saber o que reaproveitar.

---

## FASE 2 — BACKEND: ROTA DE LOGIN

### 2.1 Verificar/criar `backend/routes/auth.py`

A rota de login deve:
- Receber `email` e `senha`
- Buscar usuário no `datahub_meta`
- Verificar senha com `bcrypt`
- Retornar lista de empresas que o usuário tem acesso
- NÃO gerar JWT ainda — JWT só é gerado após selecionar a empresa

```python
# POST /api/auth/login
# Body: { "email": "...", "senha": "..." }
# Retorno: {
#   "user_id": 1,
#   "nome": "João",
#   "empresas": [
#     { "id": 1, "slug": "alpha", "nome": "Empresa Alpha", "logo_url": null },
#     { "id": 2, "slug": "beta",  "nome": "Empresa Beta",  "logo_url": null }
#   ]
# }
# IMPORTANTE: não retorna token ainda
```

### 2.2 Rota de seleção de empresa

```python
# POST /api/auth/selecionar-empresa
# Body: { "user_id": 1, "empresa_id": 1 }
# Valida que o usuário realmente tem acesso àquela empresa
# Retorna JWT com payload: { user_id, empresa_id, company_slug, nome, role }
```

### 2.3 Rota de empresas do usuário logado

```python
# GET /api/auth/minhas-empresas
# Requer JWT válido
# Retorna lista de empresas do usuário (para trocar de empresa sem relogar)
```

### 2.4 Rota para testar conexão com banco

```python
# POST /api/empresas/testar-conexao
# Body: { host, port, database, user, password }
# Tenta conectar via asyncpg
# Retorna { ok: true } ou { ok: false, erro: "mensagem" }
# Requer role: admin
```

---

## FASE 3 — BACKEND: CRUD DE EMPRESAS (admin)

### 3.1 `backend/routes/empresas.py`

Implemente as rotas abaixo. Todas requerem `role: admin`.

```
GET    /api/empresas/          → lista todas as empresas
GET    /api/empresas/{id}      → busca empresa por ID
POST   /api/empresas/          → cadastra nova empresa
PATCH  /api/empresas/{id}      → atualiza empresa
DELETE /api/empresas/{id}      → desativa empresa (ativo=false, não apaga)
POST   /api/empresas/testar-conexao → testa conexão com o banco
POST   /api/empresas/{id}/logo → upload de logo (salva em /data/logos/)
```

### Modelo de empresa:

```python
class EmpresaInput(BaseModel):
    slug: str           # identificador único ex: 'alpha'
    nome: str           # nome exibido ex: 'Empresa Alpha Ltda'
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_pass: str
    ativo: bool = True
```

### Regras importantes:
- `slug` deve ser único e sem espaços
- Ao cadastrar, sempre testar a conexão antes de salvar
- Logo salva em `/data/logos/{empresa_id}.png`
- Se deletar empresa, setar `ativo=false` — nunca apagar do banco

---

## FASE 4 — BACKEND: CRUD DE USUÁRIOS (admin)

### 4.1 `backend/routes/usuarios.py`

```
GET    /api/usuarios/                    → lista usuários
POST   /api/usuarios/                    → cadastra usuário
PATCH  /api/usuarios/{id}               → atualiza usuário
DELETE /api/usuarios/{id}               → desativa usuário
POST   /api/usuarios/{id}/empresas      → vincula empresas ao usuário
GET    /api/usuarios/{id}/empresas      → lista empresas do usuário
DELETE /api/usuarios/{id}/empresas/{empresa_id} → remove vínculo
```

### Modelo:
```python
class UsuarioInput(BaseModel):
    nome: str
    email: str
    senha: str
    role: str = 'viewer'   # 'admin' ou 'viewer'
    ativo: bool = True
```

### Regras:
- Senha sempre hasheada com bcrypt antes de salvar
- Email único no sistema
- Admin não pode desativar a si mesmo
- Ao criar usuário, já vincular às empresas desejadas

---

## FASE 5 — FRONTEND: TELA DE LOGIN

### `frontend/src/routes/login/+page.svelte`

**Layout:**
- Tela centralizada, fundo escuro (#0d1117)
- Logo do DataHub no topo
- Card branco/surface com formulário
- Campos: E-mail + Senha
- Botão "Entrar"
- Sem seletor de empresa — empresa é escolhida DEPOIS

**Comportamento:**
1. Usuário preenche e-mail e senha
2. Chama `POST /api/auth/login`
3. Se credenciais inválidas → mensagem de erro
4. Se válidas → salva `user_id` e `nome` temporariamente
5. Redireciona para `/selecionar-empresa`

**NÃO deve ter:**
- Campo de empresa
- Link de cadastro (sistema fechado)
- "Esqueci minha senha" (por enquanto)

---

## FASE 6 — FRONTEND: TELA DE SELEÇÃO DE EMPRESA

### `frontend/src/routes/selecionar-empresa/+page.svelte`

**Layout:**
- Título: "Olá, {nome}! Selecione a empresa:"
- Grid de cards — um card por empresa que o usuário tem acesso
- Cada card mostra:
  - Logo da empresa (ou inicial do nome se não tiver logo)
  - Nome da empresa
  - Efeito hover com borda colorida
- Botão "Sair" no canto superior direito

**Comportamento:**
1. Ao carregar, busca empresas do usuário via `user_id` salvo
2. Se usuário tiver acesso a só 1 empresa → seleciona automaticamente
3. Usuário clica no card da empresa
4. Chama `POST /api/auth/selecionar-empresa`
5. Recebe JWT → salva no localStorage
6. Salva empresa selecionada no store
7. Redireciona para `/` (dashboard)

**Segurança:**
- Se não tiver `user_id` temporário → redireciona para `/login`
- Usuário NÃO vê empresas de outros usuários

---

## FASE 7 — FRONTEND: TELA DE CONFIGURAÇÕES (admin)

### Estrutura de rotas:

```
/configuracoes
├── /empresas              → lista de empresas
│   ├── /nova              → cadastrar nova empresa
│   └── /[id]              → editar empresa
├── /usuarios              → lista de usuários
│   ├── /novo              → cadastrar usuário
│   └── /[id]              → editar usuário + vínculos
└── /queries               → (já documentado no arquitetura-queries-dinamicas.md)
```

### 7.1 `/configuracoes/empresas/+page.svelte`

**Lista de empresas em cards:**
- Logo + nome + slug + status (ativo/inativo)
- Botão "Nova Empresa"
- Botão editar em cada card
- Botão desativar em cada card (com confirmação)
- Somente admin vê este menu

### 7.2 `/configuracoes/empresas/nova/+page.svelte`

**Formulário de cadastro:**

```
Seção 1 — Dados da Empresa
  [ Nome da empresa          ]
  [ Slug (identificador)     ]  auto-gerado a partir do nome, editável
  [ Upload de logo           ]  preview da imagem após seleção

Seção 2 — Conexão com o Banco
  [ Host                     ]
  [ Porta          ] [ Banco ]
  [ Usuário                  ]
  [ Senha                    ]
  [ Botão "Testar Conexão"   ]  ← obrigatório antes de salvar
    → verde: "Conexão OK — X tabelas encontradas"
    → vermelho: "Falha: mensagem do erro"

[ Cancelar ]  [ Salvar Empresa ]
  → Salvar só habilitado após teste de conexão bem-sucedido
```

### 7.3 `/configuracoes/usuarios/+page.svelte`

**Tabela de usuários:**
- Nome, e-mail, role, status, empresas vinculadas
- Botão "Novo Usuário"
- Botão editar + desativar por linha

### 7.4 `/configuracoes/usuarios/novo/+page.svelte`

**Formulário:**
```
[ Nome completo    ]
[ E-mail           ]
[ Senha            ]
[ Perfil           ]  Admin / Visualizador

Empresas com acesso:
  [ ] Empresa Alpha
  [ ] Empresa Beta
  [ ] Empresa Gamma
  (checkboxes — só mostra empresas ativas)

[ Cancelar ]  [ Salvar Usuário ]
```

---

## FASE 8 — SIDEBAR: MENU DE CONFIGURAÇÕES

Adicione ao layout principal (`+layout.svelte`):

```
Menu lateral:
  Dashboard
  Gráficos
  Mapa
  Relatórios
  IA

  ── Admin (só aparece se role === 'admin') ──
  Empresas
  Usuários
  Queries
  Configurações
```

Adicione também no topbar:
- Nome da empresa selecionada com logo pequena
- Botão "Trocar empresa" → volta para `/selecionar-empresa`
- Avatar do usuário com nome + botão logout

---

## FASE 9 — STORE GLOBAL (SvelteKit)

### `frontend/src/lib/stores/auth.js`

```javascript
import { writable, derived } from 'svelte/store';

// Usuário logado
export const usuario = writable(
    JSON.parse(localStorage.getItem('usuario') || 'null')
);

// Empresa selecionada
export const empresaAtiva = writable(
    JSON.parse(localStorage.getItem('empresaAtiva') || 'null')
);

// Token JWT
export const token = writable(
    localStorage.getItem('token') || null
);

// É admin?
export const isAdmin = derived(usuario, $u => $u?.role === 'admin');

// Sincroniza com localStorage automaticamente
usuario.subscribe(v => localStorage.setItem('usuario', JSON.stringify(v)));
empresaAtiva.subscribe(v => localStorage.setItem('empresaAtiva', JSON.stringify(v)));
token.subscribe(v => v ? localStorage.setItem('token', v) : localStorage.removeItem('token'));

// Logout completo
export function logout() {
    usuario.set(null);
    empresaAtiva.set(null);
    token.set(null);
}
```

---

## FASE 10 — GUARD DE AUTENTICAÇÃO

### `frontend/src/hooks.client.js`

```javascript
// Rotas públicas (não precisam de login)
const PUBLIC_ROUTES = ['/login'];

// Rotas que precisam de login mas não de empresa selecionada
const AUTH_ONLY_ROUTES = ['/selecionar-empresa'];

export async function handle({ event, resolve }) {
    const token = localStorage.getItem('token');
    const path = event.url.pathname;

    const isPublic = PUBLIC_ROUTES.includes(path);
    const isAuthOnly = AUTH_ONLY_ROUTES.includes(path);

    if (!isPublic && !token) {
        return Response.redirect(new URL('/login', event.url));
    }

    return resolve(event);
}
```

---

## FASE 11 — API.JS: NOVOS MÉTODOS

Adicione ao `frontend/src/lib/api.js`:

```javascript
// Auth
login: (email, senha) =>
    request('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, senha })
    }),

selecionarEmpresa: (user_id, empresa_id) =>
    request('/api/auth/selecionar-empresa', {
        method: 'POST',
        body: JSON.stringify({ user_id, empresa_id })
    }),

minhasEmpresas: () => request('/api/auth/minhas-empresas'),

// Empresas (admin)
listarEmpresas:     ()      => request('/api/empresas/'),
buscarEmpresa:      (id)    => request(`/api/empresas/${id}`),
criarEmpresa:       (data)  => request('/api/empresas/', { method: 'POST', body: JSON.stringify(data) }),
atualizarEmpresa:   (id, data) => request(`/api/empresas/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
desativarEmpresa:   (id)    => request(`/api/empresas/${id}`, { method: 'DELETE' }),
testarConexao:      (data)  => request('/api/empresas/testar-conexao', { method: 'POST', body: JSON.stringify(data) }),
uploadLogo:         (id, formData) => request(`/api/empresas/${id}/logo`, { method: 'POST', body: formData }),

// Usuários (admin)
listarUsuarios:     ()      => request('/api/usuarios/'),
criarUsuario:       (data)  => request('/api/usuarios/', { method: 'POST', body: JSON.stringify(data) }),
atualizarUsuario:   (id, data) => request(`/api/usuarios/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
desativarUsuario:   (id)    => request(`/api/usuarios/${id}`, { method: 'DELETE' }),
vincularEmpresas:   (id, empresa_ids) => request(`/api/usuarios/${id}/empresas`, {
    method: 'POST',
    body: JSON.stringify({ empresa_ids })
}),
```

---

## CHECKLIST FINAL

Antes de considerar concluído, verifique:

- [ ] Login com e-mail e senha funciona
- [ ] Login com credenciais erradas mostra erro claro
- [ ] Após login aparece APENAS as empresas do usuário
- [ ] Usuário com 1 empresa vai direto para o dashboard
- [ ] JWT é gerado APÓS selecionar a empresa
- [ ] Dashboard mostra nome e logo da empresa no topbar
- [ ] Botão "Trocar empresa" funciona
- [ ] Logout limpa tudo e volta para /login
- [ ] Admin vê menu de configurações
- [ ] Viewer NÃO vê menu de configurações
- [ ] Cadastro de empresa testa conexão antes de salvar
- [ ] Upload de logo funciona e aparece na tela de seleção
- [ ] Cadastro de usuário com vínculo de empresas funciona
- [ ] Usuário recém cadastrado consegue logar

---

## CREDENCIAIS DE TESTE (já no banco)

```
Admin:
  email: admin@datahub.local
  senha: admin123

Acesso a: todas as empresas (Alpha, Beta, Gamma)
```

Se as credenciais não funcionarem, verifique o hash bcrypt
e recrie com:
```python
import bcrypt
hash = bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode()
print(hash)
```
