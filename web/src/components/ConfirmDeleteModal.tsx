import React from "react";

interface ConfirmDeleteModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText?: string;
  loading?: boolean;
  error?: string | null;
  onClose: () => void;
  onConfirm: () => void;
}

export const ConfirmDeleteModal: React.FC<ConfirmDeleteModalProps> = ({
  isOpen,
  title,
  message,
  confirmText = "Excluir",
  loading = false,
  error,
  onClose,
  onConfirm,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="bg-slate-800 border border-slate-700 rounded-xl shadow-2xl max-w-md w-full overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div className="flex items-center space-x-2.5">
            <span className="text-rose-500 text-lg">⚠</span>
            <h3 className="text-lg font-semibold text-white">{title}</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="text-slate-400 hover:text-white px-2 py-1 rounded text-sm bg-slate-700/50 hover:bg-slate-700 transition"
          >
            ✕ Fechar
          </button>
        </div>

        <div className="p-5 space-y-4">
          {error && (
            <div className="bg-rose-950/60 border border-rose-800 rounded-lg p-3 text-rose-300 text-xs leading-relaxed">
              {error}
            </div>
          )}

          <p className="text-sm text-slate-300 leading-relaxed">{message}</p>

          <div className="bg-rose-950/40 border border-rose-800/80 rounded-lg p-3.5 text-xs text-rose-300 leading-relaxed flex items-start space-x-2.5">
            <span className="text-rose-400 font-bold text-sm leading-none">!</span>
            <span>
              <strong>Atenção:</strong> Esta ação é irreversível. Todas as notas, submissões e tentativas associadas serão permanentemente removidas do banco de dados.
            </span>
          </div>
        </div>

        <div className="flex items-center justify-end space-x-3 p-4 border-t border-slate-700/60 bg-slate-800/80">
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-200 px-4 py-2 rounded-lg text-sm font-medium transition"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className="bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-medium px-4 py-2 rounded-lg text-sm transition flex items-center gap-2"
          >
            {loading ? (
              <>
                <span className="inline-block w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Excluindo...</span>
              </>
            ) : (
              confirmText
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
