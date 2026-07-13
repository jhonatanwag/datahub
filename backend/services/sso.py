"""Funções compartilhadas do fluxo de SSO externo (routes/auth.py + routes/empresas.py)."""
import logging
import bcrypt
from typing import List
from fastapi import HTTPException
from config.databases import query_meta, query_company

logger = logging.getLogger("datahub")


def validar_coluna_painel_slug(data: List[dict]) -> None:
    """A query de acesso SSO precisa devolver uma coluna chamada exatamente
    'painel_slug' (o backend lê essa chave literalmente). Sem essa checagem,
    uma query com coluna de outro nome roda com sucesso e devolve linhas,
    mas nenhum painel nunca é liberado, silenciosamente."""
    if data and "painel_slug" not in data[0]:
        colunas = list(data[0].keys())
        raise ValueError(
            f"A query retornou as colunas {colunas}, mas era esperado 'painel_slug'. "
            f"Use um alias, ex: SELECT slug AS painel_slug FROM tabela WHERE codigo_usuario = $1"
        )


async def validar_empresa_sso(empresa_slug: str, api_key: str) -> dict:
    """Valida a API key de SSO de uma empresa e devolve a linha completa de
    `empresas` (incluindo sso_query_acesso) se válida. Levanta HTTPException
    401 genérico (mesma mensagem pra empresa inexistente, SSO não
    habilitado, ou chave errada — evita enumeração) caso contrário."""
    empresa_rows = await query_meta(
        "SELECT id, slug, sso_api_key_hash, sso_query_acesso FROM empresas WHERE slug = $1 AND ativo = true",
        empresa_slug
    )
    if not empresa_rows:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    empresa = dict(empresa_rows[0])

    if not empresa["sso_api_key_hash"] or not empresa["sso_query_acesso"]:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    if not bcrypt.checkpw(api_key.encode(), empresa["sso_api_key_hash"].encode()):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    return empresa


async def buscar_slugs_liberados(empresa: dict, codigo_usuario: str) -> List[str]:
    """Roda a query_acesso configurada da empresa (banco da própria empresa,
    via query_company) e devolve a lista de painel_slug liberados pro
    codigo_usuario informado."""
    try:
        rows = await query_company(empresa["slug"], empresa["sso_query_acesso"], codigo_usuario)
    except Exception as e:
        logger.error(f"Erro ao rodar sso_query_acesso da empresa {empresa['slug']}: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")

    data = [dict(r) for r in rows]
    try:
        validar_coluna_painel_slug(data)
    except ValueError as e:
        logger.error(f"sso_query_acesso da empresa {empresa['slug']} com formato inválido: {e}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor")

    return [r["painel_slug"] for r in data]
