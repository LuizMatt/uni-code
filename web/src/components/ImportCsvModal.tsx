import React, { useEffect, useRef, useState } from "react";
import { ImportCsvReport } from "../api/types";
import { uploadStudentsCsv } from "../api/client";

interface ImportCsvModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const ImportCsvModal: React.FC<ImportCsvModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ImportCsvReport | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setFile(null);
      setError(null);
      setReport(null);
      setLoading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) {
      if (!selected.name.toLowerCase().endsWith(".csv")) {
        setError("Por favor, selecione um arquivo no formato .csv");
        setFile(null);
        return;
      }
      setFile(selected);
      setError(null);
      setReport(null);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setError("Selecione um arquivo CSV para continuar.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await uploadStudentsCsv(file);
      setReport(res);
      onSuccess();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Falha ao importar o arquivo CSV.");
      }
    } finally {
      setLoading(false);
    }
  };

  const resetForNewUpload = () => {
    setFile(null);
    setReport(null);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="bg-slate-800 border border-slate-700 rounded-xl shadow-2xl max-w-xl w-full max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div className="flex items-center space-x-2">
            <h3 className="text-lg font-semibold text-white">Importar Alunos via CSV</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white px-2 py-1 rounded text-sm bg-slate-700/50 hover:bg-slate-700 transition"
          >
            ✕ Fechar
          </button>
        </div>

        <div className="p-5 overflow-y-auto space-y-4 flex-1">
          {error && (
            <div className="bg-rose-950/50 border border-rose-800/80 rounded-lg p-3 text-rose-300 text-xs leading-relaxed">
              {error}
            </div>
          )}

          {!report ? (
            <div className="space-y-4">
              <div className="text-xs text-slate-300 space-y-2 bg-slate-900/60 p-3.5 rounded-lg border border-slate-800">
                <p className="font-semibold text-slate-200">Formato esperado do cabeçalho CSV:</p>
                <code className="text-emerald-400 font-mono text-xs block bg-slate-950 px-2.5 py-1.5 rounded border border-slate-800">
                  registration,email,name,class_group
                </code>
                <p className="text-slate-400 text-[11px]">
                  Delimitador vírgula (<code className="text-slate-300">,</code>) ou ponto-e-vírgula (<code className="text-slate-300">;</code>). Matrícula e email são obrigatórios.
                </p>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-2">
                  Arquivo CSV
                </label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,text/csv"
                  onChange={handleFileChange}
                  disabled={loading}
                  className="block w-full text-xs text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-700 file:text-slate-200 hover:file:bg-slate-600 file:cursor-pointer cursor-pointer border border-slate-700 rounded-lg bg-slate-950 p-2 focus:outline-none"
                />
              </div>

              {file && (
                <div className="flex items-center justify-between text-xs bg-slate-900/70 border border-slate-700/80 rounded-lg px-3 py-2 text-slate-300 font-mono">
                  <span>📄 {file.name}</span>
                  <span className="text-slate-400">{(file.size / 1024).toFixed(1)} KB</span>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="bg-emerald-950/40 border border-emerald-700/60 rounded-xl p-4">
                <h4 className="text-emerald-400 font-semibold text-sm mb-3 flex items-center gap-2">
                  <span>✓</span> Importação Concluída
                </h4>
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div className="bg-slate-900/70 rounded-lg p-2.5 border border-emerald-900/50">
                    <div className="text-lg font-bold text-emerald-400">{report.created}</div>
                    <div className="text-[11px] text-slate-400 uppercase tracking-wide">Criados</div>
                  </div>
                  <div className="bg-slate-900/70 rounded-lg p-2.5 border border-emerald-900/50">
                    <div className="text-lg font-bold text-sky-400">{report.updated}</div>
                    <div className="text-[11px] text-slate-400 uppercase tracking-wide">Atualizados</div>
                  </div>
                  <div className="bg-slate-900/70 rounded-lg p-2.5 border border-emerald-900/50">
                    <div className="text-lg font-bold text-slate-300">{report.unchanged}</div>
                    <div className="text-[11px] text-slate-400 uppercase tracking-wide">Inalterados</div>
                  </div>
                </div>
              </div>

              {report.errors.length > 0 && (
                <div className="space-y-1.5">
                  <h5 className="text-xs font-semibold text-rose-400 uppercase tracking-wider flex items-center gap-1.5">
                    <span>⚠</span> Erros ({report.errors.length})
                  </h5>
                  <div className="bg-rose-950/30 border border-rose-900/60 rounded-lg p-3 text-xs text-rose-300 max-h-36 overflow-y-auto space-y-1 font-mono">
                    {report.errors.map((err, idx) => (
                      <div key={idx} className="flex gap-2">
                        <span className="font-semibold text-rose-400 min-w-16">
                          Linha {err.line_number}:
                        </span>
                        <span>{err.message}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {report.warnings.length > 0 && (
                <div className="space-y-1.5">
                  <h5 className="text-xs font-semibold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                    <span>ℹ</span> Avisos ({report.warnings.length})
                  </h5>
                  <div className="bg-amber-950/30 border border-amber-900/60 rounded-lg p-3 text-xs text-amber-300 max-h-36 overflow-y-auto space-y-1 font-mono">
                    {report.warnings.map((warn, idx) => (
                      <div key={idx} className="flex gap-2">
                        <span className="font-semibold text-amber-400 min-w-16">
                          Linha {warn.line_number}:
                        </span>
                        <span>{warn.message}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between p-4 border-t border-slate-700/60 bg-slate-800/80">
          {report ? (
            <>
              <button
                type="button"
                onClick={resetForNewUpload}
                className="text-xs text-slate-300 hover:text-white underline underline-offset-4"
              >
                Importar outro arquivo
              </button>
              <button
                type="button"
                onClick={onClose}
                className="bg-emerald-600 hover:bg-emerald-500 text-white font-medium px-4 py-2 rounded-lg text-sm transition"
              >
                Concluir
              </button>
            </>
          ) : (
            <>
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
                onClick={handleUpload}
                disabled={!file || loading}
                className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium px-4 py-2 rounded-lg text-sm transition flex items-center gap-2"
              >
                {loading ? (
                  <>
                    <span className="inline-block w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Enviando e Importando...</span>
                  </>
                ) : (
                  "Enviar e Importar"
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
