# Integração SSO externo — DataHub

Documentação pro time do **app externo** que vai autenticar seus usuários
direto no DataHub (sem login manual) e abrir os painéis liberados pra
cada um. Gera um link de acesso por usuário — o app externo nunca
manipula JWT do DataHub diretamente, só chama uma rota server-to-server e
redireciona o navegador do usuário final pro link devolvido.

## Visão geral do fluxo

```
App externo (backend)                  DataHub (backend)              Navegador do usuário final
       |                                       |                                |
       |--- POST /api/auth/sso-entrar -------->|                                |
       |    (api_key + codigo_usuario)         |                                |
       |                                       | valida api_key, roda a query   |
       |                                       | de acesso configurada da       |
       |                                       | empresa no banco dela          |
       |<-- { redirect_url } ------------------|                                |
       |                                                                        |
       |--- redireciona o navegador do usuário pra redirect_url --------------->|
       |                                                                        |
       |                                       |<-- GET /sso?exchange=... ------|
       |                                       | troca o token de uso único     |
       |                                       | por um JWT de sessão (30 min)  |
       |                                       |--- entra logado, home normal ->|
```

O app externo faz **uma chamada server-to-server** (`sso-entrar`) e
redireciona o navegador pro `redirect_url` recebido. O DataHub cuida do
resto (troca de token, login, listagem de painéis) — nada de JWT do
DataHub passa pelo app externo.

## Pré-requisito — configuração feita pelo admin do DataHub

Antes de qualquer integração, um admin do DataHub precisa, na tela
**Configurações → Empresas → editar empresa**:

1. Gerar a **API key de SSO** da empresa (botão na tela — gera uma vez,
   mostra em texto puro só naquele momento; o DataHub guarda só o hash).
   **Essa chave é secreta** — trate como senha, nunca exponha no
   frontend do app externo.
2. Configurar a **query de acesso** (`sso_query_acesso`) — um SQL rodado
   no banco da própria empresa (não no banco do DataHub) que recebe
   `$1 = codigo_usuario` e devolve uma coluna chamada literalmente
   `painel_slug` (via `AS painel_slug` se o nome da coluna original for
   outro), uma linha por painel liberado pra esse usuário. Exemplo:
   ```sql
   SELECT p.slug AS painel_slug
   FROM permissao_painel p
   WHERE p.codigo_usuario = $1
   ```

Sem os dois configurados, `sso-entrar` responde `401` genérico (mesma
mensagem pra empresa inexistente, SSO desabilitado ou chave errada — não
dá pra saber qual pelo erro, por design).

## Rota principal — `POST /api/auth/sso-entrar`

Chamada **server-to-server** (nunca do navegador/frontend do app
externo — a `api_key` não pode vazar pro cliente).

**Request:**
```json
POST https://<dominio-datahub>/api/auth/sso-entrar
Content-Type: application/json

{
  "empresa_slug": "prats",
  "api_key": "<api key gerada pelo admin>",
  "codigo_usuario": "12345"
}
```

`codigo_usuario` é o identificador do usuário **no sistema do app
externo** — o mesmo valor que a `sso_query_acesso` da empresa espera
receber como `$1`.

**Response `200`:**
```json
{
  "redirect_url": "https://<dominio-datahub>/sso?exchange=a1b2c3...64hex"
}
```

**Próximo passo:** redirecionar o navegador do usuário final pra essa
URL (HTTP redirect, `<a href>`, `window.location`, etc — qualquer forma
de fazer o navegador abrir a URL). O token de troca (`exchange`) é
**de uso único e expira em 60 segundos** — gere o link e redirecione na
hora, não guarde/reuse.

**Erros:**
| Status | Quando |
|---|---|
| `401` | `empresa_slug` não existe/inativa, SSO não configurado, ou `api_key` errada |
| `500` | `sso_query_acesso` configurada com SQL inválido, erro ao rodar no banco da empresa, ou a query não devolveu a coluna `painel_slug` — nesses casos o problema é de configuração no DataHub (avisar o admin), não do app externo |

Se `codigo_usuario` não tiver nenhum painel liberado (query retorna
vazia), `sso-entrar` **ainda responde 200** com `redirect_url` — o
usuário chega ao DataHub logado, só que sem nenhum painel na listagem.
Não é erro.

## Rota alternativa (opcional) — `POST /api/auth/sso-meus-paineis`

Mesmo request de `sso-entrar`, mas sem gerar sessão — só devolve os
metadados dos painéis liberados, pro app externo montar sua **própria**
UI de listagem em vez de usar as telas do DataHub:

**Request:** idêntico ao de `sso-entrar` (`empresa_slug`, `api_key`,
`codigo_usuario`).

**Response `200`:**
```json
[
  { "slug": "visao_geral", "nome": "Visão Geral", "icone": "chart-bar" },
  { "slug": "lanc_fichas", "nome": "Lançamento de Fichas", "icone": "clipboard" }
]
```

Pra abrir um painel específico dessa lista dentro do DataHub, ainda é
preciso passar por `sso-entrar` normalmente (essa rota aqui é só
leitura, não gera nenhum link de acesso).

## O que acontece depois do redirect (não precisa implementar nada)

1. O navegador abre `/sso?exchange=...` no frontend do DataHub.
2. O frontend troca o `exchange` por um JWT interno
   (`POST /api/auth/sso/trocar`) — token de sessão `tipo: "externo"`,
   válido por **30 minutos** (`JWT_EXPIRE_MINUTES_EXTERNO`).
3. O usuário cai direto na home do DataHub ("Meus Painéis"), navega
   livremente entre todos os painéis liberados pra esse `codigo_usuario`
   até o token expirar.
4. A sidebar do DataHub, nessa sessão, mostra "Sair" mas não "Trocar
   empresa" (não existe multi-empresa nesse contexto).

## Segurança

- `api_key` é secreta — fica só no backend do app externo, nunca no
  frontend/navegador dele.
- Toda chamada a `sso-entrar` deve ser sobre HTTPS.
- O DataHub **não revalida** a lista de painéis liberados durante a
  sessão de 30 min — ela é travada no momento da troca de token (mesma
  filosofia do resto do sistema: checa uma vez no handshake, confia até
  expirar). Se o acesso do usuário mudar no meio de uma sessão ativa, só
  reflete na próxima vez que ele entrar via `sso-entrar`.
- Se precisar revogar acesso imediatamente (não só deixar expirar em até
  30 min), é preciso gerar uma nova API key pra empresa (invalida todas
  as sessões futuras, não as já ativas) — não existe endpoint de
  revogação de token individual hoje.

## Exemplo end-to-end (curl)

```bash
curl -X POST https://bi.psosistemas.com.br/api/auth/sso-entrar \
  -H "Content-Type: application/json" \
  -d '{
    "empresa_slug": "prats",
    "api_key": "SUA_API_KEY_AQUI",
    "codigo_usuario": "12345"
  }'
# => {"redirect_url": "https://bi.psosistemas.com.br/sso?exchange=..."}

# Redirecionar o navegador do usuário pra esse redirect_url encerra o fluxo.
```
