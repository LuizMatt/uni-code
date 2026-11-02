import React, { createContext, useContext, useState, useEffect } from "react";
import { getStoredToken, setStoredToken, clearStoredToken } from "../api/client";

interface AuthContextType {
  isAuthenticated: boolean;
  adminEmail: string | null;
  login: (email: string, pass: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(!!getStoredToken());
  const [adminEmail, setAdminEmail] = useState<string | null>(null);

  useEffect(() => {
    const token = getStoredToken();
    if (token) {
      fetch("/api/auth/me", {
        headers: { Authorization: `Basic ${token}` },
      })
        .then((res) => {
          if (res.ok) {
            return res.json();
          }
          throw new Error("Sessão inválida");
        })
        .then((data) => {
          setAdminEmail(data.email);
          setIsAuthenticated(true);
        })
        .catch(() => {
          clearStoredToken();
          setIsAuthenticated(false);
          setAdminEmail(null);
        });
    }
  }, []);

  const login = async (email: string, pass: string) => {
    const raw = `${email}:${pass}`;
    const token = btoa(unescape(encodeURIComponent(raw)));
    const res = await fetch("/api/auth/me", {
      headers: { Authorization: `Basic ${token}` },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Credenciais inválidas.");
    }
    const data = await res.json();
    setStoredToken(token);
    setAdminEmail(data.email);
    setIsAuthenticated(true);
  };

  const logout = () => {
    clearStoredToken();
    setIsAuthenticated(false);
    setAdminEmail(null);
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, adminEmail, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth deve ser usado dentro de um AuthProvider");
  }
  return context;
}

