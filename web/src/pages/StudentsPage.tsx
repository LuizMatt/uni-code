import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, deleteClassGroup, deleteStudent } from "../api/client";
import { StudentGradesSummary, StudentsResponse } from "../api/types";
import { StudentModal } from "../components/StudentModal";
import { ImportCsvModal } from "../components/ImportCsvModal";
import { ConfirmDeleteModal } from "../components/ConfirmDeleteModal";

type DeleteTarget =
  | { type: "student"; student: StudentGradesSummary }
  | { type: "class"; classGroup: string }
  | null;

export const StudentsPage: React.FC = () => {
  const [students, setStudents] = useState<StudentGradesSummary[]>([]);
  const [search, setSearch] = useState("");
  const [selectedGroup, setSelectedGroup] = useState<string>("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modals state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingStudent, setEditingStudent] = useState<StudentGradesSummary | null>(null);
  const [isImportOpen, setIsImportOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadStudents = useCallback(async () => {
    try {
      const res = await apiFetch<StudentsResponse>("/api/students");
      setStudents(res.students);
      setError(null);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Erro ao carregar alunos.");
      }
    }
  }, []);

  useEffect(() => {
    loadStudents().finally(() => setLoading(false));
  }, [loadStudents]);

  const handleOpenDelete = (target: DeleteTarget) => {
    setDeleteError(null);
    setDeleteTarget(target);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;

    setDeleteLoading(true);
    setDeleteError(null);

    try {
      if (deleteTarget.type === "student") {
        await deleteStudent(deleteTarget.student.registration);
      } else {
        await deleteClassGroup(deleteTarget.classGroup);
        setSelectedGroup("ALL");
      }
      setDeleteTarget(null);
      await loadStudents();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setDeleteError(err.message);
      } else {
        setDeleteError("Erro ao excluir.");
      }
    } finally {
      setDeleteLoading(false);
    }
  };

  if (loading) {
    return <div className="text-center py-12 text-slate-400 text-sm">Carregando alunos...</div>;
  }

  if (error) {
    return <div className="text-center py-12 text-rose-400 text-sm">Erro: {error}</div>;
  }

  // Extract unique classes
  const classes = Array.from(
    new Set(students.map((s) => s.class_group).filter((c): c is string => !!c))
  ).sort();

  // Extract all unit codes
  const unitCodes = Array.from(
    new Set(students.flatMap((s) => Object.keys(s.grades_by_unit)))
  ).sort();

  const filtered = students.filter((s) => {
    const matchesSearch =
      s.registration.includes(search) ||
      s.email.toLowerCase().includes(search.toLowerCase()) ||
      (s.name && s.name.toLowerCase().includes(search.toLowerCase()));

    const matchesGroup = selectedGroup === "ALL" || s.class_group === selectedGroup;
    return matchesSearch && matchesGroup;
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Alunos e Notas</h1>
          <p className="text-xs text-slate-400 mt-1">Notas por unidade e pontuação total acumulada.</p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <input
            type="text"
            placeholder="Buscar aluno, email ou matrícula..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-emerald-500 w-56"
          />

          <select
            value={selectedGroup}
            onChange={(e) => setSelectedGroup(e.target.value)}
            className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-emerald-500"
          >
            <option value="ALL">Todas as Turmas</option>
            {classes.map((c) => (
              <option key={c} value={c}>
                Turma {c}
              </option>
            ))}
          </select>

          {selectedGroup !== "ALL" && (
            <button
              type="button"
              onClick={() => handleOpenDelete({ type: "class", classGroup: selectedGroup })}
              className="bg-rose-600/80 hover:bg-rose-600 text-white px-3 py-1.5 rounded-lg text-xs transition"
            >
              Apagar Turma {selectedGroup}
            </button>
          )}

          <button
            type="button"
            onClick={() => setIsImportOpen(true)}
            className="bg-slate-700 hover:bg-slate-600 text-slate-200 px-3 py-1.5 rounded-lg text-xs flex items-center gap-1.5 transition"
          >
            <span>Importar CSV</span>
          </button>

          <button
            type="button"
            onClick={() => setIsCreateOpen(true)}
            className="bg-emerald-600 hover:bg-emerald-500 text-white font-medium px-3 py-1.5 rounded-lg text-xs flex items-center gap-1.5 transition"
          >
            <span>+ Novo Aluno</span>
          </button>
        </div>
      </div>

      <div className="bg-slate-800/40 border border-slate-700/60 rounded-xl overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-800/80 text-xs uppercase text-slate-400 font-medium">
            <tr>
              <th className="px-4 py-3">Matrícula</th>
              <th className="px-4 py-3">Nome / Email</th>
              <th className="px-4 py-3 text-center">Turma</th>
              {unitCodes.map((u) => (
                <th key={u} className="px-4 py-3 text-center">
                  {u}
                </th>
              ))}
              <th className="px-4 py-3 text-center font-bold text-white">Total</th>
              <th className="px-4 py-3 text-right">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/40 text-slate-200">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={5 + unitCodes.length} className="px-4 py-8 text-center text-slate-500 text-xs">
                  Nenhum aluno encontrado para os filtros selecionados.
                </td>
              </tr>
            ) : (
              filtered.map((s) => (
                <tr key={s.registration} className="hover:bg-slate-800/30 transition">
                  <td className="px-4 py-3 font-mono font-medium text-emerald-400">
                    <Link to={`/alunos/${s.registration}`} className="hover:underline">
                      {s.registration}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-white">{s.name || "-"}</div>
                    <div className="text-xs text-slate-400 font-mono">{s.email}</div>
                  </td>
                  <td className="px-4 py-3 text-center text-xs">
                    <span className="bg-slate-800 px-2 py-0.5 rounded text-slate-300 font-mono">
                      {s.class_group || "-"}
                    </span>
                  </td>
                  {unitCodes.map((u) => (
                    <td key={u} className="px-4 py-3 text-center font-mono text-xs">
                      {s.grades_by_unit[u] !== undefined ? s.grades_by_unit[u].toFixed(1) : "-"}
                    </td>
                  ))}
                  <td className="px-4 py-3 text-center font-mono font-bold text-emerald-400">
                    {s.total_points.toFixed(1)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end space-x-1.5">
                      <button
                        type="button"
                        onClick={() => setEditingStudent(s)}
                        className="bg-slate-700 hover:bg-slate-600 text-slate-200 px-2.5 py-1 rounded text-xs transition"
                      >
                        Editar
                      </button>
                      <button
                        type="button"
                        onClick={() => handleOpenDelete({ type: "student", student: s })}
                        className="bg-rose-900/40 hover:bg-rose-700 text-rose-300 hover:text-white px-2.5 py-1 rounded text-xs transition"
                      >
                        Excluir
                      </button>
                      <Link
                        to={`/alunos/${s.registration}`}
                        className="text-xs text-slate-300 hover:text-white bg-slate-700 hover:bg-slate-600 px-2.5 py-1 rounded transition"
                      >
                        Histórico
                      </Link>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Modal: Novo Aluno */}
      <StudentModal
        isOpen={isCreateOpen}
        mode="create"
        onClose={() => setIsCreateOpen(false)}
        onSuccess={loadStudents}
      />

      {/* Modal: Editar Aluno */}
      <StudentModal
        isOpen={editingStudent !== null}
        mode="edit"
        student={editingStudent}
        onClose={() => setEditingStudent(null)}
        onSuccess={loadStudents}
      />

      {/* Modal: Importar CSV */}
      <ImportCsvModal
        isOpen={isImportOpen}
        onClose={() => setIsImportOpen(false)}
        onSuccess={loadStudents}
      />

      {/* Modal: Confirmar Exclusão */}
      <ConfirmDeleteModal
        isOpen={deleteTarget !== null}
        title={
          deleteTarget?.type === "student"
            ? `Excluir Aluno ${deleteTarget.student.registration}`
            : deleteTarget?.type === "class"
            ? `Apagar Turma ${deleteTarget.classGroup}`
            : "Confirmar Exclusão"
        }
        message={
          deleteTarget?.type === "student"
            ? `Tem certeza que deseja excluir o aluno "${deleteTarget.student.name || deleteTarget.student.registration}" (${deleteTarget.student.email})?`
            : deleteTarget?.type === "class"
            ? `Tem certeza que deseja apagar a turma "${deleteTarget.classGroup}" e todos os alunos cadastrados nela?`
            : ""
        }
        confirmText={
          deleteTarget?.type === "student"
            ? "Excluir Aluno"
            : deleteTarget?.type === "class"
            ? "Apagar Turma"
            : "Excluir"
        }
        loading={deleteLoading}
        error={deleteError}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
};
