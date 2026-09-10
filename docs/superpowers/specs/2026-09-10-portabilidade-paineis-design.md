# Portabilidade de Painéis — Exportar / Importar

**Data:** 2026-09-10
**Status:** Aprovado — pronto para plano de implementação

## Objetivo

Permitir mover o cadastro de um painel entre ambientes (teste ↔ produção)
levando junto, automaticamente, todas as suas dependências — queries
(incluindo subconsultas encadeadas) e variáveis — de forma que o painel
fique funcional no destino sem trabalho manual de recriar cada peça.

O fluxo é: **exportar** um painel do ambiente A para um arquivo `.json`,
**importar** esse arquivo no ambiente B com uma tela de pré-visualização
que deixa o operador decidir, item a item, o que criar/sobrescrever.

## Decisões de escopo (definidas no brainstorming)

| Tema | Decisão |
|---|---|
| `empresa_id` | Painéis/queries movidos são **quase sempre globais** (`empresa_id = NULL`). O export grava `empresa_slug` (ou `null`); no import, `null` → global, slug conhecido → id do destino, slug desconhecido → importa como global + aviso. |
| Conflito de slug no import | **Preview + decisão por item.** A tela mostra `novo` / `conflito` / `idêntico` e o operador marca o que aplicar. |
| Conflito — nível de detalhe | Apenas a **contagem de campos diferentes** por entidade. Sem diff campo-a-campo. |
| Imagens (`paineis.imagem`, `queries.kpi_imagem`) | **Incluídas** no arquivo, em base64. |
| `painel_usuarios` (acesso) | **Não** exportado. Acesso é liberado manualmente no destino. |
| Granularidade | **Um painel por arquivo.** (O formato mesmo assim é uma estrutura achatada, extensível a N painéis no futuro sem quebrar `versao`.) |
| Mecanismo de export | **Download de arquivo** (`Content-Disposition: attachment`), não copiar/colar. |
| Nomenclatura | Módulo backend `routes/portabilidade.py`; rota frontend `configuracoes/paineis/importar`. |

## Modelo de dados relevante (estado atual)

Chaves naturais que atravessam ambientes — **nenhum `id` numérico é
serializado**:

- `paineis.slug` — `UNIQUE` global
- `variaveis.slug` — `UNIQUE` global
- `queries` — `UNIQUE (slug, empresa_id)`; para o caso global, `slug` basta

Grafo de dependências de um painel:

```
paineis
├── grupo_id            → painel_grupos(nome)          [resolvido por nome]
├── empresa_id          → empresas(slug)               [normalmente NULL]
├── imagem / imagem_mime (BYTEA)
├── painel_indicadores
│   ├── query_slug      → queries(slug)                [texto livre, pode estar quebrado]
│   └── filtro_clique_variavel_id → variaveis(id)
├── painel_variaveis
│   └── variavel_id     → variaveis(id)
└── painel_usuarios     → usuarios(id)                 [NÃO exportado]

queries
├── grupo_id            → query_grupos(nome)           [resolvido por nome]
├── empresa_id          → empresas(slug)
├── subquery_id         → queries(id)                  [AUTO-REFERÊNCIA, recursiva]
├── kpi_imagem / kpi_imagem_mime (BYTEA)
├── query_parametros
│   └── variavel_id     → variaveis(id)
├── query_agrupamentos
├── query_agregacoes
└── query_subquery_parametros

variaveis
└── query_fonte         → SQL puro, autocontida (sem FK)
```

## Formato do arquivo

Nome: `painel-<slug>-AAAAMMDD.json`

