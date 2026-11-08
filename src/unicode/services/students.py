import csv
import io
import json
import re
import unicodedata
from collections import defaultdict

from psycopg import errors

from unicode.db import DictConnection
from unicode.models.student import (
    ImportReport,
    ParseResult,
    RowIssue,
    Student,
    StudentRow,
)

_REGISTRATION_RE = re.compile(r"^[0-9]+$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class StudentConflictError(Exception):
    """Raised when creating or updating a student causes a conflict with an existing record."""


class StudentNotFoundError(Exception):
    """Raised when a student registration is not found."""


class CsvFormatError(Exception):
    """Raised when the CSV structure is fundamentally unparseable."""


def _normalize_header_name(name: str) -> str:
    cleaned = name.strip()
    nfkd = unicodedata.normalize("NFKD", cleaned)
    without_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    normalized = without_accents.lower().replace("-", "").replace("_", "").replace(" ", "")
    if "matricula" in normalized:
        return "matricula"
    if "email" in normalized or "mail" in normalized:
        return "email"
    if "nome" in normalized:
        return "nome"
    if "turma" in normalized:
        return "turma"
    return normalized


def parse_students_csv(text: str) -> ParseResult:
    """Parse and validate student CSV text without accessing the database.

    Raises CsvFormatError if the file is empty or headers are invalid.
    """
    stripped = text.strip()
    if not stripped:
        raise CsvFormatError("arquivo vazio")

    # Remove BOM if present
    text = text.removeprefix("\ufeff")

    lines = text.splitlines()
    header_line = ""
    header_idx = -1
    for idx, line in enumerate(lines):
        if line.strip():
            header_line = line
            header_idx = idx
            break

    if header_idx == -1:
        raise CsvFormatError("arquivo vazio")

    # Detect delimiter
    delimiter = ";" if header_line.count(";") > header_line.count(",") else ","

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        raw_rows = list(reader)
    except Exception as e:
        raise CsvFormatError(f"erro ao processar CSV: {e}") from e

    # Find the header row in parsed rows
    header_row = raw_rows[header_idx]
    normalized_headers: list[str] = [_normalize_header_name(h) for h in header_row]

    # Check header duplicates
    seen_headers: set[str] = set()
    for h in normalized_headers:
        if h in seen_headers:
            raise CsvFormatError(f"coluna repetida no cabeçalho: {h}")
        seen_headers.add(h)

    if "matricula" not in seen_headers or "email" not in seen_headers:
        raise CsvFormatError("coluna obrigatória ausente (esperadas: 'email' e 'matricula')")

    reg_col = normalized_headers.index("matricula")
    email_col = normalized_headers.index("email")
    name_col = normalized_headers.index("nome") if "nome" in seen_headers else None
    class_col = normalized_headers.index("turma") if "turma" in seen_headers else None

    expected_cols = len(header_row)
    issues: list[RowIssue] = []

    # Temporary storage for validation and deduplication
    parsed_candidates: list[StudentRow] = []

    for line_num, row in enumerate(raw_rows[header_idx + 1 :], start=header_idx + 2):
        # Skip completely empty lines
        if not row or not any(field.strip() for field in row):
            continue

        if len(row) != expected_cols:
            issues.append(
                RowIssue(
                    line_number=line_num,
                    message=f"esperadas {expected_cols} colunas, encontradas {len(row)}",
                    kind="error",
                )
            )
            continue

        raw_reg = row[reg_col].strip()
        raw_email = row[email_col].strip().lower()
        raw_name = row[name_col].strip() if name_col is not None else ""
        raw_class = row[class_col].strip() if class_col is not None else ""

        errors_list: list[str] = []

        if not raw_reg:
            errors_list.append("matrícula vazia")
        elif not _REGISTRATION_RE.fullmatch(raw_reg):
            errors_list.append("matrícula deve conter apenas dígitos")

        if not raw_email:
            errors_list.append("email vazio")
        elif not _EMAIL_RE.fullmatch(raw_email):
            errors_list.append("email inválido")

        if errors_list:
            issues.append(
                RowIssue(
                    line_number=line_num,
                    message="; ".join(errors_list),
                    kind="error",
                )
            )
            continue

        parsed_candidates.append(
            StudentRow(
                line_number=line_num,
                registration=raw_reg,
                email=raw_email,
                name=raw_name or None,
                class_group=raw_class or None,
            )
        )

    # In-file duplicate checking
    # 1. Exact identical lines -> keep first, warn others
    unique_rows: list[StudentRow] = []
    seen_exact: dict[tuple[str, str, str | None, str | None], int] = {}

    for cand in parsed_candidates:
        key = (cand.registration, cand.email, cand.name, cand.class_group)
        if key in seen_exact:
            issues.append(
                RowIssue(
                    line_number=cand.line_number,
                    message=f"linha idêntica à linha {seen_exact[key]}; considerada uma vez",
                    kind="warning",
                )
            )
        else:
            seen_exact[key] = cand.line_number
            unique_rows.append(cand)

    # 2. Conflicting registrations or emails
    reg_to_lines = defaultdict(list)
    email_to_lines = defaultdict(list)
    for cand in unique_rows:
        reg_to_lines[cand.registration].append(cand.line_number)
        email_to_lines[cand.email].append(cand.line_number)

    conflicting_regs = {r: lines for r, lines in reg_to_lines.items() if len(lines) > 1}
    conflicting_emails = {e: lines for e, lines in email_to_lines.items() if len(lines) > 1}

    valid_rows: list[StudentRow] = []
    for cand in unique_rows:
        is_conflict = False
        if cand.registration in conflicting_regs:
            lines_str = ", ".join(map(str, conflicting_regs[cand.registration]))
            issues.append(
                RowIssue(
                    line_number=cand.line_number,
                    message=f"matrícula {cand.registration} repetida nas linhas {lines_str}",
                    kind="error",
                )
            )
            is_conflict = True
        elif cand.email in conflicting_emails:
            lines_str = ", ".join(map(str, conflicting_emails[cand.email]))
            issues.append(
                RowIssue(
                    line_number=cand.line_number,
                    message=f"email {cand.email} repetido nas linhas {lines_str}",
                    kind="error",
                )
            )
            is_conflict = True

        if not is_conflict:
            valid_rows.append(cand)

    issues.sort(key=lambda x: (x.line_number, 0 if x.kind == "warning" else 1))
    return ParseResult(valid_rows=valid_rows, issues=issues)


def import_students(
    conn: DictConnection,
    parsed: ParseResult,
    *,
    source: str,
    actor: str = "admin",
) -> ImportReport:
    """Import parsed student rows into the database using savepoints.

    Runs within the caller's transaction. Concurrency conflicts on email
    are captured as row errors without aborting other rows.
    """
    created = 0
    updated = 0
    unchanged = 0
    issues: list[RowIssue] = list(parsed.issues)

    for cand in parsed.valid_rows:
        try:
            with conn.transaction():
                existing = conn.execute(
                    "SELECT registration, email, name, class_group FROM students "
                    "WHERE registration = %s FOR UPDATE",
                    (cand.registration,),
                ).fetchone()

                if existing is None:
                    conn.execute(
                        "INSERT INTO students (registration, email, name, class_group) "
                        "VALUES (%s, %s, %s, %s)",
                        (cand.registration, cand.email, cand.name, cand.class_group),
                    )
                    created += 1
                else:
                    new_name = cand.name if cand.name is not None else existing["name"]
                    existing_class = existing["class_group"]
                    new_class = (
                        cand.class_group if cand.class_group is not None else existing_class
                    )
                    new_email = cand.email

                    if (
                        new_email == existing["email"]
                        and new_name == existing["name"]
                        and new_class == existing["class_group"]
                    ):
                        unchanged += 1
                    else:
                        conn.execute(
                            "UPDATE students SET email = %s, name = %s, class_group = %s "
                            "WHERE registration = %s",
                            (new_email, new_name, new_class, cand.registration),
                        )
                        updated += 1
        except errors.UniqueViolation:
            issues.append(
                RowIssue(
                    line_number=cand.line_number,
                    message=f"email {cand.email} já pertence a outra matrícula",
                    kind="error",
                )
            )

    issues.sort(key=lambda x: (x.line_number, 0 if x.kind == "warning" else 1))

    # Audit log
    audit_details = {
        "source": source,
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "rejected": len([i for i in issues if i.kind == "error"]),
    }
    conn.execute(
        "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
        (actor, "import_csv", json.dumps(audit_details)),
    )

    return ImportReport(
        created=created,
        updated=updated,
        unchanged=unchanged,
        issues=issues,
    )


def list_students(
    conn: DictConnection,
    *,
    class_group: str | None = None,
) -> list[Student]:
    """List students ordered by registration ASC, optionally filtered by class_group."""
    if class_group is not None:
        rows = conn.execute(
            "SELECT registration, email, name, class_group, created_at "
            "FROM students WHERE class_group = %s ORDER BY registration ASC",
            (class_group,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT registration, email, name, class_group, created_at "
            "FROM students ORDER BY registration ASC"
        ).fetchall()

    return [
        Student(
            registration=row["registration"],
            email=row["email"],
            name=row["name"],
            class_group=row["class_group"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def create_student(
    conn: DictConnection,
    registration: str,
    email: str,
    name: str | None = None,
    class_group: str | None = None,
    *,
    actor: str = "admin",
) -> Student:
    """Create a new student with transaction and audit logging.

    Raises:
        ValueError: If registration is empty or email format is invalid.
        StudentConflictError: If registration or email already exists.
    """
    reg = registration.strip()
    em = email.strip().lower()

    if not reg:
        raise ValueError("matrícula não pode ser vazia")
    if not _EMAIL_RE.fullmatch(em):
        raise ValueError("email inválido")

    clean_name = name.strip() if name and name.strip() else None
    clean_class = class_group.strip() if class_group and class_group.strip() else None

    with conn.transaction():
        existing_reg = conn.execute(
            "SELECT registration FROM students WHERE registration = %s",
            (reg,),
        ).fetchone()
        if existing_reg is not None:
            raise StudentConflictError(f"matrícula '{reg}' já cadastrada")

        existing_email = conn.execute(
            "SELECT registration FROM students WHERE email = %s",
            (em,),
        ).fetchone()
        if existing_email is not None:
            raise StudentConflictError(f"email '{em}' já cadastrado")

        try:
            row = conn.execute(
                "INSERT INTO students (registration, email, name, class_group) "
                "VALUES (%s, %s, %s, %s) "
                "RETURNING registration, email, name, class_group, created_at",
                (reg, em, clean_name, clean_class),
            ).fetchone()
        except errors.UniqueViolation as exc:
            raise StudentConflictError(f"conflito ao cadastrar aluno: {exc}") from exc

        assert row is not None

        audit_details = {
            "registration": reg,
            "email": em,
            "name": clean_name,
            "class_group": clean_class,
        }
        conn.execute(
            "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
            (actor, "create_student", json.dumps(audit_details)),
        )

        return Student(
            registration=row["registration"],
            email=row["email"],
            name=row["name"],
            class_group=row["class_group"],
            created_at=row["created_at"],
        )


def update_student(
    conn: DictConnection,
    registration: str,
    email: str,
    name: str | None = None,
    class_group: str | None = None,
    *,
    actor: str = "admin",
) -> Student:
    """Update an existing student with conflict check and audit logging.

    Raises:
        ValueError: If registration is empty or email format is invalid.
        StudentNotFoundError: If registration is not found.
        StudentConflictError: If email is already in use by another student.
    """
    reg = registration.strip()
    em = email.strip().lower()

    if not reg:
        raise ValueError("matrícula não pode ser vazia")
    if not _EMAIL_RE.fullmatch(em):
        raise ValueError("email inválido")

    clean_name = name.strip() if name and name.strip() else None
    clean_class = class_group.strip() if class_group and class_group.strip() else None

    with conn.transaction():
        existing = conn.execute(
            "SELECT registration, email, name, class_group, created_at FROM students "
            "WHERE registration = %s FOR UPDATE",
            (reg,),
        ).fetchone()
        if existing is None:
            raise StudentNotFoundError(f"aluno '{reg}' não encontrado")

        conflict = conn.execute(
            "SELECT registration FROM students WHERE email = %s AND registration <> %s",
            (em, reg),
        ).fetchone()
        if conflict is not None:
            raise StudentConflictError(
                f"email '{em}' já pertence a outro aluno ({conflict['registration']})"
            )

        try:
            row = conn.execute(
                "UPDATE students SET email = %s, name = %s, class_group = %s "
                "WHERE registration = %s "
                "RETURNING registration, email, name, class_group, created_at",
                (em, clean_name, clean_class, reg),
            ).fetchone()
        except errors.UniqueViolation as exc:
            raise StudentConflictError(f"conflito ao atualizar aluno: {exc}") from exc

        assert row is not None

        audit_details = {
            "registration": reg,
            "email": em,
            "name": clean_name,
            "class_group": clean_class,
            "previous": {
                "email": existing["email"],
                "name": existing["name"],
                "class_group": existing["class_group"],
            },
        }
        conn.execute(
            "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
            (actor, "update_student", json.dumps(audit_details)),
        )

        return Student(
            registration=row["registration"],
            email=row["email"],
            name=row["name"],
            class_group=row["class_group"],
            created_at=row["created_at"],
        )


def delete_student(
    conn: DictConnection,
    registration: str,
    *,
    actor: str = "admin",
) -> bool:
    """Delete a student and cascade to attempts, assignments, and sessions.

    Raises:
        StudentNotFoundError: If registration is not found.
    """
    reg = registration.strip()
    if not reg:
        raise StudentNotFoundError("matrícula não pode ser vazia")

    with conn.transaction():
        existing = conn.execute(
            "SELECT registration, email, name, class_group FROM students "
            "WHERE registration = %s FOR UPDATE",
            (reg,),
        ).fetchone()
        if existing is None:
            raise StudentNotFoundError(f"aluno '{reg}' não encontrado")

        conn.execute(
            "DELETE FROM attempts WHERE assignment_id IN ("
            "SELECT id FROM assignments WHERE student_registration = %s"
            ")",
            (reg,),
        )
        conn.execute(
            "DELETE FROM assignments WHERE student_registration = %s",
            (reg,),
        )
        conn.execute(
            "DELETE FROM sessions WHERE student_registration = %s",
            (reg,),
        )
        conn.execute(
            "DELETE FROM students WHERE registration = %s",
            (reg,),
        )

        audit_details = {
            "registration": reg,
            "email": existing["email"],
            "name": existing["name"],
            "class_group": existing["class_group"],
        }
        conn.execute(
            "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
            (actor, "delete_student", json.dumps(audit_details)),
        )

        return True


def delete_class_group(
    conn: DictConnection,
    class_group: str,
    *,
    actor: str = "admin",
) -> int:
    """Delete all students in a class group with cascading delete and audit logging.

    Returns the count of deleted students (0 if none found).
    """
    target_class = class_group.strip()
    with conn.transaction():
        rows = conn.execute(
            "SELECT registration FROM students WHERE class_group = %s FOR UPDATE",
            (target_class,),
        ).fetchall()
        if not rows:
            return 0

        regs = [r["registration"] for r in rows]

        conn.execute(
            "DELETE FROM attempts WHERE assignment_id IN ("
            "SELECT id FROM assignments WHERE student_registration = ANY(%s)"
            ")",
            (regs,),
        )
        conn.execute(
            "DELETE FROM assignments WHERE student_registration = ANY(%s)",
            (regs,),
        )
        conn.execute(
            "DELETE FROM sessions WHERE student_registration = ANY(%s)",
            (regs,),
        )
        conn.execute(
            "DELETE FROM students WHERE registration = ANY(%s)",
            (regs,),
        )

        audit_details = {
            "class_group": target_class,
            "count": len(regs),
            "registrations": regs,
        }
        conn.execute(
            "INSERT INTO audit_log (actor, action, details) VALUES (%s, %s, %s)",
            (actor, "delete_class_group", json.dumps(audit_details)),
        )

        return len(regs)


def import_students_from_csv_bytes(
    conn: DictConnection,
    content: bytes,
    filename: str,
    *,
    actor: str = "admin",
) -> ImportReport:
    """Decode CSV bytes as utf-8-sig, parse and import students into database."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvFormatError(f"falha ao decodificar arquivo CSV: {exc}") from exc

    parsed = parse_students_csv(text)
    return import_students(conn, parsed, source=filename, actor=actor)
