# Configuração de SSO por empresa (query editável + listagem de painéis) — Design

## Contexto

O feature de SSO externo (`docs/superpowers/specs/2026-07-13-sso-painel-externo-design.md`,
já implementado e mergeado em `master`) deixou dois pontos fixos no código que
precisam virar configuração por empresa:

1. A chave de API da empresa (`empresas.sso_api_key_hash`) só pode ser gerada
   via `POST /api/empresas/{id}/sso-api-key` — sem tela de admin, só curl.
2. A query de verificação de acesso (`vw_datahub_sso_acesso`) está **hardcoded**
   em `backend/routes/auth.py` — toda empresa que habilitar SSO precisaria ter
   uma view com esse nome exato, sem poder apontar pra uma tabela/view
   diferente que já exista no banco dela.

Durante o desenho, surgiu uma pergunta adicional do usuário: em vez de
verificar acesso painel-a-painel (`codigo_usuario` + `painel_slug` →
boolean), não seria melhor pedir só o `codigo_usuario` e devolver a lista
de painéis liberados? Investigado o motivo — o app externo precisa, em
outro momento, montar um **menu com vários painéis** pro mesmo usuário, não
só abrir um de cada vez — o que muda o formato do contrato da query (ver
Decisões).

## Decisões

- **Formato da query configurável:** SQL livre, mesmo padrão já usado em
  `variaveis.query_fonte` (admin escreve o SELECT, validado por
  `validar_sql` — só `SELECT`, sem `DROP`/`DELETE`/etc — e testável antes de
  salvar).
- **Parâmetro único, não dois:** a query recebe só `$1 = codigo_usuario` e
  devolve **N linhas** com uma coluna `painel_slug` — a lista completa de
  painéis liberados pra esse usuário. Isso substitui o desenho anterior
  (`$1=codigo_usuario, $2=painel_slug` → `tem_acesso` boolean) porque uma
  query só, reaproveitada em dois endpoints (checar 1 painel específico e
  listar todos), é mais simples de configurar e manter do que duas queries
  separadas — e o "checar 1 painel" é só um caso particular de "está na
  lista?", não precisa de uma segunda query dedicada.
- **Teste da query:** o admin digita um `codigo_usuario` de exemplo na tela
  e vê a lista de `painel_slug` que a query devolve pra ele — mesmo padrão
  do "Testar Conexão"/"testar-fonte" já usados nas telas de empresas e
  variáveis.
- **SSO só fica "habilitado" pra uma empresa quando as DUAS coisas existem**:
  `sso_api_key_hash` E `sso_query_acesso`. Faltando qualquer uma, o handshake
  `sso-painel` devolve o mesmo 401 genérico de "SSO não habilitado" já usado
  hoje.
- **Listagem não gera token.** O novo endpoint de listagem (`sso-meus-paineis`)
  só devolve metadados (slug/nome/ícone) pra montar um menu — não emite
  `redirect_url` nem token de troca. Gerar um token pra cada painel da lista
  seria desperdiçado (token de troca dura 60s, a maioria expiraria sem uso
  antes do usuário clicar em algo) e aumentaria a superfície de tokens vivos
  sem necessidade. Quando o usuário efetivamente escolhe um painel no menu,
  o app externo chama o `sso-painel` normal (já existente) pra abrir de
  verdade — mesma separação que o fluxo interno já tem hoje entre
  `GET /api/paineis/meu-menu` (lista leve) e `GET /api/paineis/{id}/renderizar`
  (carrega de verdade).

## Modelo de dados

Nova coluna em `empresas`:

```sql
ALTER TABLE empresas ADD COLUMN sso_query_acesso TEXT;
```

`NULL` = SSO ainda não tem a query configurada (mesmo espírito do
`sso_api_key_hash` nullable). Refletir em `scripts/init-db.sql`,
`scripts/init-meta-prod.sql` e no README ("Deltas de schema pendentes"),
mesmo processo manual já estabelecido neste projeto pra colunas novas.

**Contrato da query (o que o admin escreve, e o que o time do app externo
precisa saber pra criar a view/tabela por trás):**

```sql
-- Exemplo de query que o admin colocaria em sso_query_acesso:
SELECT painel_slug FROM minha_tabela_de_permissoes WHERE codigo_usuario = $1
```

Precisa devolver uma coluna chamada literalmente `painel_slug` (texto) — uma
linha por painel liberado pra aquele `codigo_usuario`. Zero linhas = usuário
sem nenhum painel liberado (não é erro, é resultado válido).

## Backend

### `backend/routes/auth.py` — `sso_painel` (modificar)

Troca a consulta fixa (`SELECT EXISTS (...) AS tem_acesso`) por:

1. Buscar `sso_query_acesso` da empresa (junto com `sso_api_key_hash` na
   mesma query já existente) — se `NULL`, mesmo 401 genérico de "SSO não
   habilitado".
2. Rodar a query configurada via `query_company(empresa["slug"],
   empresa["sso_query_acesso"], body.codigo_usuario)` — só `$1`.
