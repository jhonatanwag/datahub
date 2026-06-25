"""ARQ Worker — processa tarefas pesadas em background."""
import json
import logging
from arq.connections import RedisSettings
from config.databases import query_company, query_meta
from config.settings import settings

logger = logging.getLogger("datahub.worker")


async def gerar_relatorio_mensal(ctx, empresa_id: int, company_slug: str, usuario_id: int):
    try:
        await query_meta(
            "UPDATE tarefas SET status='rodando' WHERE empresa_id=$1 AND usuario_id=$2 AND status='pendente'",
            empresa_id, usuario_id
        )

        rows = await query_company(company_slug, """
            SELECT
                TO_CHAR(data, 'YYYY-MM') AS mes,
                COUNT(*) AS pedidos,
                SUM(valor) AS receita,
                AVG(valor) AS ticket_medio
            FROM pedidos
            WHERE data >= NOW() - INTERVAL '12 months'
            GROUP BY 1 ORDER BY 1
        """)

        resultado = [dict(r) for r in rows]

        await query_meta(
            """UPDATE tarefas SET status='ok', resultado=$1::jsonb, concluido_em=NOW()
               WHERE empresa_id=$2 AND usuario_id=$3 AND status='rodando'""",
            json.dumps(resultado, default=str), empresa_id, usuario_id
        )
        return resultado

    except Exception as e:
        await query_meta(
            "UPDATE tarefas SET status='erro', resultado=$1::jsonb WHERE empresa_id=$2 AND usuario_id=$3",
            json.dumps({"erro": str(e)}), empresa_id, usuario_id
        )
        raise


async def startup(ctx):
    logger.info("Worker iniciado")


async def shutdown(ctx):
    logger.info("Worker encerrado")


class WorkerSettings:
    functions = [gerar_relatorio_mensal]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
