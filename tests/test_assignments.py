import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from tests.support import TEST_DAEMON_URL, TEST_OWNER_URL
from unicode.db import DictConnection
from unicode.models import Assignment
from unicode.services.assignments import (
    InsufficientQuestionsError,
    NoActiveAssignmentsError,
    StudentNotFoundError,
    UnitNotFoundError,
    draw_assignments,
    list_active_assignments,
    reset_assignments,
)


class FakeCursor:
    def __init__(
        self,
        fetchone_val: dict[str, Any] | None = None,
        fetchall_val: list[dict[str, Any]] | None = None,
    ) -> None:
        self._fetchone_val = fetchone_val
        self._fetchall_val = fetchall_val or []

    def fetchone(self) -> dict[str, Any] | None:
        return self._fetchone_val

    def fetchall(self) -> list[dict[str, Any]]:
        return self._fetchall_val


class FakeAssignmentConn:
    """In-memory fake connection to validate draw/reset business rules offline."""

    def __init__(self) -> None:
        self.students: set[str] = {"2026001"}
        self.units: dict[str, int] = {"unit-01": 1}
        self.questions: list[dict[str, Any]] = [
            {
                "id": i,
                "unit_id": 1,
                "slug": f"q0{i}",
                "title": f"Questão {i}",
                "active": True,
            }
            for i in range(1, 6)
        ]
        self.assignments: list[dict[str, Any]] = []
        self.attempts: list[dict[str, Any]] = []
        self.audit_logs: list[dict[str, Any]] = []
        self.locks_acquired: list[tuple[str, int]] = []
        self._next_id = 1

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> FakeCursor:
        normalized = " ".join(sql.split())

        if "FROM students WHERE registration = %s" in normalized:
            reg = str(params[0])
            if reg in self.students:
                return FakeCursor(fetchone_val={"registration": reg})
            return FakeCursor(fetchone_val=None)

        if "FROM units WHERE code = %s" in normalized:
            code = str(params[0])
            if code in self.units:
                return FakeCursor(fetchone_val={"id": self.units[code], "code": code})
            return FakeCursor(fetchone_val=None)

        if "pg_advisory_xact_lock" in normalized:
            self.locks_acquired.append((str(params[0]), int(params[1])))
            return FakeCursor(fetchone_val={"pg_advisory_xact_lock": None})

        if (
            "FROM assignments a" in normalized
            and "WHERE a.student_registration = %s AND a.unit_id = %s AND a.state <> 'replaced'"
            in normalized
        ):
            reg = str(params[0])
            uid = int(params[1])
            q_by_id = {q["id"]: q for q in self.questions}
            u_code = next(c for c, i in self.units.items() if i == uid)
            rows = [
                {
                    "id": a["id"],
                    "student_registration": a["student_registration"],
                    "unit_id": a["unit_id"],
                    "unit_code": u_code,
                    "question_id": a["question_id"],
                    "question_slug": q_by_id[a["question_id"]]["slug"],
                    "round": a["round"],
                    "state": a["state"],
                    "points": a["points"],
                    "created_at": a["created_at"],
                }
                for a in sorted(self.assignments, key=lambda x: x["id"])
                if a["student_registration"] == reg
                and a["unit_id"] == uid
                and a["state"] != "replaced"
            ]
            return FakeCursor(fetchall_val=rows)

        if (
            "FROM assignments a" in normalized
            and "WHERE a.student_registration = %s AND a.state <> 'replaced'" in normalized
            and "COUNT(att.id)" not in normalized
        ):
            reg = str(params[0])
            q_by_id = {q["id"]: q for q in self.questions}
            uid_to_code = {i: c for c, i in self.units.items()}
            rows = [
                {
                    "id": a["id"],
                    "student_registration": a["student_registration"],
                    "unit_id": a["unit_id"],
                    "unit_code": uid_to_code.get(a["unit_id"], "unit-01"),
                    "question_id": a["question_id"],
                    "question_slug": q_by_id[a["question_id"]]["slug"],
                    "round": a["round"],
                    "state": a["state"],
                    "points": a["points"],
                    "created_at": a["created_at"],
                }
                for a in sorted(self.assignments, key=lambda x: x["id"])
                if a["student_registration"] == reg and a["state"] != "replaced"
            ]
            return FakeCursor(fetchall_val=rows)

        if "SELECT id, slug FROM questions WHERE unit_id = %s AND active = TRUE" in normalized:
            uid = int(params[0])
            rows = [
                {"id": q["id"], "slug": q["slug"]}
                for q in self.questions
                if q["unit_id"] == uid and q["active"]
            ]
            return FakeCursor(fetchall_val=rows)

        if (
            "SELECT question_id, round FROM assignments "
            "WHERE student_registration = %s AND unit_id = %s"
        ) in normalized:
            reg = str(params[0])
            uid = int(params[1])
            rows = [
                {"question_id": a["question_id"], "round": a["round"]}
                for a in self.assignments
                if a["student_registration"] == reg and a["unit_id"] == uid
            ]
            return FakeCursor(fetchall_val=rows)

        if (
            "UPDATE assignments SET state = 'replaced', points = 0 WHERE id = ANY(%s)"
            in normalized
        ):
            target_ids = set(params[0])
            for a in self.assignments:
                if a["id"] in target_ids:
                    a["state"] = "replaced"
                    a["points"] = Decimal("0.0")
            return FakeCursor()

        if "INSERT INTO assignments" in normalized:
            reg, qid, uid, rnd = str(params[0]), int(params[1]), int(params[2]), int(params[3])
            now = datetime.now(UTC)
            aid = self._next_id
            self._next_id += 1
            rec = {
                "id": aid,
                "student_registration": reg,
                "question_id": qid,
                "unit_id": uid,
                "round": rnd,
                "state": "pending",
                "points": Decimal("0.0"),
                "created_at": now,
            }
            self.assignments.append(rec)
            return FakeCursor(
                fetchone_val={
                    "id": aid,
                    "state": "pending",
                    "points": Decimal("0.0"),
                    "created_at": now,
                }
            )

        if "INSERT INTO audit_log" in normalized:
            self.audit_logs.append(
                {
                    "actor": params[0],
                    "action": params[1],
                    "details": json.loads(str(params[2])),
                }
            )
            return FakeCursor()

        if "COUNT(att.id) AS attempts_used" in normalized:
            reg = str(params[0])
            unit_filter = str(params[1]) if len(params) > 1 else None
            q_by_id = {q["id"]: q for q in self.questions}
            code_by_uid = {uid: c for c, uid in self.units.items()}
            rows = []
            for a in sorted(
                self.assignments, key=lambda x: (code_by_uid[x["unit_id"]], x["id"])
            ):
                if a["student_registration"] != reg or a["state"] == "replaced":
                    continue
                u_code = code_by_uid[a["unit_id"]]
                if unit_filter is not None and u_code != unit_filter:
                    continue
                q = q_by_id[a["question_id"]]
                used = sum(
                    1 for att in self.attempts if att["assignment_id"] == a["id"]
                )
                rows.append(
                    {
                        "unit_code": u_code,
                        "question_slug": q["slug"],
                        "question_title": q["title"],
                        "round": a["round"],
                        "state": a["state"],
                        "points": a["points"],
                        "attempts_used": used,
                    }
                )
            return FakeCursor(fetchall_val=rows)

        if (
            "SELECT u.code AS unit_code FROM assignments a" in normalized
            and "q.slug = %s" in normalized
        ):
            reg, slug = str(params[0]), str(params[1])
            q_by_id = {q["id"]: q for q in self.questions}
            code_by_uid = {uid: c for c, uid in self.units.items()}
            for a in self.assignments:
                if (
                    a["student_registration"] == reg
                    and a["state"] != "replaced"
                    and q_by_id[a["question_id"]]["slug"] == slug
                ):
                    return FakeCursor(
                        fetchone_val={"unit_code": code_by_uid[a["unit_id"]]}
                    )
            return FakeCursor(fetchone_val=None)

        raise AssertionError(f"Unexpected SQL in FakeAssignmentConn: {normalized}")


