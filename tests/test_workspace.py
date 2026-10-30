from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from unicode.models.assignment import Assignment
from unicode.services.assignments import (
    archive_replaced_workspaces,
    provision_workspace,
)


def _make_assignment(
    slug: str = "soma-dois-numeros",
    round_num: int = 1,
) -> Assignment:
    return Assignment(
        id=1,
        student_registration="2026001",
        unit_id=1,
        unit_code="unit-01",
        question_id=10,
        question_slug=slug,
        round=round_num,
        state="pending",
        points=Decimal("0.0"),
        created_at=datetime.now(UTC),
    )


def _create_catalog_question(questions_dir: Path, unit_code: str, slug: str) -> Path:
    q_dir = questions_dir / unit_code / slug
    q_dir.mkdir(parents=True, exist_ok=True)
    (q_dir / "question.yaml").write_text(f"title: {slug}\n", encoding="utf-8")
    (q_dir / "README.md").write_text(f"# Enunciado {slug}\n", encoding="utf-8")
    (q_dir / "template.py").write_text("def solve():\n    pass\n", encoding="utf-8")
    (q_dir / "test_eval.py").write_text("def test_secret():\n    assert True\n", encoding="utf-8")
    return q_dir


def test_provision_workspace_creates_readme_and_solution_without_hidden_tests(
    tmp_path: Path,
) -> None:
    questions_dir = tmp_path / "questions"
    workspaces_dir = tmp_path / "workspaces"
    _create_catalog_question(questions_dir, "unit-01", "soma-dois-numeros")

    assignment = _make_assignment("soma-dois-numeros", round_num=1)
    created_dirs = provision_workspace(workspaces_dir, questions_dir, [assignment])

    assert len(created_dirs) == 1
    target_dir = workspaces_dir / "2026001" / "unit-01" / "soma-dois-numeros"
    assert created_dirs[0] == target_dir
    readme_content = (target_dir / "README.md").read_text(encoding="utf-8")
    assert readme_content == "# Enunciado soma-dois-numeros\n"
    assert (target_dir / "solution.py").read_text(encoding="utf-8") == "def solve():\n    pass\n"
    assert not (target_dir / "test_eval.py").exists()
    assert not (target_dir / "question.yaml").exists()
    assert not (target_dir / "template.py").exists()


def test_provision_workspace_does_not_overwrite_existing_student_solution(
    tmp_path: Path,
) -> None:
    questions_dir = tmp_path / "questions"
    workspaces_dir = tmp_path / "workspaces"
    _create_catalog_question(questions_dir, "unit-01", "soma-dois-numeros")

    assignment = _make_assignment("soma-dois-numeros", round_num=1)
    provision_workspace(workspaces_dir, questions_dir, [assignment])

    solution_file = workspaces_dir / "2026001" / "unit-01" / "soma-dois-numeros" / "solution.py"
    solution_file.write_text("def solve():\n    return 42\n", encoding="utf-8")

    # Re-provisioning must preserve the student's modified solution.py
    provision_workspace(workspaces_dir, questions_dir, [assignment])
    assert solution_file.read_text(encoding="utf-8") == "def solve():\n    return 42\n"


def test_archive_replaced_workspaces_moves_to_archive_round_dir(
    tmp_path: Path,
) -> None:
    questions_dir = tmp_path / "questions"
    workspaces_dir = tmp_path / "workspaces"
    _create_catalog_question(questions_dir, "unit-01", "soma-dois-numeros")

    a_round1 = _make_assignment("soma-dois-numeros", round_num=1)
    provision_workspace(workspaces_dir, questions_dir, [a_round1])

    sol_path = workspaces_dir / "2026001" / "unit-01" / "soma-dois-numeros" / "solution.py"
    sol_path.write_text("# tentativa rodada 1\n", encoding="utf-8")

    archived_paths = archive_replaced_workspaces(workspaces_dir, [a_round1])
    expected_archive = (
        workspaces_dir / "2026001" / "unit-01" / "_archive" / "round-1" / "soma-dois-numeros"
    )
    assert archived_paths == [expected_archive]
    archived_sol = (expected_archive / "solution.py").read_text(encoding="utf-8")
    assert archived_sol == "# tentativa rodada 1\n"
    assert not (workspaces_dir / "2026001" / "unit-01" / "soma-dois-numeros").exists()

    # If the same question is drawn again in round 2, a clean solution.py is created
    a_round2 = _make_assignment("soma-dois-numeros", round_num=2)
    provision_workspace(workspaces_dir, questions_dir, [a_round2])
    assert sol_path.read_text(encoding="utf-8") == "def solve():\n    pass\n"
