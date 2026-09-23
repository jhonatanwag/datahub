from datetime import datetime

import pytest

from services.script_permissoes import FaixaExcedidaError, gerar_script

AGORA = datetime(2026, 9, 23, 10, 0, 0, 123000)


def _p(seq, slug, nome, grupo_seq=None, grupo_nome=None, ordem=0):
    return {"id": 4000 + seq, "seq": seq, "slug": slug, "nome": nome,
            "grupo_seq": grupo_seq, "grupo_nome": grupo_nome, "ordem_menu": ordem}


def test_ids_deterministicos_e_estrutura():
    s = gerar_script([_p(5, "perdas_resumo", "Resumo de Perdas", 2, "PERDAS")], AGORA)
    assert "VALUES(6000, 'GPA ANALYTICS', 1, 'ATIVO', NULL, NULL, NULL)" in s
    assert "VALUES(6002, 'PERDAS', 1, 'ATIVO', NULL, NULL, 6000)" in s
    assert ("VALUES(6005, '2026-09-23 10:00:00.123', 'Resumo de Perdas', 'ATIVO', "
            "'MOBILE', 'perdas_resumo', 0)") in s
    assert "VALUES(6005, 6005, 11)" in s
    assert "VALUES(6105, 'Resumo de Perdas', 1, 'ATIVO', NULL, 6005, 6002)" in s
    assert gerar_script([_p(5, "perdas_resumo", "Resumo de Perdas", 2, "PERDAS")], AGORA) == s


def test_painel_sem_grupo_fica_sob_raiz():
    s = gerar_script([_p(1, "a", "A")], AGORA)
    assert "VALUES(6101, 'A', 1, 'ATIVO', NULL, 6001, 6000)" in s


def test_grupo_aparece_uma_vez():
    s = gerar_script([_p(1, "a", "A", 3, "G"), _p(2, "b", "B", 3, "G")], AGORA)
    assert s.count("VALUES(6003, 'G'") == 1


def test_escape_de_aspas():
    s = gerar_script([_p(1, "a", "D'Agua")], AGORA)
    assert "'D''Agua'" in s


def test_estouro_da_faixa():
    with pytest.raises(FaixaExcedidaError):
        gerar_script([_p(900, "a", "A")], AGORA)
