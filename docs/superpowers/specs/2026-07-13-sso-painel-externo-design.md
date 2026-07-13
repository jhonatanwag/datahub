# Autenticação via API para app externo (SSO sem tela de login) — Design

## Contexto

Hoje o único jeito de entrar no DataHub é `/login` (email + senha) →
`/selecionar-empresa` → JWT (`routes/auth.py`). Existe agora a necessidade de
um app externo já desenvolvido (com seu próprio cadastro de usuários, fora do
DataHub) mostrar painéis do DataHub pros usuários dele **sem** passar por essa
tela — o app externo redireciona o navegador do usuário final direto pro
DataHub, já autenticado.

Esse usuário **não é** um registro em `usuarios` — ele só existe no sistema do
app externo, identificado por um "código do usuário" que o app externo
controla. O acesso (se aquele código pode ver aquele painel) é decidido por
uma view/consulta que existe no **banco de dados da própria empresa** (o mesmo
banco tenant que o `query_runner` já usa pra rodar as queries dos painéis),
não pelo `datahub_meta`.

Este é um caminho de autenticação **novo e paralelo** ao login tradicional —
não altera em nada `/login`, `/selecionar-empresa` nem o fluxo de quem já usa
o sistema hoje.

## Decisões

- **Como o app externo dispara a entrada:** redirect de navegador — o app
  externo manda o usuário final pra uma URL do DataHub, não embute nada via
  iframe.
- **Onde fica o segredo de confiança:** o **backend** do app externo chama a
  API do DataHub server-to-server com uma API key **por empresa**
  (nunca o navegador do usuário vê essa chave).
- **Identidade do usuário:** não existe cadastro prévio em `usuarios`. O
  "código do usuário" vem em cada chamada e é repassado pro DataHub validar
  contra o banco da própria empresa.
- **Escopo de acesso:** por painel. Cada chamada de SSO já informa qual
  `painel_slug` quer abrir, e a checagem de acesso (via view no banco da
  empresa) recebe `codigo_usuario` + `painel_slug` juntos — o token emitido
  só abre aquele painel específico, nunca serve pra navegar pra outro.
- **Uso do código do usuário depois do acesso liberado:** continua sendo
  usado — é injetado como parâmetro nas queries do painel (filtra os dados
  pra mostrar só o que pertence àquela pessoa), não serve só pra checagem de
  entrada.
- **Por que dois saltos (API key da empresa → token de troca de uso único →
  JWT final)** em vez de já devolver o JWT final na URL de redirect: o token
  de troca (Redis, TTL curto, `GETDEL` — mesmo padrão do `session_token` que
  o login tradicional já usa) só serve uma vez. Um JWT final (que dura a
  sessão inteira, hoje `JWT_EXPIRE_MINUTES`) aparecendo direto na URL de
  redirect ficaria exposto em histórico de navegador, logs de proxy e
  cabeçalho `Referer` como credencial reutilizável.

## Modelo de dados

Nova coluna em `empresas`:

```sql
ALTER TABLE empresas ADD COLUMN sso_api_key_hash VARCHAR(255);
```

`NULL` = SSO desabilitado pra essa empresa (default seguro — nenhuma empresa
existente passa a aceitar SSO sem uma ação explícita de gerar a chave). O
valor em texto puro da API key só é mostrado **uma vez**, no momento em que é
gerada (mesmo princípio de senha/hash — só o bcrypt fica persistido).

**Migração:** mesmo processo manual já usado pra colunas novas neste projeto
— `ALTER TABLE` no Postgres de dev, refletir em `scripts/init-db.sql` e
`scripts/init-meta-prod.sql`, aplicar manualmente em produção (VPS) como
pendência de deploy documentada.

**Contrato da view/consulta no banco da empresa (a combinar com o time do app
externo):** um nome de view ou função fixo que o DataHub chama passando
`codigo_usuario` e `painel_slug`, devolvendo se há acesso (e nada mais — os
dados do usuário em si, se precisarem aparecer em algum lugar do DataHub,
ficam fora de escopo deste desenho). Esse contrato precisa existir/ser criado
em cada banco de empresa que for habilitar SSO antes de gerar a API key
correspondente.

