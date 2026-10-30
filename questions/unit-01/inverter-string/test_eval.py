from solution import inverter_string


def test_inverter_palavra_simples() -> None:
    assert inverter_string("python") == "nohtyp"
    assert inverter_string("abc") == "cba"


def test_inverter_vazia_e_um_caractere() -> None:
    assert inverter_string("") == ""
    assert inverter_string("a") == "a"


def test_inverter_com_espacos() -> None:
    assert inverter_string("ola mundo") == "odnum alo"
