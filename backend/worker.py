from arq.connections import RedisSettings
import os

async def tarefa_exemplo(ctx, mensagem: str = "ok"):
    """Tarefa placeholder — será substituída pelo código real."""
    print(f"Tarefa executada: {mensagem}")
    return {"status": "ok"}

async def startup(ctx):
    print("Worker iniciado")

async def shutdown(ctx):
    print("Worker encerrado")

class WorkerSettings:
    functions = [tarefa_exemplo]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(
        os.getenv("REDIS_URL", "redis://redis:6379")
    )