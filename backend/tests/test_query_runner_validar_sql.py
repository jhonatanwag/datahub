import pytest

from services.query_runner import validar_sql


def test_select_simples_e_permitido():
    assert validar_sql("SELECT 1") is True


def test_cte_with_select_e_permitida():
    sql = """
    WITH ultimas AS (
        SELECT id, ROW_NUMBER() OVER (PARTITION BY grupo ORDER BY data DESC) AS rn
        FROM tabela
    )
    SELECT COUNT(*) AS valor, 'label' AS label
    FROM ultimas
    WHERE rn = 1
    """
    assert validar_sql(sql) is True


def test_cte_com_espacos_e_quebras_iniciais_e_permitida():
    assert validar_sql("   \n  WITH x AS (SELECT 1) SELECT * FROM x") is True


def test_query_nao_select_e_rejeitada():
    with pytest.raises(ValueError):
        validar_sql("EXPLAIN SELECT 1")


def test_palavra_proibida_dentro_de_cte_e_rejeitada():
    with pytest.raises(ValueError):
        validar_sql("WITH x AS (DELETE FROM tabela RETURNING id) SELECT * FROM x")
