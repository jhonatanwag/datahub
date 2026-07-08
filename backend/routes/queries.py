from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam
from pydantic import BaseModel
from typing import Optional, List
from middleware.auth import get_current_user, require_admin
from config.databases import query_meta, query_company
from services.query_runner import resolver_query, invalidar_cache_empresa, validar_sql, _cast

router = APIRouter(prefix="/api/queries", tags=["Queries"])


class QueryInput(BaseModel):
    slug: str
    nome: str
    descricao: Optional[str] = None
    sql_texto: str
    tipo: str
    empresa_id: Optional[int] = None
    cache_ttl: int = 300
    ativo: bool = True
    kpi_cor_fonte: Optional[str] = '#e6edf3'
    kpi_cor_fundo: Optional[str] = '#161b22'
    mapa_camada: Optional[str] = 'padrao'
    chart_fonte_tamanho: Optional[int] = 12
    chart_truncar_label: Optional[bool] = False
    chart_truncar_tamanho: Optional[int] = 15
    chart_mostrar_valor: Optional[bool] = False
    testar_empresa_id: Optional[int] = None
    testar_parametros: List[dict] = []  # [{nome, valor}] em ordem — só usado no /testar


class QueryUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    sql_texto: Optional[str] = None
    tipo: Optional[str] = None
    cache_ttl: Optional[int] = None
    ativo: Optional[bool] = None
    kpi_cor_fonte: Optional[str] = None
    kpi_cor_fundo: Optional[str] = None
    mapa_camada: Optional[str] = None
    chart_fonte_tamanho: Optional[int] = None
    chart_truncar_label: Optional[bool] = None
    chart_truncar_tamanho: Optional[int] = None
    chart_mostrar_valor: Optional[bool] = None


class ParamInput(BaseModel):
    nome: str
    tipo: str = 'text'
    obrigatorio: bool = False
    valor_padrao: Optional[str] = None
    descricao: Optional[str] = None
    variavel_id: Optional[int] = None
    param_slot: Optional[str] = None  # 'inicio' | 'fim' — apenas para date_range


TIPOS_VALIDOS = {
    'kpi', 'chart_line', 'chart_bar',
    'chart_bar_horizontal', 'chart_doughnut',
    'table', 'rag_context', 'map'
}

CAMADAS_MAPA_VALIDAS = {'padrao', 'satelite'}


@router.get("/layout/dashboard")
async def layout_dashboard(user=Depends(get_current_user)):
    try:
        rows = await query_meta("""
            SELECT DISTINCT ON (dl.query_slug)
                dl.query_slug,
                dl.posicao,
                dl.largura,
                COALESCE(dl.titulo, q.nome) AS titulo,
                dl.visivel,
                q.tipo
            FROM dashboard_layout dl
            JOIN queries q ON q.slug = dl.query_slug AND q.ativo = true
            WHERE dl.visivel = true
              AND (dl.empresa_id = $1 OR dl.empresa_id IS NULL)
            ORDER BY dl.query_slug, dl.empresa_id NULLS LAST, dl.posicao
        """, user["empresa_id"])

        layout = sorted([dict(r) for r in rows], key=lambda x: x["posicao"])
        return layout
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar layout: {e}")


