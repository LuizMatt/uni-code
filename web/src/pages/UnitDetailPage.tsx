import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { apiFetch, downloadGradesCsv } from "../api/client";
import { UnitDetailReport } from "../api/types";

export const UnitDetailPage: React.FC = () => {
  const { codigo } = useParams<{ codigo: string }>();
  const [data, setData] = useState<UnitDetailReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!codigo) return;
    apiFetch<UnitDetailReport>(`/api/units/${codigo}`)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [codigo]);

  if (loading) {
    return <div className="text-center py-12 text-slate-400 text-sm">Carregando métricas da unidade...</div>;
  }

  if (error || !data) {
    return <div className="text-center py-12 text-rose-400 text-sm">Erro: {error}</div>;
  }

  const { code, title, questions } = data;

  return (
    <div className="space-y-6">
      <div className="flex items-center space-x-2 text-xs text-slate-400">
        <Link to="/" className="hover:text-white">
          ← Voltar para Visão Geral
        </Link>
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <div className="flex items-center space-x-3">
            <span className="font-mono text-emerald-400 font-bold text-lg">{code}</span>
            <h1 className="text-2xl font-bold text-white tracking-tight">{title}</h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">Estatísticas de sorteio, taxa de acerto e tentativas por questão.</p>
        </div>

        <button
          onClick={() => downloadGradesCsv(code)}
          className="self-start sm:self-auto text-xs text-emerald-300 hover:text-emerald-200 bg-emerald-950/60 hover:bg-emerald-900 border border-emerald-800 px-3 py-2 rounded-lg font-medium transition"
        >
          Exportar Notas da Unidade (.CSV)
        </button>
      </div>

      <div className="bg-slate-800/40 border border-slate-700/60 rounded-xl overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-800/80 text-xs uppercase text-slate-400 font-medium">
            <tr>
              <th className="px-4 py-3">Questão</th>
              <th className="px-4 py-3 text-center">Status</th>
              <th className="px-4 py-3 text-center">Sorteada</th>
              <th className="px-4 py-3 text-center">Aprovados</th>
              <th className="px-4 py-3 text-center">Esgotados</th>
              <th className="px-4 py-3 text-center">Pendentes</th>
              <th className="px-4 py-3 text-center">Média Tentativas</th>
              <th className="px-4 py-3">Taxa de Acerto</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/40 text-slate-200">
            {questions.map((q) => (
              <tr key={q.slug} className="hover:bg-slate-800/30 transition">
                <td className="px-4 py-3">
                  <div className="font-medium text-white">{q.title}</div>
                  <div className="text-xs text-slate-400 font-mono">{q.slug}</div>
                </td>
                <td className="px-4 py-3 text-center">
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${
                      q.active
                        ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    {q.active ? "Ativa" : "Inativa"}
                  </span>
                </td>
                <td className="px-4 py-3 text-center font-mono">{q.assigned_count}</td>
                <td className="px-4 py-3 text-center font-mono text-emerald-400 font-medium">{q.passed_count}</td>
                <td className="px-4 py-3 text-center font-mono text-rose-400">{q.exhausted_count}</td>
                <td className="px-4 py-3 text-center font-mono text-amber-400">{q.pending_count}</td>
                <td className="px-4 py-3 text-center font-mono">{q.avg_attempts.toFixed(2)}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center space-x-2">
                    <div className="w-24 bg-slate-700 rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-emerald-500 h-2 rounded-full"
                        style={{ width: `${Math.min(100, Math.max(0, q.pass_rate))}%` }}
                      ></div>
                    </div>
                    <span className="text-xs font-mono text-slate-300">{q.pass_rate.toFixed(1)}%</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