```jsonc
{
  "formato": "datahub-painel",
  "versao": 1,
  "exportado_em": "2026-09-10T12:00:00Z",

  "painel": {
    "slug": "...", "nome": "...", "descricao": "...", "icone": "...",
    "colunas": 3, "linhas_fixas": false, "total_linhas": null,
    "ordem_menu": 0, "impressao_orientacao": "retrato", "ativo": true,
    "grupo_nome": "Financeiro | null",
    "empresa_slug": null,
    "imagem_base64": "... | null",
    "imagem_mime": "image/png | null",

    "indicadores": [
      {
        "query_slug": "kpi_receita",
        "titulo": null,
        "linha": 1, "coluna": 1, "col_span": 1, "row_span": 1, "posicao": 0,
        "filtro_clique_variavel_slug": "vendedor | null"
      }
    ],

    "variaveis_painel": [
      {
        "variavel_slug": "periodo",
        "obrigatorio": false,
        "valor_padrao": null,
        "valor_padrao_inicio": null,
        "valor_padrao_fim": null,
        "posicao": 1
      }
    ]
  },

  "queries": [
    {
      "slug": "kpi_receita", "nome": "...", "descricao": "...",
      "sql_texto": "...", "tipo": "kpi", "cache_ttl": 300, "ativo": true,
      "kpi_cor_fonte": "...", "kpi_cor_fundo": "...", "mapa_camada": "padrao",
      "chart_fonte_tamanho": 12, "chart_truncar_label": false,
      "chart_truncar_tamanho": 15, "chart_mostrar_valor": false,
      "chart_valor_label": null, "chart_rotulo_eixo": "horizontal",
      "chart_rotulo_valor": "horizontal",
      "impressao_habilitada": false, "impressao_caminho": null, "impressao_coluna": null,
      "meta_habilitada": false, "meta_coluna_valor": null,
      "meta_coluna_inicio": null, "meta_coluna_fim": null,
      "meta_cor_dentro": "#3fb950", "meta_cor_fora": "#f85149",
      "pdf_orientacao": "retrato",
      "kpi_imagem_habilitada": false, "kpi_imagem_posicao": "direita",
      "kpi_valor_primeiro": false, "chart_filtro_coluna": null,

      "grupo_nome": "KPIs | null",
      "empresa_slug": null,
      "subquery_slug": "detalhe_receita | null",
      "kpi_imagem_base64": "... | null",
      "kpi_imagem_mime": "image/png | null",

      "parametros": [
        {
          "nome": "data_inicio", "tipo": "date", "obrigatorio": true,
          "valor_padrao": null, "descricao": null,
          "variavel_slug": "periodo | null", "param_slot": "inicio"
        }
      ],
      "agrupamentos": [ { "coluna": "regiao", "ordem": 0 } ],
      "agregacoes": [ { "coluna": "valor", "funcao": "soma", "label": "Total", "ordem": 0 } ],
      "subquery_parametros": [ { "coluna_origem": "id", "parametro_destino": "pedido_id", "ordem": 0 } ]
    }
  ],

  "variaveis": [
    {
      "slug": "periodo", "nome": "Período", "descricao": "...",
      "tipo": "date_range",
      "query_fonte": null,
      "param_names": ["data_inicio", "data_fim"],
      "ativo": true
    }
  ]
}
```

Regras do formato:

- **Todos os campos de config da query são listados explicitamente** (não
  `SELECT *`), para o formato não vazar `id`, `criado_em`, `atualizado_em`,
  `grupo_id`, `empresa_id`, `subquery_id`, `kpi_imagem` cru.
- `param_names` é `text[]` — vai como array JSON.
- Import rejeita `formato` != `"datahub-painel"` ou `versao` > versão
  suportada (400 com mensagem clara).

## Resolução de dependências (no export)

`GET /api/paineis/{id}/exportar`:

1. Carrega o painel + `painel_indicadores` + `painel_variaveis`.
2. **Conjunto inicial de queries** = slugs distintos em
   `painel_indicadores.query_slug`.
3. **Fecho transitivo**: para cada query carregada, se tem `subquery_id`,
   adiciona o slug da subquery ao conjunto e repete. Guardar os slugs já
   visitados para cortar ciclo (`a → b → a`).
4. Para cada query do fecho, carrega as 4 tabelas-filhas.
5. **Conjunto de variáveis** = união de:
   - `painel_variaveis.variavel_id`
   - `painel_indicadores.filtro_clique_variavel_id`
   - `query_parametros.variavel_id` de todas as queries do fecho
6. Converte `grupo_id → grupo_nome`, `empresa_id → empresa_slug`,
   `subquery_id → subquery_slug`, `*_id de variável → *_slug`, BYTEA →
   base64.
7. `avisos`: se algum `painel_indicadores.query_slug` não existe na tabela
   `queries`, exporta o indicador assim mesmo e registra
   `"Indicador referencia query inexistente: <slug>"`.
8. Resposta: JSON com header
   `Content-Disposition: attachment; filename="painel-<slug>-AAAAMMDD.json"`.

## Backend — `routes/portabilidade.py`

Módulo novo para não inflar `paineis.py` (já 568 linhas). Todos os
endpoints `Depends(require_admin)`.

### `GET /api/paineis/{painel_id}/exportar`

Registrado neste módulo com `prefix="/api/paineis"` (FastAPI permite
múltiplos routers no mesmo prefixo). Retorna o bundle como download.
404 se o painel não existe.

### `POST /api/portabilidade/paineis/analisar`