def test_draw_assignments_initial_and_idempotent_fake() -> None:
    conn = FakeAssignmentConn()
    res1 = draw_assignments(conn, "2026001", "unit-01")  # type: ignore[arg-type]
    assert res1.created is True
    assert len(res1.assignments) == 2
    assert {a.round for a in res1.assignments} == {1}
    assert len(conn.audit_logs) == 1
    assert conn.audit_logs[0]["action"] == "draw_assignments"
    assert conn.locks_acquired == [("2026001", 1)]

    # Calling again is idempotent and does not re-draw or add audit log
    res2 = draw_assignments(conn, "2026001", "unit-01")  # type: ignore[arg-type]
    assert res2.created is False
    assert [a.question_slug for a in res2.assignments] == [
        a.question_slug for a in res1.assignments
    ]
    assert len(conn.audit_logs) == 1


def test_draw_assignments_errors_fake() -> None:
    conn = FakeAssignmentConn()
    with pytest.raises(StudentNotFoundError):
        draw_assignments(conn, "9999999", "unit-01")  # type: ignore[arg-type]

    with pytest.raises(UnitNotFoundError):
        draw_assignments(conn, "2026001", "unit-99")  # type: ignore[arg-type]

    for q in conn.questions[1:]:
        q["active"] = False
    with pytest.raises(InsufficientQuestionsError):
        draw_assignments(conn, "2026001", "unit-01")  # type: ignore[arg-type]


