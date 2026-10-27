import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from unicode.db import DictConnection
from unicode.models.question import (
    QuestionDefinition,
    QuestionIssue,
    ScanResult,
    SyncReport,
    UnitDefinition,
)

_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
_REQUIRED_QUESTION_FILES = ("README.md", "template.py", "test_eval.py")


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        cleaned = value.strip().replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    raise ValueError(f"tipo de data inesperado: {type(value).__name__}")


def scan_and_validate_questions_dir(root_dir: Path) -> ScanResult:
    issues: list[QuestionIssue] = []
    units: list[UnitDefinition] = []
    questions: list[QuestionDefinition] = []

    if not root_dir.exists() or not root_dir.is_dir():
        issues.append(QuestionIssue(path=root_dir, message="diretório de questões não existe"))
        return ScanResult(issues=issues)

    seen_unit_codes: set[str] = set()
    seen_question_slugs: set[str] = set()

    for unit_dir in sorted(root_dir.iterdir()):
        if not unit_dir.is_dir() or unit_dir.name.startswith("."):
            continue

        unit_yaml = unit_dir / "unit.yaml"
        if not unit_yaml.exists():
            issues.append(
                QuestionIssue(path=unit_dir, message="pasta de unidade sem arquivo unit.yaml")
            )
            continue

        try:
            raw_unit = yaml.safe_load(unit_yaml.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            issues.append(QuestionIssue(path=unit_yaml, message=f"YAML inválido: {exc}"))
            continue

        if not isinstance(raw_unit, dict):
            issues.append(
                QuestionIssue(
                    path=unit_yaml,
                    message="conteúdo do unit.yaml deve ser um mapeamento/dicionário",
                )
            )
            continue

        unit_code = str(raw_unit.get("code", "")).strip()
        unit_title = str(raw_unit.get("title", "")).strip()

        if not unit_code:
            issues.append(QuestionIssue(path=unit_yaml, message="campo 'code' obrigatório ausente"))
            continue
        if unit_code != unit_dir.name:
            issues.append(
                QuestionIssue(
                    path=unit_yaml,
                    message=f"campo 'code' ({unit_code}) difere do nome da pasta ({unit_dir.name})",
                )
            )
            continue
        if not unit_title:
            issues.append(
                QuestionIssue(path=unit_yaml, message="campo 'title' obrigatório ausente")
            )
            continue
        if unit_code in seen_unit_codes:
            issues.append(
                QuestionIssue(path=unit_yaml, message=f"código de unidade repetido: {unit_code}")
            )
            continue

        seen_unit_codes.add(unit_code)

        try:
            opens_at = _parse_iso_datetime(raw_unit.get("opens_at"))
            closes_at = _parse_iso_datetime(raw_unit.get("closes_at"))
            if opens_at and closes_at and closes_at <= opens_at:
                issues.append(
                    QuestionIssue(path=unit_yaml, message="closes_at deve ser posterior a opens_at")
                )
                continue
        except Exception as exc:
            issues.append(QuestionIssue(path=unit_yaml, message=f"data inválida: {exc}"))
            continue

        units.append(
            UnitDefinition(
                code=unit_code,
                title=unit_title,
                opens_at=opens_at,
                closes_at=closes_at,
            )
        )

        for q_dir in sorted(unit_dir.iterdir()):
            if not q_dir.is_dir() or q_dir.name.startswith("."):
                continue

            slug = q_dir.name
            if not _SLUG_RE.fullmatch(slug):
                issues.append(
                    QuestionIssue(
                        path=q_dir,
                        message=(
                            f"slug '{slug}' inválido "
                            "(use apenas letras minúsculas, números e hifens)"
                        ),
                    )
                )
                continue

            if slug in seen_question_slugs:
                issues.append(QuestionIssue(path=q_dir, message=f"slug repetido: {slug}"))
                continue

            q_yaml = q_dir / "question.yaml"
            if not q_yaml.exists():
                issues.append(QuestionIssue(path=q_dir, message="arquivo question.yaml ausente"))
                continue

            try:
                raw_q = yaml.safe_load(q_yaml.read_text(encoding="utf-8")) or {}
            except Exception as exc:
                issues.append(QuestionIssue(path=q_yaml, message=f"YAML inválido: {exc}"))
                continue

            if not isinstance(raw_q, dict):
                issues.append(
                    QuestionIssue(
                        path=q_yaml,
                        message="conteúdo do question.yaml deve ser um mapeamento/dicionário",
                    )
                )
                continue

            q_title = str(raw_q.get("title", "")).strip()
            if not q_title:
                issues.append(
                    QuestionIssue(path=q_yaml, message="campo 'title' obrigatório ausente")
                )
                continue

            active = bool(raw_q.get("active", True))
            raw_timeout = raw_q.get("timeout_seconds", 3)
            try:
                timeout_sec = int(raw_timeout)
            except (ValueError, TypeError):
                issues.append(
                    QuestionIssue(
                        path=q_yaml,
                        message=f"timeout_seconds inválido: {raw_timeout}",
                    )
                )
                continue

            missing_files = [f for f in _REQUIRED_QUESTION_FILES if not (q_dir / f).exists()]
            if missing_files:
                issues.append(
                    QuestionIssue(
                        path=q_dir,
                        message=f"arquivos obrigatórios ausentes: {', '.join(missing_files)}",
                    )
                )
                continue

            seen_question_slugs.add(slug)
            questions.append(
                QuestionDefinition(
                    slug=slug,
                    unit_code=unit_code,
                    title=q_title,
                    active=active,
                    timeout_seconds=timeout_sec,
                    dir_path=q_dir,
                )
            )

    return ScanResult(units=units, questions=questions, issues=issues)


def sync_questions(
    conn: DictConnection,
    scanned: ScanResult,
    *,
    actor: str = "admin",
) -> SyncReport:
    if scanned.has_errors:
        return SyncReport(issues=list(scanned.issues))

    units_created = 0
    units_updated = 0
    questions_created = 0
    questions_updated = 0
    questions_deactivated = 0

    unit_code_to_id: dict[str, int] = {}

    for u in scanned.units:
        with conn.transaction():
            existing = conn.execute(
                "SELECT id, title, opens_at, closes_at FROM units WHERE code = %s FOR UPDATE",
                (u.code,),
            ).fetchone()

            if existing is None:
                row = conn.execute(
                    "INSERT INTO units (code, title, opens_at, closes_at) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    (u.code, u.title, u.opens_at, u.closes_at),
                ).fetchone()
                assert row is not None
                unit_code_to_id[u.code] = int(row["id"])
                units_created += 1
            else:
                unit_code_to_id[u.code] = int(existing["id"])
                if (
                    existing["title"] != u.title
                    or existing["opens_at"] != u.opens_at
                    or existing["closes_at"] != u.closes_at
                ):
                    conn.execute(
                        "UPDATE units SET title = %s, opens_at = %s, closes_at = %s WHERE id = %s",
                        (u.title, u.opens_at, u.closes_at, existing["id"]),
                    )
                    units_updated += 1

    synced_slugs_by_unit: dict[int, set[str]] = {uid: set() for uid in unit_code_to_id.values()}

    for q in scanned.questions:
        unit_id = unit_code_to_id[q.unit_code]
        synced_slugs_by_unit[unit_id].add(q.slug)

        with conn.transaction():
            existing_q = conn.execute(
                "SELECT id, unit_id, title, active FROM questions WHERE slug = %s FOR UPDATE",
                (q.slug,),
            ).fetchone()

            if existing_q is None:
                conn.execute(
                    "INSERT INTO questions (unit_id, slug, title, active) VALUES (%s, %s, %s, %s)",
                    (unit_id, q.slug, q.title, q.active),
                )
                questions_created += 1
            else:
                if (
                    existing_q["unit_id"] != unit_id
                    or existing_q["title"] != q.title
                    or existing_q["active"] != q.active
                ):
                    conn.execute(
                        "UPDATE questions SET unit_id = %s, title = %s, active = %s WHERE id = %s",
                        (unit_id, q.title, q.active, existing_q["id"]),
                    )
                    questions_updated += 1

    for unit_id, active_slugs in synced_slugs_by_unit.items():
        with conn.transaction():
            if active_slugs:
                slug_list = list(active_slugs)
                deactivated_rows = conn.execute(
                    "UPDATE questions SET active = FALSE "
                    "WHERE unit_id = %s AND active = TRUE AND NOT (slug = ANY(%s)) RETURNING id",
                    (unit_id, slug_list),
                ).fetchall()
            else:
                deactivated_rows = conn.execute(
                    "UPDATE questions SET active = FALSE "
                    "WHERE unit_id = %s AND active = TRUE RETURNING id",
                    (unit_id,),
                ).fetchall()
            questions_deactivated += len(deactivated_rows)

    audit_details = {
        "units_created": units_created,
        "units_updated": units_updated,
        "questions_created": questions_created,
        "questions_updated": questions_updated,
        "questions_deactivated": questions_deactivated,
    }
    conn.execute(
        "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
        (actor, "sync_questions", json.dumps(audit_details)),
    )

    return SyncReport(
        units_created=units_created,
        units_updated=units_updated,
        questions_created=questions_created,
        questions_updated=questions_updated,
        questions_deactivated=questions_deactivated,
        issues=list(scanned.issues),
    )
