"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
} from "react";

interface AuthContextValue {
  token: string | null;
  email: string | null;
  isAuthenticated: boolean;
  login: (token: string, email: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(
  undefined
);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  // Ensure no hydration mismatch
  useEffect(() => {
    const storedToken = window.localStorage.getItem("token");
    const storedEmail = window.localStorage.getItem("email");

    if (storedToken) setToken(storedToken);
    if (storedEmail) setEmail(storedEmail);

    setHydrated(true);
  }, []);

  const login = (newToken: string, userEmail: string) => {
    setToken(newToken);
    setEmail(userEmail);

    window.localStorage.setItem("token", newToken);
    window.localStorage.setItem("email", userEmail);
  };

  const logout = () => {
    setToken(null);
    setEmail(null);

    window.localStorage.removeItem("token");
    window.localStorage.removeItem("email");
  };

  // Prevent React hydration mismatch by not rendering until client loads
  if (!hydrated) return null;

  return (
    <AuthContext.Provider
      value={{
        token,
        email,
        isAuthenticated: !!token,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