def test_reset_assignments_tiers_and_single_question_fake() -> None:
    conn = FakeAssignmentConn()
    draw = draw_assignments(conn, "2026001", "unit-01")  # type: ignore[arg-type]
    r1_slugs = {a.question_slug for a in draw.assignments}

    # Full unit reset (Round 2): must pick 2 from the 3 never-seen questions
    reset1 = reset_assignments(conn, "2026001", "unit-01")  # type: ignore[arg-type]
    assert reset1.new_round == 2
    assert reset1.reused_questions is False
    r2_slugs = {a.question_slug for a in reset1.new_assignments}
    assert len(r2_slugs) == 2
    assert r1_slugs.isdisjoint(r2_slugs)

    # Full unit reset again (Round 3): only 1 never-seen left,
    # must take 1 from Tier 1 + 1 from Tier 2 (Round 1)
    reset2 = reset_assignments(conn, "2026001", "unit-01")  # type: ignore[arg-type]
    assert reset2.new_round == 3
    assert reset2.reused_questions is True
    r3_slugs = {a.question_slug for a in reset2.new_assignments}
    assert len(r3_slugs) == 2
    # Must not repeat the questions that were just replaced in Round 2
    assert r3_slugs.isdisjoint(r2_slugs)

    # Single question reset (Round 4): replace only one of Round 3's questions
    target_slug = reset2.new_assignments[0].question_slug
    kept_slug = reset2.new_assignments[1].question_slug
    reset3 = reset_assignments(
        conn, "2026001", "unit-01", question_slug=target_slug  # type: ignore[arg-type]
    )
    assert reset3.new_round == 4
    assert len(reset3.replaced_assignments) == 1
    assert reset3.replaced_assignments[0].question_slug == target_slug
    assert len(reset3.new_assignments) == 1
    new_single_slug = reset3.new_assignments[0].question_slug
    assert new_single_slug != target_slug
    assert new_single_slug != kept_slug

    active_now = list_active_assignments(conn, "2026001", "unit-01")  # type: ignore[arg-type]
    assert {a.question_slug for a in active_now} == {kept_slug, new_single_slug}


def test_reset_without_active_assignments_raises_fake() -> None:
    conn = FakeAssignmentConn()
    with pytest.raises(NoActiveAssignmentsError):
        reset_assignments(conn, "2026001", "unit-01")  # type: ignore[arg-type]


def test_list_all_active_assignments_fake_unit() -> None:
    from unicode.services.assignments import list_all_active_assignments

    conn = FakeAssignmentConn()
    assert list_all_active_assignments(conn, "2026001") == []  # type: ignore[arg-type]

    draw = draw_assignments(conn, "2026001", "unit-01")  # type: ignore[arg-type]
    active = list_all_active_assignments(conn, "2026001")  # type: ignore[arg-type]
    assert len(active) == 2
    assert [a.id for a in active] == [a.id for a in draw.assignments]

    with pytest.raises(StudentNotFoundError):
        list_all_active_assignments(conn, "unknown")  # type: ignore[arg-type]


def _seed_unit_and_student(conn: DictConnection, num_questions: int = 5) -> None:
    conn.execute(
        "INSERT INTO students (registration, email, name) "
        "VALUES ('2026001', 'a@uni.edu', 'Aluno 1')"
    )
    row = conn.execute(
        "INSERT INTO units (code, title) VALUES ('unit-01', 'Unidade 1') RETURNING id"
    ).fetchone()
    assert row is not None
    unit_id = int(row["id"])
    for idx in range(1, num_questions + 1):
        conn.execute(
            "INSERT INTO questions (unit_id, slug, title, active) VALUES (%s, %s, %s, TRUE)",
            (unit_id, f"q0{idx}", f"Questão {idx}"),
        )