- Body: o bundle (JSON).
- **Não grava nada.**
- Valida `formato` / `versao`.
- Para cada entidade do bundle (`painel`, cada `query`, cada `variavel`),
  compara com o registro do destino (buscado por slug) usando a **mesma
  serialização** do export (normaliza query + arrays-filhos antes de
  comparar) e classifica:
  - `novo` — slug não existe no destino
  - `identico` — existe e a serialização é igual
  - `conflito` — existe e difere; inclui `campos_diferentes: ["sql_texto", "cache_ttl"]`
    (nomes dos campos de topo e/ou `"parametros"`, `"agregacoes"` etc. quando
    o array-filho difere)
- `avisos`:
  - `empresa_slug` do bundle não existe no destino → "entrará como global"
  - query/variável referenciada que **não está no bundle e não existe no
    destino** → "dependência ausente: `<slug>`"
- Resposta:
  ```jsonc
  {
    "formato_ok": true,
    "plano": {
      "painel":    { "slug", "nome", "situacao", "campos_diferentes": [] },
      "queries":   [ { "slug", "nome", "situacao", "campos_diferentes": [] } ],
      "variaveis": [ { "slug", "nome", "situacao", "campos_diferentes": [] } ]
    },
    "avisos": [ "..." ]
  }
  ```

### `POST /api/portabilidade/paineis/importar`

- Body:
  ```jsonc
  {
    "bundle": { ... },
    "aplicar": {
      "variaveis": ["periodo", "vendedor"],
      "queries":   ["kpi_receita", "detalhe_receita"],
      "painel":    true
    }
  }
  ```
- Só grava as entidades cujos slugs estão em `aplicar`. As demais são
  ignoradas (assume-se que já existem no destino).
- **Checagem de integridade referencial antes de qualquer escrita**: para
  cada query/variável referenciada pelo que vai ser aplicado, o slug tem
  que **já existir no destino OU estar em `aplicar`**. Caso contrário →
  `400` com a lista do que falta.
- **Tudo dentro de uma transação** numa conexão dedicada do pool meta.

Ordem de gravação:

1. **`variaveis`** — upsert por slug (`INSERT ... ON CONFLICT (slug) DO
   UPDATE`). Reativa (`ativo = true`) se o registro existente estava
   desativado e o bundle diz ativo.
2. **`queries` — passo 1**: upsert por `(slug, empresa_id)` **sem**
   `subquery_id` e sem `grupo_id` resolvido ainda. `empresa_id` resolvido
   de `empresa_slug` (null se não achar). `grupo_id` via o helper
   compartilhado `resolver_grupo_id` (ver abaixo).
3. **`queries` — passo 2**: para as que têm `subquery_slug`, resolve o id
   agora (todas já existem) e faz `UPDATE queries SET subquery_id = ...`.
4. **Tabelas-filhas das queries aplicadas**: `DELETE ... WHERE query_id =
   $1` + reinsert, para `query_parametros` (com `variavel_id` resolvido de
   `variavel_slug`), `query_agrupamentos`, `query_agregacoes`,
   `query_subquery_parametros`. Mesmo padrão dos `PUT` existentes.
5. **`paineis`** — upsert por slug. `grupo_id` via o helper compartilhado
   `resolver_grupo_id` (tabela `painel_grupos`). `empresa_id` de
   `empresa_slug`. `imagem` decodificada de base64.
6. **`painel_indicadores`** e **`painel_variaveis`** — `DELETE WHERE
   painel_id = $1` + reinsert. `filtro_clique_variavel_id` e `variavel_id`
   resolvidos por slug (null se o slug não resolver — mesma tolerância do
   schema, que é `ON DELETE SET NULL`).
7. Fora da transação, depois do commit: `invalidar_cache_query(slug)` para
   cada query tocada.
8. Resposta:
   ```jsonc
   {
     "painel_slug": "visao_geral",
     "aplicado": { "variaveis": 2, "queries": 2, "painel": true },
     "avisos": [ "..." ]
   }
   ```

### Helper de grupo compartilhado

Hoje `_resolver_grupo_id` está **duplicado** em `routes/queries.py` e
`routes/paineis.py` — mesma lógica (acha por nome case-insensitive ou
cria), só muda a tabela (`query_grupos` vs `painel_grupos`). Extrair para
`services/grupos.py`:

```python
async def resolver_grupo_id(tabela: str, nome: str | None) -> int | None:
    """tabela ∈ {'query_grupos', 'painel_grupos'} — literal fixo no código,
    nunca entrada de usuário."""
    nome = (nome or "").strip()
    if not nome:
        return None
    existente = await query_meta(f"SELECT id FROM {tabela} WHERE LOWER(nome) = LOWER($1)", nome)
    if existente:
        return existente[0]["id"]
    novo = await query_meta(f"INSERT INTO {tabela} (nome) VALUES ($1) RETURNING id", nome)
    return novo[0]["id"]
```

