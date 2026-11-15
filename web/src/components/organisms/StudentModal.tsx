import React, { useEffect, useState } from "react";
import { StudentGradesSummary } from "../../api/types";
import { createStudent, updateStudent } from "../../api/client";
import { useToast } from "../../context/ToastContext";
import { Button } from "../atoms/Button";

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
  const toast = useToast();

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
    }
  }, [isOpen, mode, student]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (mode === "create" && !registration.trim()) {
      toast.error("A matrícula é obrigatória.");
      return;
    }

    if (!email.trim()) {
      toast.error("O email é obrigatório.");
      return;
    }

    if (mode !== "create" && !student) return;
    setLoading(true);

    try {
      if (mode === "create") {
        await createStudent({
          registration: registration.trim(),
          email: email.trim(),
          name: name.trim() || null,
          class_group: classGroup.trim() || null,
        });
        toast.success("Aluno criado com sucesso!");
      } else if (student) {
        await updateStudent(student.registration, {
          email: email.trim(),
          name: name.trim() || null,
          class_group: classGroup.trim() || null,
        });
        toast.success("Dados do aluno atualizados com sucesso!");
      }
      onSuccess();
      onClose();
    } catch (err: unknown) {
      if (err instanceof Error) {
        toast.error(err.message);
      } else {
        toast.error("Erro ao salvar aluno.");
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
          <Button variant="ghost" size="xs" icon="mdi-close" onClick={onClose} disabled={loading}>
            Fechar
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
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
            <Button
              variant="secondary"
              size="md"
              onClick={onClose}
              disabled={loading}
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="md"
              icon="mdi-check"
              loading={loading}
              loadingText="Salvando..."
            >
              {mode === "create" ? "Criar Aluno" : "Salvar Aluno"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