@pytest.mark.db
def test_db_draw_and_reset_flow(daemon_conn: DictConnection) -> None:
    _seed_unit_and_student(daemon_conn, num_questions=5)

    draw1 = draw_assignments(daemon_conn, "2026001", "unit-01")
    assert draw1.created is True
    assert len(draw1.assignments) == 2
    slugs1 = {a.question_slug for a in draw1.assignments}

    # Idempotency check
    draw2 = draw_assignments(daemon_conn, "2026001", "unit-01")
    assert draw2.created is False
    assert {a.question_slug for a in draw2.assignments} == slugs1

    # Simulate student passing the first assignment (state='passed', points=0.5)
    first_id = draw1.assignments[0].id
    daemon_conn.execute(
        "UPDATE assignments SET state = 'passed', points = 0.5 WHERE id = %s",
        (first_id,),
    )

    # Reset full unit: must zero points on replaced assignment
    # to satisfy ck_assignments_points_match_state
    reset1 = reset_assignments(daemon_conn, "2026001", "unit-01", actor="prof")
    assert reset1.new_round == 2
    assert reset1.reused_questions is False
    slugs2 = {a.question_slug for a in reset1.new_assignments}
    assert slugs1.isdisjoint(slugs2)

    replaced_row = daemon_conn.execute(
        "SELECT state, points FROM assignments WHERE id = %s", (first_id,)
    ).fetchone()
    assert replaced_row is not None
    assert replaced_row["state"] == "replaced"
    assert replaced_row["points"] == Decimal("0.0")

    # Round 3: only 1 unseen question left, so 1 from Tier 1 + 1 reused from Round 1 (Tier 2)
    # Also verifies uq_assignments_active allows re-inserting a previously 'replaced' question_id
    reset2 = reset_assignments(daemon_conn, "2026001", "unit-01", actor="prof")
    assert reset2.new_round == 3
    assert reset2.reused_questions is True
    slugs3 = {a.question_slug for a in reset2.new_assignments}
    assert slugs3.isdisjoint(slugs2)

    # Round 4: single-question reset
    target_slug = reset2.new_assignments[0].question_slug
    kept_slug = reset2.new_assignments[1].question_slug
    reset3 = reset_assignments(
        daemon_conn, "2026001", "unit-01", question_slug=target_slug, actor="prof"
    )
    assert reset3.new_round == 4
    assert len(reset3.replaced_assignments) == 1
    assert len(reset3.new_assignments) == 1
    active_after = list_active_assignments(daemon_conn, "2026001", "unit-01")
    assert {a.question_slug for a in active_after} == {
        kept_slug,
        reset3.new_assignments[0].question_slug,
    }


@pytest.mark.db
def test_db_concurrent_draw_advisory_lock(
    database_available: None, migrated_db: None
) -> None:
    with psycopg.connect(TEST_DAEMON_URL, row_factory=dict_row) as setup_conn:
        with setup_conn.transaction():
            _seed_unit_and_student(setup_conn, num_questions=5)

    try:
        def worker() -> list[str]:
            with (
                psycopg.connect(TEST_DAEMON_URL, row_factory=dict_row) as w_conn,
                w_conn.transaction(),
            ):
                res = draw_assignments(w_conn, "2026001", "unit-01")
                return sorted(a.question_slug for a in res.assignments)

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(worker)
            f2 = pool.submit(worker)
            r1 = f1.result()
            r2 = f2.result()

        assert r1 == r2
        assert len(r1) == 2

        with psycopg.connect(TEST_DAEMON_URL, row_factory=dict_row) as check_conn:
            rows = check_conn.execute(
                "SELECT count(*) AS n FROM assignments WHERE student_registration = '2026001'"
            ).fetchone()
            assert rows is not None
            assert rows["n"] == 2
    finally:
        with psycopg.connect(TEST_OWNER_URL) as cleanup_conn:
            cleanup_conn.execute("DELETE FROM audit_log")
            cleanup_conn.execute("DELETE FROM assignments")
            cleanup_conn.execute("DELETE FROM questions")
            cleanup_conn.execute("DELETE FROM units")
            cleanup_conn.execute("DELETE FROM students")