@router.get("/executar/{slug}")
async def executar_query(slug: str, user=Depends(get_current_user)):
    try:
        return await resolver_query(
            slug=slug,
            company_slug=user["company_slug"],
            empresa_id=user["empresa_id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao executar query: {e}")


@router.post("/testar")
async def testar_query(body: QueryInput, user=Depends(require_admin)):
    try:
        validar_sql(body.sql_texto)

        company_slug = user["company_slug"]
        if body.testar_empresa_id:
            emp = await query_meta(
                "SELECT slug FROM empresas WHERE id = $1 AND ativo = true",
                body.testar_empresa_id
            )
            if not emp:
                return {"ok": False, "erro": f"Empresa #{body.testar_empresa_id} não encontrada ou inativa"}
            company_slug = emp[0]["slug"]

        # Constrói lista de valores posicionais na ordem dos parâmetros
        valores = [_cast(p.get("valor")) for p in body.testar_parametros]

        resultado = await query_company(company_slug, body.sql_texto, *valores)
        data = [dict(r) for r in resultado[:50]]
        return {
            "ok": True,
            "linhas": len(data),
            "colunas": list(data[0].keys()) if data else [],
            "amostra": data[:5]
        }
    except ValueError as e:
        return {"ok": False, "erro": str(e)}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


@router.get("/")
async def listar_queries(
    tipo: Optional[str] = None,
    empresa_id: Optional[int] = None,
    user=Depends(get_current_user)
):
    try:
        filtros = ["1=1"]
        params = []

        if tipo:
            params.append(tipo)
            filtros.append(f"tipo = ${len(params)}")

        if empresa_id is not None:
            params.append(empresa_id)
            filtros.append(f"(empresa_id = ${len(params)} OR empresa_id IS NULL)")

        where = " AND ".join(filtros)
        rows = await query_meta(
            f"SELECT * FROM queries WHERE {where} ORDER BY tipo, nome",
            *params
        )
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar queries: {e}")


@router.get("/{query_id}/parametros")
async def listar_parametros(query_id: int, user=Depends(get_current_user)):
    try:
        rows = await query_meta(
            "SELECT * FROM query_parametros WHERE query_id = $1 ORDER BY id",
            query_id
        )
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar parâmetros: {e}")


@router.put("/{query_id}/parametros")
async def salvar_parametros(
    query_id: int, parametros: List[ParamInput], user=Depends(require_admin)
):
    try:
        await query_meta("DELETE FROM query_parametros WHERE query_id = $1", query_id)
        for p in parametros:
            await query_meta("""
                INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, param_slot)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """, query_id, p.nome, p.tipo, p.obrigatorio, p.valor_padrao, p.descricao, p.variavel_id, p.param_slot)
        rows = await query_meta(
            "SELECT * FROM query_parametros WHERE query_id = $1 ORDER BY id", query_id
        )
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar parâmetros: {e}")


@router.get("/{query_id}")
async def buscar_query(query_id: int, user=Depends(get_current_user)):
    try:
        rows = await query_meta("SELECT * FROM queries WHERE id = $1", query_id)
        if not rows:
            raise HTTPException(status_code=404, detail="Query não encontrada")
        return dict(rows[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar query: {e}")


@router.post("/")
async def criar_query(body: QueryInput, user=Depends(require_admin)):
    try:
        if not body.slug.strip():
            raise HTTPException(status_code=400, detail="Slug é obrigatório.")
        if not body.nome.strip():
            raise HTTPException(status_code=400, detail="Nome é obrigatório.")
        if body.tipo not in TIPOS_VALIDOS:
            raise HTTPException(status_code=400, detail=f"Tipo inválido. Use: {TIPOS_VALIDOS}")
        if body.mapa_camada not in CAMADAS_MAPA_VALIDAS:
            raise HTTPException(status_code=400, detail=f"Camada de mapa inválida. Use: {CAMADAS_MAPA_VALIDAS}")
        validar_sql(body.sql_texto)

        rows = await query_meta("""
            INSERT INTO queries (
                slug, nome, descricao, sql_texto, tipo, empresa_id, cache_ttl, ativo,
                kpi_cor_fonte, kpi_cor_fundo, mapa_camada,
                chart_fonte_tamanho, chart_truncar_label, chart_truncar_tamanho, chart_mostrar_valor
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            RETURNING *
        """, body.slug, body.nome, body.descricao, body.sql_texto,
            body.tipo, body.empresa_id, body.cache_ttl, body.ativo,
            body.kpi_cor_fonte, body.kpi_cor_fundo, body.mapa_camada,
            body.chart_fonte_tamanho, body.chart_truncar_label,
            body.chart_truncar_tamanho, body.chart_mostrar_valor)
        return dict(rows[0])
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao criar query: {e}")


@router.patch("/{query_id}")
async def atualizar_query(query_id: int, body: QueryUpdate, user=Depends(require_admin)):
    try:
        atual = await query_meta("SELECT * FROM queries WHERE id = $1", query_id)
        if not atual:
            raise HTTPException(status_code=404, detail="Query não encontrada")

        atual = dict(atual[0])
        updates = body.dict(exclude_none=True)

        if not updates:
            return atual

        ALLOWED_COLS = {
            'nome', 'descricao', 'sql_texto', 'tipo', 'cache_ttl', 'ativo',
            'kpi_cor_fonte', 'kpi_cor_fundo', 'mapa_camada',
            'chart_fonte_tamanho', 'chart_truncar_label', 'chart_truncar_tamanho', 'chart_mostrar_valor'
        }
        for k in updates:
            if k not in ALLOWED_COLS:
                raise HTTPException(status_code=400, detail=f"Campo inválido: {k}")

        if "nome" in updates and not updates["nome"].strip():
            raise HTTPException(status_code=400, detail="Nome é obrigatório.")

        if "mapa_camada" in updates and updates["mapa_camada"] not in CAMADAS_MAPA_VALIDAS:
            raise HTTPException(status_code=400, detail=f"Camada de mapa inválida. Use: {CAMADAS_MAPA_VALIDAS}")

        if "sql_texto" in updates:
            validar_sql(updates["sql_texto"])

        campos = []
        valores = []
        for i, (k, v) in enumerate(updates.items(), start=1):
            campos.append(f"{k} = ${i}")
            valores.append(v)

        valores.append(query_id)
        sql = f"UPDATE queries SET {', '.join(campos)} WHERE id = ${len(valores)} RETURNING *"
        rows = await query_meta(sql, *valores)

        if atual.get("empresa_id"):
            emp = await query_meta("SELECT slug FROM empresas WHERE id = $1", atual["empresa_id"])
            if emp:
                await invalidar_cache_empresa(emp[0]["slug"])

        return dict(rows[0])
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar query: {e}")


@router.delete("/{query_id}")
async def deletar_query(query_id: int, user=Depends(require_admin)):
    try:
        rows = await query_meta(
            "DELETE FROM queries WHERE id = $1 RETURNING id, slug", query_id
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Query não encontrada")
        return {"deletado": True, "slug": rows[0]["slug"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao deletar query: {e}")
