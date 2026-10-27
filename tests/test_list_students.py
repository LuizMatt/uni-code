import pytest

from unicode.db import DictConnection
from unicode.services.students import import_students, list_students, parse_students_csv

pytestmark = pytest.mark.db


def test_list_students_ordering_and_filtering(daemon_conn: DictConnection) -> None:
    csv_content = """email,matricula,nome,turma
b@uni.edu,00200,B,T01
a@uni.edu,00100,A,T02
c@uni.edu,00050,C,T01
"""
    import_students(daemon_conn, parse_students_csv(csv_content), source="seed.csv")

    all_students = list_students(daemon_conn)
    assert len(all_students) == 3
    assert [s.registration for s in all_students] == ["00050", "00100", "00200"]

    t01_students = list_students(daemon_conn, class_group="T01")
    assert len(t01_students) == 2
    assert [s.registration for s in t01_students] == ["00050", "00200"]

    empty = list_students(daemon_conn, class_group="NON_EXISTENT")
    assert len(empty) == 0
