import React from "react";
import { AssignmentState, AttemptStatus } from "../api/types";

export const StatusBadge: React.FC<{ status: AssignmentState | AttemptStatus }> = ({ status }) => {
  const map: Record<string, { label: string; className: string }> = {
    passed: { label: "Aprovada", className: "bg-emerald-900/60 text-emerald-300 border-emerald-700" },
    pending: { label: "Pendente", className: "bg-amber-900/60 text-amber-300 border-amber-700" },
    exhausted: { label: "Esgotada", className: "bg-rose-900/60 text-rose-300 border-rose-700" },
    replaced: { label: "Substituída", className: "bg-slate-700/60 text-slate-400 border-slate-600" },
    running: { label: "Executando", className: "bg-blue-900/60 text-blue-300 border-blue-700" },
    failed: { label: "Reprovada", className: "bg-rose-900/60 text-rose-300 border-rose-700" },
    error: { label: "Erro", className: "bg-orange-900/60 text-orange-300 border-orange-700" },
  };

  const current = map[status] || { label: status, className: "bg-slate-800 text-slate-300 border-slate-700" };

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${current.className}`}>
      {current.label}
    </span>
  );
};

