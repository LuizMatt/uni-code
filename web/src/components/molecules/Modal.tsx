import React, { useEffect } from "react";
import { createPortal } from "react-dom";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  disabled?: boolean;
  maxWidthClass?: string;
  className?: string;
  children: React.ReactNode;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  disabled = false,
  maxWidthClass = "max-w-md",
  className = "",
  children,
}) => {
  useEffect(() => {
    if (!isOpen || disabled) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, disabled, onClose]);

  if (!isOpen) return null;

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!disabled && e.target === e.currentTarget) {
      onClose();
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/30 backdrop-blur-sm p-4"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
    >
      <div
        className={`bg-slate-800 border border-slate-600/70 rounded-xl shadow-[0_20px_60px_-15px_rgba(0,0,0,0.8)] ${maxWidthClass} w-full overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-150 ${className}`.trim()}
      >
        {children}
      </div>
    </div>,
    document.body
  );
};
