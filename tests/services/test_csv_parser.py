import pytest

from unicode.services.students import CsvFormatError, parse_students_csv


def test_parse_valid_comma_csv() -> None:
    csv_content = """email,matricula,nome,turma
alice@uni.edu,00123,Alice Smith,T01
bob@uni.edu,00124,Bob Jones,T01
"""
    result = parse_students_csv(csv_content)
    assert not result.has_errors
    assert len(result.valid_rows) == 2
    assert result.valid_rows[0].registration == "00123"
    assert result.valid_rows[0].email == "alice@uni.edu"
    assert result.valid_rows[0].name == "Alice Smith"
    assert result.valid_rows[0].class_group == "T01"
    assert result.valid_rows[0].line_number == 2


def test_parse_semicolon_and_bom_and_accents() -> None:
    csv_content = "\ufeffE-mail;Matrícula;Nome Completo;Turma\nalice@uni.edu;00999;Alice;T02\n"
    result = parse_students_csv(csv_content)
    assert not result.has_errors
    assert len(result.valid_rows) == 1
    assert result.valid_rows[0].registration == "00999"
    assert result.valid_rows[0].email == "alice@uni.edu"


def test_empty_content_raises_format_error() -> None:
    with pytest.raises(CsvFormatError, match="arquivo vazio"):
        parse_students_csv("")
    with pytest.raises(CsvFormatError, match="arquivo vazio"):
        parse_students_csv("   \n\n  ")


def test_missing_required_columns_raises_format_error() -> None:
    with pytest.raises(CsvFormatError, match="coluna obrigatória ausente"):
        parse_students_csv("matricula,nome\n001,Alice")
    with pytest.raises(CsvFormatError, match="coluna obrigatória ausente"):
        parse_students_csv("email,nome\na@b.com,Alice")


def test_duplicate_header_column_raises_format_error() -> None:
    with pytest.raises(CsvFormatError, match="coluna repetida no cabeçalho"):
        parse_students_csv("email,matricula,email\na@b.com,001,c@d.com")


def test_invalid_field_formats() -> None:
    csv_content = """email,matricula,nome,turma
invalid_email,00123,Alice,T01
alice@uni.edu,12a34,Alice,T01
bob@uni.edu,,Bob,T01
,00125,Charlie,T01
"""
    result = parse_students_csv(csv_content)
    assert result.has_errors
    assert len(result.valid_rows) == 0
    assert len(result.errors) == 4
    assert result.errors[0].line_number == 2
    assert "email inválido" in result.errors[0].message
    assert result.errors[1].line_number == 3
    assert "apenas dígitos" in result.errors[1].message
    assert result.errors[2].line_number == 4
    assert "matrícula vazia" in result.errors[2].message
    assert result.errors[3].line_number == 5
    assert "email vazio" in result.errors[3].message


def test_in_file_identical_duplicates_warn_and_deduplicate() -> None:
    csv_content = """email,matricula,nome,turma
alice@uni.edu,00123,Alice,T01
alice@uni.edu,00123,Alice,T01
"""
    result = parse_students_csv(csv_content)
    assert len(result.valid_rows) == 1
    assert len(result.warnings) == 1
    assert result.warnings[0].line_number == 3
    assert "linha idêntica à linha 2" in result.warnings[0].message


def test_in_file_conflicting_duplicates_reject_all() -> None:
    csv_content = """email,matricula,nome,turma
alice1@uni.edu,00123,Alice,T01
alice2@uni.edu,00123,Different Name,T01
bob@uni.edu,00124,Bob,T01
"""
    result = parse_students_csv(csv_content)
    assert len(result.valid_rows) == 1
    assert result.valid_rows[0].registration == "00124"
    assert any("matrícula 00123 repetida nas linhas 2, 3" in e.message for e in result.errors)


def test_in_file_duplicate_email_different_registration_reject_all() -> None:
    csv_content = """email,matricula,nome,turma
same@uni.edu,00123,Alice,T01
same@uni.edu,00124,Bob,T01
"""
    result = parse_students_csv(csv_content)
    assert len(result.valid_rows) == 0
    assert any("email same@uni.edu repetido nas linhas 2, 3" in e.message for e in result.errors)


def test_extra_columns_ignored_and_empty_fields_become_none() -> None:
    csv_content = """email,matricula,nome,turma,notes
alice@uni.edu,00123,,,some extra note
"""
    result = parse_students_csv(csv_content)
    assert not result.has_errors
    assert len(result.valid_rows) == 1
    assert result.valid_rows[0].name is None
    assert result.valid_rows[0].class_group is None
