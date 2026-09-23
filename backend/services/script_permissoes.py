"""Gera o script SQL de permissões (obj_sistema, obj_opcao, menu_mobile) que
o usuário roda no PSOEDUCARE para liberar o acesso aos painéis.

Os IDs são determinísticos (derivados de paineis.id / painel_grupos.id),
então gerar o script de novo produz os mesmos IDs e, com ON CONFLICT DO
NOTHING, rodar duas vezes não duplica registros. Faixa reservada: 6000–6999.
"""
from datetime import datetime
from typing import List, Optional

from config.databases import query_meta

FAIXA_MIN = 6000
FAIXA_MAX = 6999
ID_MENU_RAIZ = 6000
OFFSET_GRUPO = 6000     # menu_mobile do grupo = 6000 + painel_grupos.id
OFFSET_PAINEL_MENU = 6100  # menu_mobile do painel = 6100 + paineis.id
OFFSET_PAINEL_OBJ = 6000   # obj_sistema/obj_opcao = 6000 + paineis.id
DESCRICAO_RAIZ = "GPA ANALYTICS"


class FaixaExcedidaError(ValueError):
    pass


def _q(texto) -> str:
    """Literal SQL entre aspas simples, com escape."""
    return "'" + str(texto).replace("'", "''") + "'"


def _checar_faixa(valor: int, o_que: str) -> int:
    if not (FAIXA_MIN <= valor <= FAIXA_MAX):
        raise FaixaExcedidaError(
            f"{o_que}: ID {valor} fora da faixa reservada {FAIXA_MIN}–{FAIXA_MAX}"
        )
    return valor


def gerar_script(paineis: List[dict], agora: Optional[datetime] = None) -> str:
    """`paineis`: dicts com id, slug, nome, grupo_id (ou None), grupo_nome,
    ordem_menu. Devolve o SQL completo (raiz + grupos + painéis)."""
    agora = agora or datetime.now()
    ts = agora.strftime("%Y-%m-%d %H:%M:%S.") + f"{agora.microsecond // 1000:03d}"

    linhas = [
        "-- Script de permissões GPA ANALYTICS (gerado pelo DataHub)",
        "-- Pode ser executado mais de uma vez: registros já existentes são ignorados.",
        "",
        "-- Menu principal",
        "INSERT INTO public.menu_mobile "
        "(menu_mob_id, descricao, ordem, situacao_cadastro, view_id, obj_sist_id, sub_menu_mob_id) "
        f"VALUES({ID_MENU_RAIZ}, {_q(DESCRICAO_RAIZ)}, 1, 'ATIVO', NULL, NULL, NULL) "
        "ON CONFLICT DO NOTHING;",
    ]

    grupos_vistos = set()
    ordem_grupo = 0
    blocos_paineis = []
    for p in sorted(paineis, key=lambda x: (x.get("ordem_menu") or 0, x["id"])):
        obj_id = _checar_faixa(OFFSET_PAINEL_OBJ + p["id"], f"Painel {p['slug']}")
        menu_id = _checar_faixa(OFFSET_PAINEL_MENU + p["id"], f"Menu do painel {p['slug']}")

        pai = ID_MENU_RAIZ
        if p.get("grupo_id"):
            gid = _checar_faixa(OFFSET_GRUPO + p["grupo_id"], f"Grupo {p.get('grupo_nome')}")
            pai = gid
            if gid not in grupos_vistos:
                grupos_vistos.add(gid)
                ordem_grupo += 1
                linhas += [
                    "",
                    f"-- Grupo: {p.get('grupo_nome')}".replace("\n", " "),
                    "INSERT INTO public.menu_mobile "
                    "(menu_mob_id, descricao, ordem, situacao_cadastro, view_id, obj_sist_id, sub_menu_mob_id) "
                    f"VALUES({gid}, {_q(p.get('grupo_nome'))}, {ordem_grupo}, 'ATIVO', NULL, NULL, {ID_MENU_RAIZ}) "
                    "ON CONFLICT DO NOTHING;",
                ]

        blocos_paineis.append((p, obj_id, menu_id, pai))

    for i, (p, obj_id, menu_id, pai) in enumerate(blocos_paineis, start=1):
        linhas += [
            "",
            f"-- Painel: {p['nome']} ({p['slug']})".replace("\n", " "),
            "INSERT INTO public.obj_sistema "
            "(obj_sist_id, data_cadastro, descricao, situacao_cadastro, tipo_sistema, url, versao) "
            f"VALUES({obj_id}, {_q(ts)}, {_q(p['nome'])}, 'ATIVO', 'MOBILE', {_q(p['slug'])}, 0) "
            "ON CONFLICT DO NOTHING;",
            "INSERT INTO public.obj_opcao (obj_opc_id, obj_sist_id, opcao_id) "
            f"VALUES({obj_id}, {obj_id}, 11) ON CONFLICT DO NOTHING;",
            "INSERT INTO public.menu_mobile "
            "(menu_mob_id, descricao, ordem, situacao_cadastro, view_id, obj_sist_id, sub_menu_mob_id) "
            f"VALUES({menu_id}, {_q(p['nome'])}, {i}, 'ATIVO', NULL, {obj_id}, {pai}) "
            "ON CONFLICT DO NOTHING;",
        ]

    return "\n".join(linhas) + "\n"


_SELECT = """
    SELECT p.id, p.slug, p.nome, p.ordem_menu, p.grupo_id, g.nome AS grupo_nome
    FROM paineis p
    LEFT JOIN painel_grupos g ON g.id = p.grupo_id
"""


async def script_do_painel(painel_id: int) -> Optional[str]:
    rows = await query_meta(_SELECT + " WHERE p.id = $1", painel_id)
    if not rows:
        return None
    return gerar_script([dict(r) for r in rows])


async def script_da_empresa(empresa_id: int) -> str:
    rows = await query_meta(
        _SELECT + " WHERE p.ativo = true AND (p.empresa_id = $1 OR p.empresa_id IS NULL)",
        empresa_id,
    )
    return gerar_script([dict(r) for r in rows])