## Backend

### Novo: geração da API key por empresa (admin)

Endpoint admin (em `routes/empresas.py`, protegido por `require_admin`) que
gera uma nova API key aleatória, salva só o hash bcrypt em
`sso_api_key_hash`, e devolve o valor em texto puro **uma única vez** na
resposta (não é recuperável depois — só regenerável, invalidando a anterior).

### Novo endpoint 1 — `POST /api/auth/sso-painel`

Público (sem `Authorization` Bearer — a autenticação aqui é a API key no
corpo). Chamado pelo backend do app externo.

Entrada: `{ empresa_slug, api_key, codigo_usuario, painel_slug }`

1. Busca `empresas` por `slug` (`ativo = true`) → 404 genérico se não achar
2. `sso_api_key_hash` nulo → 403 genérico ("SSO não habilitado")
3. `bcrypt.checkpw(api_key, sso_api_key_hash)` → 401 genérico se não bater
4. Busca `paineis` por `slug` **e** `empresa_id` (confirma que o painel
   pertence a essa empresa, `ativo = true`) → 404 genérico se não achar
5. Conecta no banco da própria empresa (reaproveita
   `db_host/db_port/db_name/db_user/db_pass` de `empresas`, mesma conexão que
   o `query_runner` já usa) e roda a view/consulta de acesso combinada,
   passando `codigo_usuario` + `painel_slug` → 403 genérico se não tiver
   acesso
6. Gera token de troca opaco (`secrets.token_hex(32)`), salva no Redis
   (`sso_exchange:<token>`, TTL curto — ex. 60s) carregando
   `{empresa_id, company_slug, codigo_usuario, painel_slug}`
7. Retorna `{ redirect_url: f"{FRONTEND_URL}/sso?exchange={token}" }`

Todas as respostas de erro (empresa errada, painel errado, api_key errada, sem
acesso) usam mensagens genéricas o suficiente pra não permitir enumeração
(não dá pra distinguir de fora "empresa não existe" de "chave errada", por
exemplo).

### Novo endpoint 2 — `POST /api/auth/sso/trocar`

Chamado pelo frontend, a partir da rota `/sso`.

Entrada: `{ exchange }`

1. `GETDEL` de `sso_exchange:<exchange>` no Redis (uso único, atômico) → 401
   se expirado/já usado/inválido
2. Emite o JWT final:
   ```json
   {
     "tipo": "externo",
     "empresa_id": ...,
     "company_slug": ...,
     "codigo_usuario": ...,
     "painel_slug": ...,
     "jti": "<uuid gerado>",
     "exp": ...
   }
   ```
   (`jti` novo porque não existe `user_id` pra usar como chave de blacklist,
   diferente do fluxo interno)
3. Retorna `{ token, token_type: "bearer", painel_slug }`

### `middleware/auth.py` — `get_current_user`

Passa a ramificar pelo claim `tipo` do payload do JWT:

- ausente ou `"interno"` → comportamento de hoje, sem mudança (join com
  `usuarios` + `usuario_empresas`)
- `"externo"` → não consulta `usuarios`. Checa blacklist por
  `blacklist:externo:{jti}` (não por `user_id`, que não existe). Devolve um
  dict no mesmo formato usado hoje, pra não quebrar código que já lê
  `user["empresa_id"]` / `user["company_slug"]`:
  ```python
  {
      "id": None,
      "nome": None,
      "role": "externo",
      "tema": None,
      "empresa_id": payload["empresa_id"],
      "company_slug": payload["company_slug"],
      "company_name": None,
      "codigo_usuario": payload["codigo_usuario"],
      "painel_slug": payload["painel_slug"],
  }
  ```

