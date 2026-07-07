import argparse
import asyncio
import os
import sys

import asyncpg
import bcrypt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings


async def criar_admin(nome: str, email: str, senha: str) -> None:
    conn = await asyncpg.connect(
        host=settings.META_DB_HOST,
        port=settings.META_DB_PORT,
        database=settings.META_DB_NAME,
        user=settings.META_DB_USER,
        password=settings.META_DB_PASS,
    )
    try:
        existente = await conn.fetchrow(
            "SELECT id FROM usuarios WHERE email = $1", email
        )
        if existente:
            print(f"Usuário com email '{email}' já existe (id={existente['id']}). Nada foi alterado.")
            return

        senha_hash = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()
        row = await conn.fetchrow(
            """
            INSERT INTO usuarios (nome, email, senha_hash, role)
            VALUES ($1, $2, $3, 'admin')
            RETURNING id
            """,
            nome, email, senha_hash,
        )
        print(f"Usuário admin '{email}' criado com id={row['id']}.")
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Cria o usuário admin inicial do DataHub em produção."
    )
    parser.add_argument("--nome", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--senha", required=True)
    args = parser.parse_args()

    asyncio.run(criar_admin(args.nome, args.email, args.senha))
