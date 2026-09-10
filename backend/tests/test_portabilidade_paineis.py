import uuid
import pytest
from conftest import _connect_meta
import asyncio

from services.grupos import resolver_grupo_id


def test_resolver_grupo_id_acha_ou_cria_e_reusa():
    nome = f"Grupo Teste {uuid.uuid4().hex[:8]}"

    async def cenario():
        conn = await _connect_meta()
        id1 = None
        try:
            id1 = await resolver_grupo_id("painel_grupos", nome, conn=conn)
            id2 = await resolver_grupo_id("painel_grupos", nome.upper(), conn=conn)  # case-insensitive
            vazio = await resolver_grupo_id("painel_grupos", "  ", conn=conn)

            assert id1 is not None
            assert id1 == id2
            assert vazio is None
        finally:
            if id1:
                await conn.execute("DELETE FROM painel_grupos WHERE id = $1", id1)
            await conn.close()

    asyncio.run(cenario())


def test_resolver_grupo_id_rejeita_tabela_desconhecida():
    async def cenario():
        with pytest.raises(ValueError):
            await resolver_grupo_id("usuarios", "x")
    asyncio.run(cenario())
