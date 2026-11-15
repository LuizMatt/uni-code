import React, { useEffect, useState } from "react";
import toastConfig from "../../config/toastConfig.json";

export type ToastType = keyof typeof toastConfig;

export interface ToastItem {
  id: string;
  type: ToastType;
  message: string;
  title?: string;
  duration?: number;
}

interface ToastCardProps {
  toast: ToastItem;
  onDismiss: (id: string) => void;
}

const ToastCard: React.FC<ToastCardProps> = ({ toast, onDismiss }) => {
  const cfg = toastConfig[toast.type] || toastConfig.info;
  const totalDuration = toast.duration ?? cfg.duration;
  const [paused, setPaused] = useState(false);
  const [remaining, setRemaining] = useState(totalDuration);

  useEffect(() => {
    if (paused) return;
    const interval = 50;
    const timer = window.setInterval(() => {
      setRemaining((prev) => (prev <= interval ? 0 : prev - interval));
    }, interval);

    return () => window.clearInterval(timer);
  }, [paused]);

  useEffect(() => {
    if (remaining <= 0) {
      onDismiss(toast.id);
    }
  }, [remaining, toast.id, onDismiss]);

  const progressPercent =
    totalDuration > 0 ? Math.max(0, Math.min(100, (remaining / totalDuration) * 100)) : 0;

  return (
    <div
      role="alert"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      className={`pointer-events-auto relative overflow-hidden backdrop-blur-md border rounded-xl shadow-2xl p-3.5 transition-all duration-200 ${cfg.containerClass}`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 border ${cfg.iconClass}`}
        >
          <i className={`mdi ${cfg.icon} text-base leading-none`} aria-hidden="true" />
        </div>

        <div className="flex-1 min-w-0 pr-1">
          <div className={`text-xs font-semibold tracking-wide ${cfg.titleClass}`}>
            {toast.title || cfg.defaultTitle}
          </div>
          <div className="text-xs text-slate-300 mt-0.5 leading-relaxed break-words">
            {toast.message}
          </div>
        </div>

        <button
          type="button"
          onClick={() => onDismiss(toast.id)}
          aria-label="Fechar notificação"
          className="text-slate-400 hover:text-white px-1.5 py-0.5 rounded hover:bg-slate-800/80 transition shrink-0"
        >
          <i className="mdi mdi-close text-sm leading-none" aria-hidden="true" />
        </button>
      </div>

      <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-slate-800">
        <div
          className={`h-full transition-all duration-75 ${cfg.progressClass}`}
          style={{ width: `${progressPercent}%` }}
        />
      </div>
    </div>
  );
};

export const ToastContainer: React.FC<{
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}> = ({ toasts, onDismiss }) => {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2.5 max-w-sm w-full pointer-events-none">
      {toasts.map((t) => (
        <ToastCard key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
};
