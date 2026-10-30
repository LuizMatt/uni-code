from solution import fatorial


def test_fatorial_base() -> None:
    assert fatorial(0) == 1
    assert fatorial(1) == 1


def test_fatorial_pequenos() -> None:
    assert fatorial(3) == 6
    assert fatorial(5) == 120


def test_fatorial_maior() -> None:
    assert fatorial(7) == 5040
