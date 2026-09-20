from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PORT: int = 3001
    JWT_SECRET: str
    JWT_EXPIRE_MINUTES: int = 480
    JWT_EXPIRE_MINUTES_EXTERNO: int = 30

    META_DB_HOST: str = "postgres"
    META_DB_PORT: int = 5432
    META_DB_NAME: str = "datahub_meta"
    META_DB_USER: str = "datahub_user"
    META_DB_PASS: str

    REDIS_URL: str = "redis://redis:6379"
    GROQ_API_KEY: str
    FRONTEND_URL: str = "http://localhost:3000"
    RENDERER_URL: str = "http://pdf-renderer:4000"
    RENDERER_SECRET: str = ""
    RELATORIO_BASE_URL: str = "http://frontend:3000"
    # Teto de linhas que UMA query pode devolver. Sem isso o resultado inteiro vive em memória várias
    # vezes (asyncpg Record -> dict -> JSON pro Redis -> JSON pro navegador). Consulta legítima grande
    # deve ser refinada por filtro; se precisar mais, sobe via env MAX_LINHAS_QUERY.
    MAX_LINHAS_QUERY: int = 200000

    class Config:
        env_file = ".env.dev"
        env_file_encoding = "utf-8"


settings = Settings()
