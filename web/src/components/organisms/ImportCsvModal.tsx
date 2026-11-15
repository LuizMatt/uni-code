import React, { useEffect, useRef, useState } from "react";
import { ImportCsvReport } from "../../api/types";
import { uploadStudentsCsv } from "../../api/client";
import { useToast } from "../../context/ToastContext";
import { Button } from "../atoms/Button";

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
  const [report, setReport] = useState<ImportCsvReport | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  useEffect(() => {
    if (isOpen) {
      setFile(null);
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
        toast.warning("Por favor, selecione um arquivo no formato .csv");
        setFile(null);
        return;
      }
      setFile(selected);
      setReport(null);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      toast.warning("Selecione um arquivo CSV para continuar.");
      return;
    }

    setLoading(true);

    try {
      const res = await uploadStudentsCsv(file);
      setReport(res);
      onSuccess();
      if (res.errors.length > 0 || res.warnings.length > 0) {
        toast.warning("Importação concluída com observações. Confira os detalhes no relatório.");
      } else {
        toast.success("Arquivo CSV importado com sucesso!");
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        toast.error(err.message);
      } else {
        toast.error("Falha ao importar o arquivo CSV.");
      }
    } finally {
      setLoading(false);
    }
  };

  const resetForNewUpload = () => {
    setFile(null);
    setReport(null);
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
          <Button variant="ghost" size="xs" icon="mdi-close" onClick={onClose} disabled={loading}>
            Fechar
          </Button>
        </div>

        <div className="p-5 overflow-y-auto space-y-4 flex-1">
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
                  <span className="flex items-center gap-1.5">
                    <i className="mdi mdi-file-delimited-outline text-emerald-400 text-sm" aria-hidden="true" />
                    {file.name}
                  </span>
                  <span className="text-slate-400">{(file.size / 1024).toFixed(1)} KB</span>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="bg-emerald-950/40 border border-emerald-700/60 rounded-xl p-4">
                <h4 className="text-emerald-400 font-semibold text-sm mb-3 flex items-center gap-2">
                  <i className="mdi mdi-check-circle-outline text-base" aria-hidden="true" />
                  <span>Importação Concluída</span>
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
                    <i className="mdi mdi-alert-circle-outline text-sm" aria-hidden="true" />
                    <span>Erros ({report.errors.length})</span>
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
                    <i className="mdi mdi-alert-outline text-sm" aria-hidden="true" />
                    <span>Avisos ({report.warnings.length})</span>
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
              <Button
                variant="ghost"
                size="sm"
                icon="mdi-refresh"
                onClick={resetForNewUpload}
              >
                Importar outro arquivo
              </Button>
              <Button
                variant="primary"
                size="md"
                icon="mdi-check"
                onClick={onClose}
              >
                Concluir
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="secondary"
                size="md"
                onClick={onClose}
                disabled={loading}
              >
                Cancelar
              </Button>
              <Button
                variant="primary"
                size="md"
                icon="mdi-upload"
                onClick={handleUpload}
                disabled={!file}
                loading={loading}
                loadingText="Enviando e Importando..."
              >
                Enviar e Importar
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
