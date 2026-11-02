import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { apiFetch } from "../api/client";
import { StudentDetailReport, AttemptDetail } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { CodeModal } from "../components/CodeModal";

export const StudentDetailPage: React.FC = () => {
  const { matricula } = useParams<{ matricula: string }>();
  const [data, setData] = useState<StudentDetailReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedAttempt, setSelectedAttempt] = useState<AttemptDetail | null>(null);

  useEffect(() => {
    if (!matricula) return;
    apiFetch<StudentDetailReport>(`/api/students/${matricula}`)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [matricula]);

  if (loading) {
    return <div className="text-center py-12 text-slate-400 text-sm">Carregando histórico do aluno...</div>;
  }

  if (error || !data) {
    return <div className="text-center py-12 text-rose-400 text-sm">Erro: {error}</div>;
  }

  const { student, grades_by_unit, total_points, assignments } = data;

  return (
    <div className="space-y-8">
      <div className="flex items-center space-x-2 text-xs text-slate-400">
        <Link to="/alunos" className="hover:text-white">
          ← Voltar para lista de alunos
        </Link>
      </div>

      <div className="bg-slate-800/40 border border-slate-700/60 rounded-xl p-6 flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-bold text-white tracking-tight">{student.name || "Aluno sem nome"}</h1>
            <span className="font-mono text-xs bg-slate-800 px-2.5 py-1 rounded text-emerald-400 border border-slate-700">
              {student.registration}
            </span>
          </div>
          <div className="text-sm text-slate-400 mt-1 flex items-center space-x-4">
            <span>{student.email}</span>
            {student.class_group && <span>• Turma {student.class_group}</span>}
          </div>
        </div>

        <div className="flex items-center space-x-6 border-t md:border-t-0 md:border-l border-slate-700 pt-4 md:pt-0 md:pl-6">
          <div>
            <div className="text-xs text-slate-400 font-medium">Nota Total</div>
            <div className="text-3xl font-bold text-emerald-400 font-mono mt-0.5">{total_points.toFixed(1)}</div>
          </div>
          <div className="text-xs space-y-1">
            {Object.entries(grades_by_unit).map(([u, pts]) => (
              <div key={u} className="flex justify-between space-x-3 text-slate-300">
                <span className="text-slate-400">{u}:</span>
                <span className="font-mono font-medium">{pts.toFixed(1)} pts</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-white">Sorteios e Tentativas de Submissão</h2>

        {assignments.length === 0 ? (
          <div className="bg-slate-800/20 border border-slate-800 rounded-xl p-8 text-center text-slate-500 text-xs">
            Nenhum sorteio registrado para este aluno até o momento.
          </div>
        ) : (
          <div className="space-y-4">
            {assignments.map((a) => (
              <div key={a.id} className="bg-slate-800/40 border border-slate-700/60 rounded-xl p-5 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-700/60 pb-3">
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-mono text-slate-400 bg-slate-900 px-2 py-0.5 rounded">
                        {a.unit_code}
                      </span>
                      <h3 className="font-medium text-white">{a.question_title}</h3>
                      <span className="text-xs text-slate-500 font-mono">({a.question_slug})</span>
                      {a.round > 1 && (
                        <span className="text-xs bg-indigo-950 text-indigo-300 border border-indigo-800 px-2 py-0.5 rounded">
                          Rodada {a.round}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center space-x-3">
                    <StatusBadge status={a.state} />
                    <span className="text-sm font-mono font-bold text-emerald-400">{a.points.toFixed(1)} pts</span>
                  </div>
                </div>

                <div>
                  <h4 className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
                    Tentativas ({a.attempts.length}/3)
                  </h4>
                  {a.attempts.length === 0 ? (
                    <div className="text-xs text-slate-500 italic">Nenhuma tentativa submetida nesta questão.</div>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      {a.attempts.map((att) => (
                        <div
                          key={att.id}
                          className="bg-slate-900/60 border border-slate-800 rounded-lg p-3 space-y-2"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-white">Tentativa #{att.number}</span>
                            <StatusBadge status={att.status} />
                          </div>

                          <div className="text-xs text-slate-400">
                            {att.tests_passed !== null && att.tests_total !== null ? (
                              <span>
                                {att.tests_passed}/{att.tests_total} testes passaram
                              </span>
                            ) : (
                              <span>Execução finalizada</span>
                            )}
                          </div>

                          <button
                            onClick={() => setSelectedAttempt(att)}
                            className="w-full text-xs text-center py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded transition"
                          >
                            Inspecionar Código
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <CodeModal attempt={selectedAttempt} onClose={() => setSelectedAttempt(null)} />
    </div>
  );
};

