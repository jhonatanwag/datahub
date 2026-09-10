from config.databases import query_meta

_TABELAS_PERMITIDAS = {"query_grupos", "painel_grupos"}


async def resolver_grupo_id(tabela: str, nome, conn=None):
    """Acha o grupo pelo nome (case-insensitive) ou cria um novo. `tabela` é
    um literal fixo do código (query_grupos | painel_grupos), nunca entrada
    de usuário. `conn`, se passado, roda dentro da transação chamadora."""
    if tabela not in _TABELAS_PERMITIDAS:
        raise ValueError(f"Tabela de grupo inválida: {tabela}")

    nome = (nome or "").strip()
    if not nome:
        return None

    exec_ = conn.fetch if conn is not None else query_meta
    existente = await exec_(f"SELECT id FROM {tabela} WHERE LOWER(nome) = LOWER($1)", nome)
    if existente:
        return existente[0]["id"]
    novo = await exec_(f"INSERT INTO {tabela} (nome) VALUES ($1) RETURNING id", nome)
    return novo[0]["id"]
