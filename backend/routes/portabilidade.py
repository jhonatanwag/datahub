import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response

from middleware.auth import require_admin
from services.portabilidade import montar_bundle_painel

router = APIRouter(tags=["Portabilidade"])


@router.get("/api/paineis/{painel_id}/exportar")
async def exportar_painel(painel_id: int, user=Depends(require_admin)):
    bundle = await montar_bundle_painel(painel_id)
    if bundle is None:
        raise HTTPException(404, "Painel não encontrado")

    slug = bundle["painel"]["slug"]
    filename = f"painel-{slug}-{date.today():%Y%m%d}.json"
    corpo = json.dumps(bundle, ensure_ascii=False, default=str, indent=2)
    return Response(
        content=corpo,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
