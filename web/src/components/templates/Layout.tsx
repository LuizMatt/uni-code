import React from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { Button } from "../atoms/Button";

export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { adminEmail, logout } = useAuth();
  const location = useLocation();

  const navLinks = [
    { to: "/", label: "Visão Geral" },
    { to: "/alunos", label: "Alunos" },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-slate-900 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-8">
            <Link to="/" className="text-xl font-bold tracking-tight text-white flex items-center space-x-2">
              <span className="text-emerald-500 font-mono">&gt;</span>
              <span>UniCode</span>
              <span className="text-xs font-normal text-slate-400 bg-slate-800 px-2 py-0.5 rounded">Professor</span>
            </Link>

            <nav className="flex space-x-1">
              {navLinks.map((item) => {
                const active = location.pathname === item.to;
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
                      active ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center space-x-4">
            <span className="text-xs text-slate-400 font-mono hidden sm:inline">{adminEmail}</span>
            <Button
              variant="danger-soft"
              size="sm"
              icon="mdi-logout"
              onClick={logout}
            >
              Sair
            </Button>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6">{children}</main>
    </div>
  );
};
