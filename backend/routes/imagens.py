from fastapi import APIRouter, Depends, HTTPException, Response
from middleware.auth import get_current_user
from config.databases import query_company

router = APIRouter(prefix="/api/imagens", tags=["Imagens"])


def _mime(foto: bytes) -> str:
    if foto[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if foto[:4] == b"RIFF" and foto[8:12] == b"WEBP":
        return "image/webp"
    if foto[:3] == b"GIF":
        return "image/gif"
    return "image/jpeg"


@router.get("/tipo-veiculo/{tip_veic_id}")
async def imagem_tipo_veiculo(tip_veic_id: int, user=Depends(get_current_user)):
    """Foto vinculada ao tipo de equipamento (tipo_veiculo.imagem_id → imagem.foto),
    lida do banco da empresa ativa. Usada pelo card de perfil do painel de pesquisa de equipamento."""
    rows = await query_company(
        user["company_slug"],
        "SELECT i.foto FROM tipo_veiculo t JOIN imagem i ON i.imagem_id = t.imagem_id "
        "WHERE t.tip_veic_id = $1",
        tip_veic_id,
    )
    if not rows or not rows[0]["foto"]:
        raise HTTPException(status_code=404, detail="Imagem não encontrada")
    foto = bytes(rows[0]["foto"])
    return Response(content=foto, media_type=_mime(foto),
                    headers={"Cache-Control": "private, max-age=3600"})
