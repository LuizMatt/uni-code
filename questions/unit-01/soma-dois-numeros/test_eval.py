from solution import soma


def test_soma_positivos() -> None:
    assert soma(2, 3) == 5


def test_soma_com_negativos() -> None:
    assert soma(-1, 1) == 0
    assert soma(-5, -5) == -10


def test_soma_com_zero() -> None:
    assert soma(0, 0) == 0
    assert soma(10, 0) == 10
