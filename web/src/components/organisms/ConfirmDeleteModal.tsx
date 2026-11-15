import React from "react";
import { Button } from "../atoms/Button";

interface ConfirmDeleteModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText?: string;
  loading?: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export const ConfirmDeleteModal: React.FC<ConfirmDeleteModalProps> = ({
  isOpen,
  title,
  message,
  confirmText = "Excluir",
  loading = false,
  onClose,
  onConfirm,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="bg-slate-800 border border-slate-700 rounded-xl shadow-2xl max-w-md w-full overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div className="flex items-center space-x-2.5">
            <i className="mdi mdi-alert-outline text-rose-500 text-lg leading-none" aria-hidden="true" />
            <h3 className="text-lg font-semibold text-white">{title}</h3>
          </div>
          <Button
            variant="ghost"
            size="xs"
            icon="mdi-close"
            onClick={onClose}
            disabled={loading}
          >
            Fechar
          </Button>
        </div>

        <div className="p-5 space-y-4">
          <p className="text-sm text-slate-300 leading-relaxed">{message}</p>

          <div className="bg-rose-950/40 border border-rose-800/80 rounded-lg p-3.5 text-xs text-rose-300 leading-relaxed flex items-start space-x-2.5">
            <i className="mdi mdi-alert-circle-outline text-rose-400 text-base leading-none mt-0.5" aria-hidden="true" />
            <span>
              <strong>Atenção:</strong> Esta ação é irreversível. Todas as notas, submissões e tentativas associadas serão permanentemente removidas do banco de dados.
            </span>
          </div>
        </div>

        <div className="flex items-center justify-end space-x-3 p-4 border-t border-slate-700/60 bg-slate-800/80">
          <Button
            variant="secondary"
            size="md"
            onClick={onClose}
            disabled={loading}
          >
            Cancelar
          </Button>
          <Button
            variant="danger"
            size="md"
            icon="mdi-delete-outline"
            loading={loading}
            loadingText="Excluindo..."
            onClick={onConfirm}
          >
            {confirmText}
          </Button>
        </div>
      </div>
    </div>
  );
};
