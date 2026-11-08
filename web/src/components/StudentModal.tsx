import React, { useEffect, useState } from "react";
import { StudentGradesSummary } from "../api/types";
import { createStudent, updateStudent } from "../api/client";

interface StudentModalProps {
  isOpen: boolean;
  mode: "create" | "edit";
  student?: StudentGradesSummary | null;
  onClose: () => void;
  onSuccess: () => void;
}

export const StudentModal: React.FC<StudentModalProps> = ({
  isOpen,
  mode,
  student,
  onClose,
  onSuccess,
}) => {
  const [registration, setRegistration] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [classGroup, setClassGroup] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      if (mode === "edit" && student) {
        setRegistration(student.registration);
        setName(student.name ?? "");
        setEmail(student.email);
        setClassGroup(student.class_group ?? "");
      } else {
        setRegistration("");
        setName("");
        setEmail("");
        setClassGroup("");
      }
      setError(null);
    }
  }, [isOpen, mode, student]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (mode === "create" && !registration.trim()) {
      setError("A matrícula é obrigatória.");
      return;
    }

    if (!email.trim()) {
      setError("O email é obrigatório.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      if (mode === "create") {
        await createStudent({
          registration: registration.trim(),
          email: email.trim(),
          name: name.trim() || null,
          class_group: classGroup.trim() || null,
        });
      } else {
        if (!student) return;
        await updateStudent(student.registration, {
          email: email.trim(),
          name: name.trim() || null,
          class_group: classGroup.trim() || null,
        });
      }
      onSuccess();
      onClose();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Erro ao salvar aluno.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="bg-slate-800 border border-slate-700 rounded-xl shadow-2xl max-w-md w-full overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <h3 className="text-lg font-semibold text-white">
            {mode === "create" ? "Novo Aluno" : "Editar Aluno"}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white px-2 py-1 rounded text-sm bg-slate-700/50 hover:bg-slate-700 transition"
          >
            ✕ Fechar
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="bg-rose-950/50 border border-rose-800/80 rounded-lg p-3 text-rose-300 text-xs leading-relaxed">
              {error}
            </div>
          )}

          <div>
            <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-1">
              Matrícula <span className="text-rose-400">*</span>
            </label>
            <input
              type="text"
              required
              disabled={mode === "edit" || loading}
              value={registration}
              onChange={(e) => setRegistration(e.target.value)}
              placeholder="ex: 202401001"
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500 w-full disabled:opacity-50 disabled:bg-slate-900 disabled:cursor-not-allowed font-mono"
            />
            {mode === "edit" && (
              <p className="text-[11px] text-slate-400 mt-1">
                A matrícula é a chave de identificação do aluno e não pode ser alterada.
              </p>
            )}
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-1">
              Nome Completo
            </label>
            <input
              type="text"
              disabled={loading}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="ex: Maria da Silva"
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500 w-full"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-1">
              Email <span className="text-rose-400">*</span>
            </label>
            <input
              type="email"
              required
              disabled={loading}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="ex: maria@faculdade.edu.br"
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500 w-full font-mono text-xs sm:text-sm"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-1">
              Turma
            </label>
            <input
              type="text"
              disabled={loading}
              value={classGroup}
              onChange={(e) => setClassGroup(e.target.value)}
              placeholder="ex: T01"
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500 w-full font-mono"
            />
          </div>

          <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-700/60">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-200 px-4 py-2 rounded-lg text-sm font-medium transition"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={loading}
              className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium px-4 py-2 rounded-lg text-sm transition flex items-center gap-2"
            >
              {loading ? (
                <>
                  <span className="inline-block w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Salvando...</span>
                </>
              ) : mode === "create" ? (
                "Criar Aluno"
              ) : (
                "Salvar Aluno"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
