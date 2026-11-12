"""Seed script to populate initial test students, assignments, and submissions in UniCode."""

from unicode.config import get_settings
from unicode.db import close_pool, get_pool
from unicode.services.assignments import draw_assignments_for_unit
from unicode.services.questions import scan_and_validate_questions_dir, sync_questions

STUDENTS = [
    ("202601001", "lucas.silva@aluno.dev", "Lucas Silva", "TURMA-A"),
    ("202601002", "beatriz.mendes@aluno.dev", "Beatriz Mendes", "TURMA-A"),
    ("202601003", "rodrigo.souza@aluno.dev", "Rodrigo Souza", "TURMA-A"),
    ("202601004", "camila.rocha@aluno.dev", "Camila Rocha", "TURMA-B"),
    ("202601099", "marcos.lima@aluno.dev", "Marcos Lima (Trancado)", "TURMA-B"),
]


def run_seed():
    settings = get_settings()
    pool = get_pool()

    with pool.connection() as conn:
        print("[1/4] Sincronizando catálogo de questões...")
        catalog = scan_and_validate_questions_dir(settings.questions_dir)
        sync_questions(conn, catalog)

        print("[2/4] Cadastrando alunos de teste...")
        for reg, email, name, turma in STUDENTS:
            conn.execute(
                """
                INSERT INTO students (registration, email, name, class_group)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (registration) DO UPDATE
                SET email = EXCLUDED.email, name = EXCLUDED.name, class_group = EXCLUDED.class_group
                """,
                (reg, email, name, turma),
            )

        print("[3/4] Sorteando questões (assignments) para alunos de teste...")
        # Aluno 1, 2 e 3 iniciam a unit-01
        a1_draw = draw_assignments_for_unit(conn, "202601001", "unit-01")
        a2_draw = draw_assignments_for_unit(conn, "202601002", "unit-01")
        a3_draw = draw_assignments_for_unit(conn, "202601003", "unit-01")

        print("[4/4] Simulando submissões e tentativas...")
        # Aluno 1: 1 questão aprovada (0.5 ponto, state='passed')
        if a1_draw.assignments:
            first_asg = a1_draw.assignments[0]
            conn.execute(
                """
                INSERT INTO attempts (assignment_id, attempt_number, feedback, passed, stdout, test_summary)
                VALUES (%s, 1, 'passed', TRUE, 'All tests passed.', '{"passed": 3, "failed": 0}')
                ON CONFLICT DO NOTHING
                """,
                (first_asg.id,),
            )
            conn.execute(
                """
                UPDATE assignments
                SET state = 'passed', points = 0.5
                WHERE id = %s
                """,
                (first_asg.id,),
            )

        # Aluno 2: 2 tentativas reprovadas em uma questão (pending, 1 tentativa restante)
        if a2_draw.assignments:
            asg2 = a2_draw.assignments[0]
            conn.execute(
                """
                INSERT INTO attempts (assignment_id, attempt_number, feedback, passed, stdout, test_summary)
                VALUES (%s, 1, 'failed', FALSE, 'AssertionError: 2 != 3', '{"passed": 1, "failed": 1}'),
                       (%s, 2, 'failed', FALSE, 'AssertionError: None != 5', '{"passed": 0, "failed": 2}')
                ON CONFLICT DO NOTHING
                """,
                (asg2.id, asg2.id),
            )

        # Aluno 3: 3 tentativas esgotadas (state='exhausted', 0 pontos)
        if a3_draw.assignments:
            asg3 = a3_draw.assignments[0]
            conn.execute(
                """
                INSERT INTO attempts (assignment_id, attempt_number, feedback, passed, stdout, test_summary)
                VALUES (%s, 1, 'failed', FALSE, 'Test fail', '{"passed": 0, "failed": 2}'),
                       (%s, 2, 'failed', FALSE, 'Test fail', '{"passed": 0, "failed": 2}'),
                       (%s, 3, 'failed', FALSE, 'Test fail', '{"passed": 0, "failed": 2}')
                ON CONFLICT DO NOTHING
                """,
                (asg3.id, asg3.id, asg3.id),
            )
            conn.execute(
                """
                UPDATE assignments
                SET state = 'exhausted', points = 0.0
                WHERE id = %s
                """,
                (asg3.id,),
            )

        conn.commit()
        print("✔ Seed concluído com sucesso!")


if __name__ == "__main__":
    try:
        run_seed()
    finally:
        close_pool()