def test_get_student_status_and_resolve_unit_fake() -> None:
    from unicode.services.assignments import (
        get_student_status,
        resolve_student_question_unit,
    )

    conn = FakeAssignmentConn()
    draw = draw_assignments(conn, "2026001", "unit-01")  # type: ignore[arg-type]
    slug_1 = draw.assignments[0].question_slug
    slug_2 = draw.assignments[1].question_slug

    assert (
        resolve_student_question_unit(conn, "2026001", slug_1)  # type: ignore[arg-type]
        == "unit-01"
    )
    with pytest.raises(NoActiveAssignmentsError):
        resolve_student_question_unit(conn, "2026001", "nonexistent-slug")  # type: ignore[arg-type]

    with pytest.raises(StudentNotFoundError):
        get_student_status(conn, "9999999")  # type: ignore[arg-type]

    with pytest.raises(UnitNotFoundError):
        get_student_status(conn, "2026001", unit_code="unit-99")  # type: ignore[arg-type]

    conn.attempts.append({"id": 1, "assignment_id": draw.assignments[0].id})

    statuses = get_student_status(conn, "2026001", unit_code="unit-01")  # type: ignore[arg-type]
    assert len(statuses) == 2
    by_slug = {s.question_slug: s for s in statuses}
    assert by_slug[slug_1].attempts_used == 1
    assert by_slug[slug_1].attempts_remaining == 2
    assert by_slug[slug_1].state == "pending"
    assert by_slug[slug_2].attempts_used == 0
    assert by_slug[slug_2].attempts_remaining == 3

    statuses_all = get_student_status(conn, "2026001")  # type: ignore[arg-type]
    assert len(statuses_all) == 2


@pytest.mark.db
def test_get_student_status_and_resolve_unit_db(daemon_conn: DictConnection) -> None:
    from unicode.services.assignments import (
        get_student_status,
        resolve_student_question_unit,
    )

    _seed_unit_and_student(daemon_conn)
    draw = draw_assignments(daemon_conn, "2026001", "unit-01")
    slug_1 = draw.assignments[0].question_slug
    slug_2 = draw.assignments[1].question_slug

    # Resolve unit from active question slug
    assert resolve_student_question_unit(daemon_conn, "2026001", slug_1) == "unit-01"
    with pytest.raises(NoActiveAssignmentsError):
        resolve_student_question_unit(daemon_conn, "2026001", "nonexistent-slug")

    # Record 1 failed attempt on first assignment
    daemon_conn.execute(
        "INSERT INTO attempts (assignment_id, number, status, tests_total, tests_passed, code) "
        "VALUES (%s, 1, 'failed', 3, 1, 'x=1')",
        (draw.assignments[0].id,),
    )

    statuses = get_student_status(daemon_conn, "2026001", unit_code="unit-01")
    assert len(statuses) == 2
    by_slug = {s.question_slug: s for s in statuses}
    assert by_slug[slug_1].attempts_used == 1
    assert by_slug[slug_1].attempts_remaining == 2
    assert by_slug[slug_1].state == "pending"
    assert by_slug[slug_2].attempts_used == 0
    assert by_slug[slug_2].attempts_remaining == 3


def test_ensure_student_workspace_creates_base_dir_and_preserves_edits(tmp_path: Path) -> None:
    from unicode.services.assignments import ensure_student_workspace

    ws_dir = tmp_path / "workspaces"
    q_dir = tmp_path / "questions"

    # Student with no active assignments still gets /srv/unicode/workspaces/<matricula>
    student_dir = ensure_student_workspace(ws_dir, q_dir, "0020261", [])
    assert student_dir == ws_dir / "0020261"
    assert student_dir.is_dir()

    # With active assignment, provisions README.md and solution.py without overwriting edits
    q_folder = q_dir / "unit-01" / "q01-soma"
    q_folder.mkdir(parents=True)
    (q_folder / "README.md").write_text("# Enunciado", encoding="utf-8")
    (q_folder / "template.py").write_text("def soma(a, b):\n    return 0\n", encoding="utf-8")

    assignment = Assignment(
        id=1,
        student_registration="0020261",
        unit_id=1,
        unit_code="unit-01",
        question_id=1,
        question_slug="q01-soma",
        round=1,
        state="pending",
        points=Decimal("0.0"),
        created_at=datetime.now(UTC),
    )
    ensure_student_workspace(ws_dir, q_dir, "0020261", [assignment])
    sol_file = student_dir / "unit-01" / "q01-soma" / "solution.py"
    assert sol_file.exists()
    sol_file.write_text("def soma(a, b):\n    return a + b\n", encoding="utf-8")

    # Calling ensure_student_workspace again on re-login keeps student's edited solution.py
    ensure_student_workspace(ws_dir, q_dir, "0020261", [assignment])
    assert "return a + b" in sol_file.read_text(encoding="utf-8")


@pytest.mark.db
def test_list_all_active_assignments_db(daemon_conn: DictConnection) -> None:
    from unicode.services.assignments import list_all_active_assignments

    _seed_unit_and_student(daemon_conn)
    assert list_all_active_assignments(daemon_conn, "2026001") == []

    draw = draw_assignments(daemon_conn, "2026001", "unit-01")
    all_active = list_all_active_assignments(daemon_conn, "2026001")
    assert len(all_active) == 2
    assert [a.id for a in all_active] == [a.id for a in draw.assignments]