`queries.py` e `paineis.py` passam a chamar
`resolver_grupo_id("query_grupos", nome)` /
`resolver_grupo_id("painel_grupos", nome)` e removem a cópia local. O
módulo de portabilidade usa a versão que recebe uma conexão (ver helper de
transação) — passar `conn` como parâmetro opcional, ou uma segunda função
`resolver_grupo_id_conn(conn, tabela, nome)`; decisão de forma no plano,
mas o resultado é **uma implementação só da lógica**.

### Helper de transação

`config/databases.py` hoje não expõe transação. Adicionar:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def meta_tx():
    pool = await get_meta_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            yield conn
```

O módulo de portabilidade usa `conn.fetch/execute` direto dentro do
`async with meta_tx() as conn:`.

## Frontend

### `api.js`

```js
exportarPainel:        (id)          => /* fetch blob com Bearer, dispara download */,
analisarImportPainel:  (bundle)      => request('/api/portabilidade/paineis/analisar', { method:'POST', body: JSON.stringify(bundle) }),
importarPainel:        (payload)     => request('/api/portabilidade/paineis/importar', { method:'POST', body: JSON.stringify(payload) }),
```

O download precisa do header `Authorization`, então não dá pra usar
`<a href>` puro: `fetch` → `res.blob()` → `URL.createObjectURL` → `<a>`
temporário com `download` → `click()` → `revokeObjectURL`.

### Lista de painéis (`configuracoes/paineis/+page.svelte`)

- Botão **"Exportar"** em cada card (ao lado de Editar/Desativar).
- Botão **"Importar painel"** no `page-header`, ao lado de "+ Novo Painel"
  → navega para `configuracoes/paineis/importar`.

### Nova rota `configuracoes/paineis/importar/+page.svelte`

1. `<input type="file" accept="application/json">`.
2. Ao escolher: lê o arquivo (`FileReader` / `file.text()`), faz
   `JSON.parse`, chama `analisarImportPainel`.
3. Renderiza:
   - Bloco de **avisos** (se houver).
   - Tabela do **painel** + tabelas de **queries** e **variáveis**, cada
     linha com: checkbox, slug, nome, badge de situação
     (`novo` verde / `conflito` amarelo / `idêntico` cinza) e, no
     conflito, "N campos diferentes: a, b, c".
   - Pré-seleção: `novo` e `conflito` marcados; `identico` desmarcado.
4. Botão **"Aplicar"** → monta `aplicar` a partir dos checkboxes marcados,
   chama `importarPainel`, mostra resultado + link
   `/configuracoes/paineis` (ou direto para o painel).
5. Erro `400` de dependência ausente → mostra a mensagem e mantém a tela
   para o operador remarcar.

## Testes — `backend/tests/test_portabilidade_paineis.py`

Segue o padrão da suíte: `TestClient` contra o banco meta de dev,
`hard_delete_*` no `finally`.

1. **Export — fecho transitivo**: painel → query A (com `subquery` B) →
   B tem `parametro` ligado a variável V. Export traz A, B e V; imagem
   do painel vem em base64.
2. **Export — aviso de query quebrada**: indicador com `query_slug`
   inexistente → sai em `avisos`, export não falha.
3. **`analisar` — classificação**: com o destino vazio, tudo `novo`;
   reimportando o mesmo bundle sem mudar nada, tudo `identico`; mudando
   `sql_texto` de uma query no bundle, ela vira `conflito` com
   `campos_diferentes: ["sql_texto"]`.
4. **`importar` — respeita `aplicar`**: bundle com 2 queries, `aplicar`
   só uma → só uma é criada; a segunda, se não existe no destino e é
   referenciada pelo painel aplicado → `400` de dependência ausente.
5. **`importar` — upsert**: importar, editar a query no destino,
   reimportar o bundle original marcando a query → volta ao conteúdo do
   bundle.
6. **`importar` — rollback**: forçar erro no passo do painel (ex: slug do
   painel com 200+ chars estourando `VARCHAR(100)`) → nenhuma variável
   nem query do bundle fica gravada.
7. **`importar` — recursão de subquery**: query A.`subquery_slug = "B"` e
   B.`subquery_slug = "A"` no mesmo bundle → importa as duas sem
   deadlock e com os dois `subquery_id` preenchidos.

## Fora de escopo

- Exportar múltiplos painéis num arquivo (formato já permite; UI não).
- Exportar `painel_usuarios` / casar usuários por email.
- Diff campo-a-campo com valores lado a lado na UI.
- Versionamento / histórico de imports.
- Merge automático de conflitos (a decisão é sempre do operador, e é
  tudo-ou-nada por entidade: aplica o do bundle ou mantém o do destino).
