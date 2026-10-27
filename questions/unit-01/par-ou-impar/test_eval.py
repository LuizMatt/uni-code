from solution import par_ou_impar


def test_pares() -> None:
    assert par_ou_impar(2) == "par"
    assert par_ou_impar(0) == "par"
    assert par_ou_impar(-4) == "par"


def test_impares() -> None:
    assert par_ou_impar(1) == "impar"
    assert par_ou_impar(3) == "impar"
    assert par_ou_impar(-5) == "impar"
