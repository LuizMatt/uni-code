import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import { ToastContainer, ToastItem, ToastType } from "../components/molecules/Toast";

export interface ToastOptions {
  title?: string;
  duration?: number;
}

interface ToastContextValue {
  showToast: (type: ToastType, message: string, options?: ToastOptions) => void;
  success: (message: string, options?: ToastOptions) => void;
  error: (message: string, options?: ToastOptions) => void;
  warning: (message: string, options?: ToastOptions) => void;
  info: (message: string, options?: ToastOptions) => void;
  dismissToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const MAX_TOASTS = 5;

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const showToast = useCallback((type: ToastType, message: string, options?: ToastOptions) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setToasts((prev) => {
      const next = [...prev, { id, type, message, title: options?.title, duration: options?.duration }];
      return next.length > MAX_TOASTS ? next.slice(next.length - MAX_TOASTS) : next;
    });
  }, []);

  const success = useCallback(
    (message: string, options?: ToastOptions) => showToast("success", message, options),
    [showToast]
  );
  const error = useCallback(
    (message: string, options?: ToastOptions) => showToast("error", message, options),
    [showToast]
  );
  const warning = useCallback(
    (message: string, options?: ToastOptions) => showToast("warning", message, options),
    [showToast]
  );
  const info = useCallback(
    (message: string, options?: ToastOptions) => showToast("info", message, options),
    [showToast]
  );

  const value = useMemo(
    () => ({ showToast, success, error, warning, info, dismissToast }),
    [showToast, success, error, warning, info, dismissToast]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </ToastContext.Provider>
  );
};

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast deve ser usado dentro de um ToastProvider");
  }
  return ctx;
}