`logout` (que hoje grava `blacklist:{user['id']}`) precisa de um equivalente
pra `tipo="externo"` usando `jti` — fora do escopo estrito deste SSO (o token
externo já expira sozinho), mas o campo `jti` já fica disponível caso seja
necessário no futuro.

### `routes/paineis.py`

**Trava por painel:** hoje o acesso é decidido via `painel_usuarios` (join por
`usuario_id`), que não existe pra identidade externa. Nas rotas que resolvem
um painel específico (`buscar_painel_por_slug`, `renderizar_painel` e as que
dependem do `painel_id` resolvido a partir dele — `listar_indicadores`,
`listar_variaveis_painel`): se `user["role"] == "externo"`, pular o join de
`painel_usuarios` e em vez disso comparar o slug do painel resolvido com
`user["painel_slug"]` — se não bater, 403. Ou seja, um token externo abre
**só** o painel pro qual foi emitido.

**Filtro automático (`renderizar_painel`):** logo depois de montar
`filtros = dict(request.query_params)`, se `user["role"] == "externo"`:

```python
filtros["codigo_usuario_externo"] = user["codigo_usuario"]  # sempre do JWT, nunca do request
```

Essa atribuição **sobrescreve** qualquer valor que viesse na query string —
um usuário externo não pode forjar `?codigo_usuario_externo=outro` pra ver
dado de outra pessoa, porque o valor real sempre vem do claim assinado do
JWT, não do parâmetro da URL. Quem cadastra a query em
`/configuracoes/queries` referencia esse nome de parâmetro do mesmo jeito que
já faz hoje com variáveis como `var_fazenda` (documentado nas telas de
Nova/Editar Query).

## Frontend

### Nova rota `/sso`

`frontend/src/routes/sso/+page.svelte`:

1. Lê `?exchange=` da URL
2. Chama `POST /api/auth/sso/trocar`
3. Sucesso: salva o token retornado via `$lib/stores/auth.js` (mesmo store
   de hoje — já é agnóstico ao conteúdo do JWT) e redireciona pra
   `/painel/{painel_slug}` (slug vem da resposta da troca)
4. Erro (token expirado/inválido/já usado): mostra mensagem simples de link
   inválido — **não** redireciona pra `/login` (esse visitante nunca tem
   senha aqui)

Nenhuma mudança em `/login`, `/selecionar-empresa` ou `+layout.svelte` — a
sidebar/menu geral (`meu_menu`, `meu_dashboard`) continua sendo só pro fluxo
interno; identidade externa nunca navega por ali, só abre o painel direto.

## Fora de escopo

- Tela admin completa de gestão de API keys por empresa (rotação, histórico)
  — só o endpoint de gerar/regenerar.
- Embed via iframe/webview (decidido: só redirect).
- Provisionamento automático de registros em `usuarios` para esses usuários
  externos.
- `logout` explícito / blacklist por `jti` pro fluxo externo (o token já
  expira sozinho pelo `exp`).
- Definir o nome/schema exato da view de acesso em cada banco de empresa —
  é um contrato a combinar caso a caso, não implementado aqui.
- Aplicar o `ALTER TABLE` em produção (VPS) — pendência manual de deploy.

## Verificação

- `POST /api/auth/sso-painel` com api_key/empresa/painel/código válidos
  devolve `redirect_url` funcional.
- api_key errada, empresa inexistente/inativa, painel de outra empresa, ou
  view de acesso negando → sempre 401/403/404 com mensagem genérica.
- `POST /api/auth/sso/trocar` com token de troca válido emite JWT com
  `tipo: "externo"`; reusar o mesmo token de troca uma segunda vez falha
  (uso único).
- `GET /api/paineis/slug/{outro_slug}` com um JWT externo escopado pra um
  painel diferente → 403.
- `renderizar_painel` com JWT externo aplica `codigo_usuario_externo` nas
  queries independente do que vier na query string da requisição.
- Fluxo de login tradicional (`/login` → `/selecionar-empresa` → dashboard)
  continua funcionando sem nenhuma diferença observável.
