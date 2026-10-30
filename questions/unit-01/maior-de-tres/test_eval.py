from solution import maior_de_tres


def test_maior_distintos() -> None:
    assert maior_de_tres(10, 25, 15) == 25
    assert maior_de_tres(30, 10, 20) == 30
    assert maior_de_tres(1, 2, 99) == 99


def test_maior_negativos() -> None:
    assert maior_de_tres(-5, -2, -10) == -2


def test_maior_com_empate() -> None:
    assert maior_de_tres(7, 7, 3) == 7
