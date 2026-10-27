from datetime import UTC, datetime
from pathlib import Path

from unicode.services.questions import scan_and_validate_questions_dir


def test_scan_valid_unit_and_question(tmp_path: Path) -> None:
    unit_dir = tmp_path / "unit-01"
    unit_dir.mkdir()
    unit_yaml_content = (
        "code: unit-01\n"
        "title: Unidade 1\n"
        "opens_at: '2026-03-01T00:00:00Z'\n"
        "closes_at: '2026-04-01T00:00:00Z'\n"
    )
    (unit_dir / "unit.yaml").write_text(unit_yaml_content, encoding="utf-8")

    q_dir = unit_dir / "soma-dois"
    q_dir.mkdir()
    q_yaml_content = "title: Soma Dois\nactive: true\ntimeout_seconds: 5\n"
    (q_dir / "question.yaml").write_text(q_yaml_content, encoding="utf-8")
    (q_dir / "README.md").write_text("# Enunciado\n", encoding="utf-8")
    (q_dir / "template.py").write_text("def soma(): pass\n", encoding="utf-8")
    (q_dir / "test_eval.py").write_text("def test_ok(): pass\n", encoding="utf-8")

    result = scan_and_validate_questions_dir(tmp_path)
    assert not result.has_errors
    assert len(result.units) == 1
    assert result.units[0].code == "unit-01"
    assert result.units[0].title == "Unidade 1"
    assert result.units[0].opens_at == datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    assert result.units[0].closes_at == datetime(2026, 4, 1, 0, 0, tzinfo=UTC)
    assert len(result.questions) == 1
    assert result.questions[0].slug == "soma-dois"
    assert result.questions[0].unit_code == "unit-01"
    assert result.questions[0].title == "Soma Dois"
    assert result.questions[0].timeout_seconds == 5
    assert result.questions[0].dir_path == q_dir


def test_scan_missing_required_files(tmp_path: Path) -> None:
    unit_dir = tmp_path / "unit-01"
    unit_dir.mkdir()
    (unit_dir / "unit.yaml").write_text("code: unit-01\ntitle: U1\n", encoding="utf-8")

    q_dir = unit_dir / "incompleta"
    q_dir.mkdir()
    (q_dir / "question.yaml").write_text("title: Incompleta\n", encoding="utf-8")
    # Ausentes README.md, template.py, test_eval.py

    result = scan_and_validate_questions_dir(tmp_path)
    assert result.has_errors
    assert any("README.md" in issue.message for issue in result.errors)


def test_scan_nonexistent_root_dir(tmp_path: Path) -> None:
    non_existent = tmp_path / "does_not_exist"
    result = scan_and_validate_questions_dir(non_existent)
    assert result.has_errors
    assert len(result.errors) == 1
    assert "diretório de questões não existe" in result.errors[0].message


def test_scan_unit_code_mismatch(tmp_path: Path) -> None:
    unit_dir = tmp_path / "unit-01"
    unit_dir.mkdir()
    (unit_dir / "unit.yaml").write_text("code: unit-divergente\ntitle: U1\n", encoding="utf-8")

    result = scan_and_validate_questions_dir(tmp_path)
    assert result.has_errors
    assert any("difere do nome da pasta" in issue.message for issue in result.errors)


def test_scan_invalid_dates(tmp_path: Path) -> None:
    unit_dir = tmp_path / "unit-01"
    unit_dir.mkdir()
    unit_yaml_content = (
        "code: unit-01\n"
        "title: U1\n"
        "opens_at: '2026-05-01T00:00:00Z'\n"
        "closes_at: '2026-04-01T00:00:00Z'\n"
    )
    (unit_dir / "unit.yaml").write_text(unit_yaml_content, encoding="utf-8")

    result = scan_and_validate_questions_dir(tmp_path)
    assert result.has_errors
    assert any(
        "closes_at deve ser posterior a opens_at" in issue.message for issue in result.errors
    )


def test_scan_invalid_slug(tmp_path: Path) -> None:
    unit_dir = tmp_path / "unit-01"
    unit_dir.mkdir()
    (unit_dir / "unit.yaml").write_text("code: unit-01\ntitle: U1\n", encoding="utf-8")

    q_dir = unit_dir / "Slug_Invalido!"
    q_dir.mkdir()
    (q_dir / "question.yaml").write_text("title: Questao\n", encoding="utf-8")
    (q_dir / "README.md").write_text("#\n", encoding="utf-8")
    (q_dir / "template.py").write_text("pass\n", encoding="utf-8")
    (q_dir / "test_eval.py").write_text("pass\n", encoding="utf-8")

    result = scan_and_validate_questions_dir(tmp_path)
    assert result.has_errors
    assert any("slug 'Slug_Invalido!' inválido" in issue.message for issue in result.errors)


def test_scan_duplicate_slug(tmp_path: Path) -> None:
    u1 = tmp_path / "unit-01"
    u1.mkdir()
    (u1 / "unit.yaml").write_text("code: unit-01\ntitle: U1\n", encoding="utf-8")
    q1 = u1 / "soma"
    q1.mkdir()
    (q1 / "question.yaml").write_text("title: Soma 1\n", encoding="utf-8")
    (q1 / "README.md").write_text("#\n", encoding="utf-8")
    (q1 / "template.py").write_text("pass\n", encoding="utf-8")
    (q1 / "test_eval.py").write_text("pass\n", encoding="utf-8")

    u2 = tmp_path / "unit-02"
    u2.mkdir()
    (u2 / "unit.yaml").write_text("code: unit-02\ntitle: U2\n", encoding="utf-8")
    q2 = u2 / "soma"
    q2.mkdir()
    (q2 / "question.yaml").write_text("title: Soma 2\n", encoding="utf-8")
    (q2 / "README.md").write_text("#\n", encoding="utf-8")
    (q2 / "template.py").write_text("pass\n", encoding="utf-8")
    (q2 / "test_eval.py").write_text("pass\n", encoding="utf-8")

    result = scan_and_validate_questions_dir(tmp_path)
    assert result.has_errors
    assert any("slug repetido: soma" in issue.message for issue in result.errors)
