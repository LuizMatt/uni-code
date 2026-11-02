import React from "react";
import { AttemptDetail } from "../api/types";
import { StatusBadge } from "./StatusBadge";

interface CodeModalProps {
  attempt: AttemptDetail | null;
  onClose: () => void;
}

export const CodeModal: React.FC<CodeModalProps> = ({ attempt, onClose }) => {
  if (!attempt) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="bg-slate-800 border border-slate-700 rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div className="flex items-center space-x-3">
            <h3 className="text-lg font-semibold text-white">
              Tentativa #{attempt.number}
            </h3>
            <StatusBadge status={attempt.status} />
            <span className="text-xs text-slate-400">
              {attempt.tests_passed !== null && attempt.tests_total !== null
                ? `${attempt.tests_passed}/${attempt.tests_total} testes passaram`
                : "Sem testes"}
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white px-2 py-1 rounded text-sm bg-slate-700/50 hover:bg-slate-700"
          >
            ✕ Fechar
          </button>
        </div>

        <div className="p-4 overflow-y-auto space-y-4 flex-1">
          <div>
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
              Código Submetido (`solucao.py`):
            </h4>
            <pre className="bg-slate-950 p-4 rounded-lg text-emerald-400 font-mono text-xs overflow-x-auto border border-slate-800">
              <code>{attempt.code}</code>
            </pre>
          </div>

          {attempt.output && (
            <div>
              <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
                Saída dos Testes:
              </h4>
              <pre className="bg-slate-950 p-3 rounded-lg text-slate-300 font-mono text-xs overflow-x-auto border border-slate-800">
                <code>{attempt.output}</code>
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

