import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api/client";
import { StudentGradesSummary, StudentsResponse } from "../api/types";

export const StudentsPage: React.FC = () => {
  const [students, setStudents] = useState<StudentGradesSummary[]>([]);
  const [search, setSearch] = useState("");
  const [selectedGroup, setSelectedGroup] = useState<string>("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<StudentsResponse>("/api/students")
      .then((res) => setStudents(res.students))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

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
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Alunos e Notas</h1>
          <p className="text-xs text-slate-400 mt-1">Notas por unidade e pontuação total acumulada.</p>
        </div>

        <div className="flex items-center space-x-3">
          <input
            type="text"
            placeholder="Buscar aluno, email ou matrícula..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-emerald-500 w-64"
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
              <th className="px-4 py-3 text-right">Ação</th>
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
                    <Link
                      to={`/alunos/${s.registration}`}
                      className="text-xs text-slate-300 hover:text-white bg-slate-700 hover:bg-slate-600 px-2.5 py-1 rounded transition"
                    >
                      Histórico
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