3. Validar que as linhas devolvidas têm a coluna `painel_slug` (nova função
   `_validar_coluna_painel_slug`, mesmo padrão de
   `_validar_colunas_valor_label` em `variaveis.py`, adaptada pra uma
   coluna só) — erro claro (500 logado, resposta genérica) se a query do
   admin estiver malformada, em vez de deixar vazar exceção crua do banco.
4. Checar em Python se `body.painel_slug` está entre os `painel_slug`
   devolvidos → 403 "Sem acesso a este painel" se não estiver.
5. Resto do handshake (token de troca no Redis, `redirect_url`) não muda.

### `backend/routes/auth.py` — novo `POST /sso-meus-paineis`

Entrada: `{ empresa_slug, api_key, codigo_usuario }` (sem `painel_slug`).

1. Mesma validação de empresa + api_key do `sso_painel` (extrair pra uma
   função auxiliar compartilhada, já que a lógica é idêntica nos dois
   endpoints — evita duplicar a checagem de api_key/hash).
2. Roda `sso_query_acesso` com `$1=codigo_usuario`, valida coluna
   `painel_slug`, monta a lista de slugs.
3. `SELECT slug, nome, icone FROM paineis WHERE empresa_id = $1 AND slug =
   ANY($2::text[]) AND ativo = true` — cruza a lista devolvida pela query
   do admin contra os painéis que **realmente existem e pertencem a essa
   empresa** (uma linha na query do admin apontando pra um slug que não
   existe mais, ou que é de outra empresa, é ignorada silenciosamente, não
   vira erro).
4. Retorna a lista `[{slug, nome, icone}]` — sem token, sem `redirect_url`.

### `backend/routes/empresas.py` — `POST /testar-sso-acesso` (novo, admin)

Entrada: `{ empresa_id, query, codigo_usuario }`.

1. Roda a `query` informada (ainda não salva) contra o banco da empresa via
   `query_company`, com `$1=codigo_usuario`.
2. Valida coluna `painel_slug`, mesmo validador do item anterior.
3. Retorna `{ ok: true, slugs: [...] }` ou `{ ok: false, erro: "..." }` — sem
   erro cru de SQL vazando (mesmo padrão de `testar-fonte` de variáveis).

### `backend/routes/empresas.py` — `PATCH /{id}` (modificar)

Adicionar `sso_query_acesso: Optional[str] = None` no corpo aceito e no
`UPDATE`, mesmo padrão de campo opcional já usado pra `db_pass`.

## Frontend

### `/configuracoes/empresas/[id]/+page.svelte` (modificar)

Nova seção "SSO Externo", abaixo de "Conexão com o Banco":

- Botão "Gerar/Regenerar chave de API" (chama o endpoint já existente,
  `POST /{id}/sso-api-key`) — mostra a chave em texto puro numa área
  destacada com aviso "copie agora, não será mostrada de novo", sem
  persistir no state depois de sair da tela.
- Textarea pra `sso_query_acesso` (SQL livre).
- Campo de texto "Código de usuário de exemplo" + botão "Testar" (chama
  `POST /api/empresas/testar-sso-acesso`) — mostra a lista de `painel_slug`
  devolvida ou o erro, mesmo estilo visual (`.status-ok`/`.status-fail`) já
  usado no "Testar Conexão" da mesma tela.
- `sso_query_acesso` entra no payload de `atualizarEmpresa` junto com o
  resto dos campos já salvos hoje.

## Fora de escopo

- Tela de admin pra ver/editar `sso_query_acesso` de várias empresas de uma
  vez (só a tela de edição individual, uma empresa por vez).
- O app externo usar a listagem (`sso-meus-paineis`) pra pré-buscar tokens
  de todos os painéis — decisão explícita (ver "Decisões") de não gerar
  token nenhum nesse endpoint.
- Migrar quem já tem `sso_query_acesso` no formato antigo (2 parâmetros) —
  não existe ninguém em produção usando isso ainda (feature nunca foi
  usada por empresa real), então não há dado a migrar.
- Aplicar o `ALTER TABLE` em produção — mesma pendência manual de sempre,
  documentada no README.

## Verificação

- Empresa sem `sso_query_acesso` configurado → `sso_painel` e
  `sso-meus-paineis` devolvem o mesmo 401 genérico de "SSO não habilitado".
- Query configurada devolvendo 2 slugs pro `codigo_usuario` de teste →
  `sso_painel` com um desses 2 slugs → 200 (token emitido); com um terceiro
  slug não devolvido → 403.
- `sso-meus-paineis` com a mesma query devolve os 2 painéis (nome/ícone
  reais, cruzados com a tabela `paineis`) — um terceiro slug que a query do
  admin devolve mas não existe em `paineis` (ou pertence a outra empresa)
  não aparece na resposta.
- `testar-sso-acesso` com SQL inválido (ex: sem coluna `painel_slug`) →
  `ok: false` com mensagem clara, sem 500 cru.
- `PATCH /api/empresas/{id}` salvando `sso_query_acesso` — persiste e volta
  no `GET` seguinte.
- Tela de edição de empresa — gerar chave, colar query, testar com um
  código de exemplo, salvar — fluxo completo manual.
