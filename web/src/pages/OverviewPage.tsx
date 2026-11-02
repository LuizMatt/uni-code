import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, downloadGradesCsv } from "../api/client";
import { OverviewResponse } from "../api/types";

export const OverviewPage: React.FC = () => {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<OverviewResponse>("/api/overview")
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="text-center py-12 text-slate-400 text-sm">Carregando métricas...</div>;
  }

  if (error || !data) {
    return <div className="text-center py-12 text-rose-400 text-sm">Erro ao carregar dados: {error}</div>;
  }

  const { stats, units } = data;

  const statCards = [
    { label: "Total de Alunos", value: stats.total_students, color: "text-blue-400" },
    { label: "Submissões Hoje", value: stats.submissions_today, color: "text-emerald-400" },
    { label: "Questões Ativas", value: stats.active_questions, color: "text-indigo-400" },
    { label: "Taxa de Aprovação", value: `${stats.approval_rate}%`, color: "text-amber-400" },
  ];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Visão Geral</h1>
        <p className="text-xs text-slate-400 mt-1">Status e métricas do sistema de submissões UniCode.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {statCards.map((card) => (
          <div key={card.label} className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-4">
            <span className="text-xs font-medium text-slate-400">{card.label}</span>
            <div className={`text-2xl font-bold mt-1 ${card.color}`}>{card.value}</div>
          </div>
        ))}
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Unidades Cadastradas</h2>
        </div>

        <div className="bg-slate-800/40 border border-slate-700/60 rounded-xl overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-800/80 text-xs uppercase text-slate-400 font-medium">
              <tr>
                <th className="px-4 py-3">Código</th>
                <th className="px-4 py-3">Título</th>
                <th className="px-4 py-3 text-center">Questões Ativas</th>
                <th className="px-4 py-3 text-center">Alunos que Iniciaram</th>
                <th className="px-4 py-3 text-center">Média de Pontos</th>
                <th className="px-4 py-3 text-right">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/40 text-slate-200">
              {units.map((u) => (
                <tr key={u.code} className="hover:bg-slate-800/30 transition">
                  <td className="px-4 py-3 font-mono text-emerald-400 font-medium">
                    <Link to={`/unidades/${u.code}`} className="hover:underline">
                      {u.code}
                    </Link>
                  </td>
                  <td className="px-4 py-3">{u.title}</td>
                  <td className="px-4 py-3 text-center">{u.active_questions}</td>
                  <td className="px-4 py-3 text-center">{u.students_started}</td>
                  <td className="px-4 py-3 text-center font-mono">{u.average_points}</td>
                  <td className="px-4 py-3 text-right space-x-2">
                    <Link
                      to={`/unidades/${u.code}`}
                      className="text-xs text-slate-300 hover:text-white bg-slate-700 hover:bg-slate-600 px-2.5 py-1 rounded"
                    >
                      Detalhes
                    </Link>
                    <button
                      onClick={() => downloadGradesCsv(u.code)}
                      className="text-xs text-emerald-300 hover:text-emerald-200 bg-emerald-950/60 hover:bg-emerald-900 border border-emerald-800 px-2.5 py-1 rounded transition"
                    >
                      Exportar CSV
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

