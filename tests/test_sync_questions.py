import json
import shutil
from pathlib import Path

import pytest

from unicode.db import DictConnection
from unicode.models.question import QuestionIssue, ScanResult
from unicode.services.questions import scan_and_validate_questions_dir, sync_questions


def test_sync_questions_aborts_on_scan_errors() -> None:
    scanned = ScanResult(issues=[QuestionIssue(path="u1", message="erro", kind="error")])
    # conn is not used when has_errors is true
    report = sync_questions(None, scanned)  # type: ignore[arg-type]
    assert report.has_errors
    assert len(report.errors) == 1
    assert report.units_created == 0
    assert report.questions_created == 0


class FakeCursor:
    def __init__(
        self,
        fetchone_val: dict[str, object] | None = None,
        fetchall_val: list[dict[str, object]] | None = None,
    ) -> None:
        self._fetchone_val = fetchone_val
        self._fetchall_val = fetchall_val or []

    def fetchone(self) -> dict[str, object] | None:
        return self._fetchone_val

    def fetchall(self) -> list[dict[str, object]]:
        return self._fetchall_val


class FakeTransactionContext:
    def __enter__(self) -> "FakeTransactionContext":
        return self

    def __exit__(self, *args: object) -> None:
        pass


class FakeConn:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple[object, ...]]] = []
        self.units: dict[str, dict[str, object]] = {}
        self.questions: dict[str, dict[str, object]] = {}

    def transaction(self) -> FakeTransactionContext:
        return FakeTransactionContext()

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> FakeCursor:
        self.queries.append((sql, params))
        if "SELECT id, title, opens_at, closes_at FROM units WHERE code = %s" in sql:
            code = str(params[0])
            if code in self.units:
                return FakeCursor(fetchone_val=self.units[code])
            return FakeCursor(fetchone_val=None)
        if "INSERT INTO units" in sql:
            code = str(params[0])
            unit_id = len(self.units) + 1
            row = {
                "id": unit_id,
                "code": code,
                "title": params[1],
                "opens_at": params[2],
                "closes_at": params[3],
            }
            self.units[code] = row
            return FakeCursor(fetchone_val={"id": unit_id})
        if "SELECT id, unit_id, title, active FROM questions WHERE slug = %s" in sql:
            slug = str(params[0])
            if slug in self.questions:
                return FakeCursor(fetchone_val=self.questions[slug])
            return FakeCursor(fetchone_val=None)
        if "INSERT INTO questions" in sql:
            slug = str(params[1])
            q_id = len(self.questions) + 1
            row = {
                "id": q_id,
                "unit_id": params[0],
                "slug": slug,
                "title": params[2],
                "active": params[3],
            }
            self.questions[slug] = row
            return FakeCursor(fetchone_val={"id": q_id})
        if "UPDATE questions SET active = FALSE" in sql:
            unit_id = int(str(params[0]))
            deactivated = []
            if len(params) > 1 and isinstance(params[1], list):
                active_slugs = set(params[1])
                for q in self.questions.values():
                    if q["unit_id"] == unit_id and q["active"] and q["slug"] not in active_slugs:
                        q["active"] = False
                        deactivated.append({"id": q["id"]})
            return FakeCursor(fetchall_val=deactivated)
        return FakeCursor()


def test_sync_questions_unit_and_question_sync_with_fake_conn() -> None:
    from unicode.models.question import QuestionDefinition, UnitDefinition

    conn = FakeConn()
    scanned = ScanResult(
        units=[UnitDefinition(code="u1", title="Unit 1")],
        questions=[QuestionDefinition(slug="q1", unit_code="u1", title="Q1")],
    )
    report = sync_questions(conn, scanned)  # type: ignore[arg-type]
    assert report.units_created == 1
    assert report.questions_created == 1
    assert report.questions_deactivated == 0
    assert any("INSERT INTO audit_log" in q[0] for q in conn.queries)


@pytest.mark.db
def test_sync_questions_upsert_and_audit(daemon_conn: DictConnection, tmp_path: Path) -> None:
    unit_dir = tmp_path / "unit-01"
    unit_dir.mkdir()
    (unit_dir / "unit.yaml").write_text("code: unit-01\ntitle: Unidade 1\n", encoding="utf-8")

    q_dir = unit_dir / "soma-dois"
    q_dir.mkdir()
    (q_dir / "question.yaml").write_text("title: Soma Dois\nactive: true\n", encoding="utf-8")
    (q_dir / "README.md").write_text("# Soma\n", encoding="utf-8")
    (q_dir / "template.py").write_text("pass\n", encoding="utf-8")
    (q_dir / "test_eval.py").write_text("pass\n", encoding="utf-8")

    scanned = scan_and_validate_questions_dir(tmp_path)
    report = sync_questions(daemon_conn, scanned, actor="admin")

    assert report.units_created == 1
    assert report.questions_created == 1
    assert not report.has_errors

    # Verifica no banco
    q_row = daemon_conn.execute(
        "SELECT slug, title, active FROM questions WHERE slug = 'soma-dois'"
    ).fetchone()
    assert q_row is not None
    assert q_row["title"] == "Soma Dois"
    assert q_row["active"] is True

    # Verifica audit_log
    audit = daemon_conn.execute(
        "SELECT details FROM audit_log WHERE action = 'sync_questions'"
    ).fetchone()
    assert audit is not None
    details = (
        audit["details"] if isinstance(audit["details"], dict) else json.loads(audit["details"])
    )
    assert details["questions_created"] == 1


@pytest.mark.db
def test_sync_questions_soft_deactivates_missing_from_disk(
    daemon_conn: DictConnection, tmp_path: Path
) -> None:
    # 1. Primeira sincronização com duas questões
    unit_dir = tmp_path / "unit-01"
    unit_dir.mkdir()
    (unit_dir / "unit.yaml").write_text("code: unit-01\ntitle: U1\n", encoding="utf-8")

    for slug in ("q1", "q2"):
        qd = unit_dir / slug
        qd.mkdir()
        (qd / "question.yaml").write_text(f"title: {slug}\n", encoding="utf-8")
        (qd / "README.md").write_text("#\n", encoding="utf-8")
        (qd / "template.py").write_text("pass\n", encoding="utf-8")
        (qd / "test_eval.py").write_text("pass\n", encoding="utf-8")

    sync_questions(daemon_conn, scan_and_validate_questions_dir(tmp_path))

    # 2. Remove 'q2' do disco
    shutil.rmtree(unit_dir / "q2")

    # 3. Segunda sincronização
    report = sync_questions(daemon_conn, scan_and_validate_questions_dir(tmp_path))
    assert report.questions_deactivated == 1

    # q2 continua no banco mas inativa
    q2_row = daemon_conn.execute("SELECT active FROM questions WHERE slug = 'q2'").fetchone()
    assert q2_row is not None
    assert q2_row["active"] is False
