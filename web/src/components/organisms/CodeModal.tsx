import React from "react";
import { AttemptDetail } from "../../api/types";
import { StatusBadge } from "../atoms/StatusBadge";
import { Button } from "../atoms/Button";
import { Modal } from "../molecules/Modal";

interface CodeModalProps {
  attempt: AttemptDetail | null;
  onClose: () => void;
}

export const CodeModal: React.FC<CodeModalProps> = ({ attempt, onClose }) => {
  return (
    <Modal
      isOpen={Boolean(attempt)}
      onClose={onClose}
      maxWidthClass="max-w-4xl"
      className="max-h-[90vh]"
    >
      {attempt && (
        <>
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
          <Button variant="ghost" size="xs" icon="mdi-close" onClick={onClose}>
            Fechar
          </Button>
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
        </>
      )}
    </Modal>
  );
};
