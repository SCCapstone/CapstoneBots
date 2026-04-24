"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";

const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL;

// Refresh the token 5 minutes before it expires.
// Default token lifetime is 60 min, so refresh at ~55 min.
const REFRESH_MARGIN_MS = 5 * 60 * 1000;

/** Decode the `exp` claim from a JWT (seconds since epoch). */
function getTokenExp(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}

interface AuthContextType {
  token: string | null;
  hydrated: boolean;
  isAuthenticated: boolean;
  login: (token: string, email?: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  token: null,
  hydrated: false,
  isAuthenticated: false,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Ref lets the scheduled callback call the latest scheduleRefresh without creating a cycle
  const scheduleRefreshRef = useRef<(t: string) => void>(() => {});

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimer.current) {
      clearTimeout(refreshTimer.current);
      refreshTimer.current = null;
    }
  }, []);

  const logout = useCallback(() => {
    clearRefreshTimer();
    localStorage.removeItem("auth_token");
    setToken(null);
  }, [clearRefreshTimer]);

  const scheduleRefresh = useCallback(
    (currentToken: string) => {
      clearRefreshTimer();
      const exp = getTokenExp(currentToken);
      if (!exp) return;

      const msUntilExpiry = exp * 1000 - Date.now();
      const delay = Math.max(msUntilExpiry - REFRESH_MARGIN_MS, 0);

      refreshTimer.current = setTimeout(async () => {
        try {
          const res = await fetch(`${API_BASE}/api/auth/refresh`, {
            method: "POST",
            headers: { Authorization: `Bearer ${currentToken}` },
          });
          if (res.ok) {
            const data = await res.json();
            const newToken: string = data.access_token;
            localStorage.setItem("auth_token", newToken);
            setToken(newToken);
            scheduleRefreshRef.current(newToken);
          } else {
            // Token rejected — force logout
            logout();
          }
        } catch {
          // Network error — don't logout, try again in 30s
          refreshTimer.current = setTimeout(
            () => scheduleRefreshRef.current(currentToken),
            30_000,
          );
        }
      }, delay);
    },
    [clearRefreshTimer, logout],
  );

  useEffect(() => {
    scheduleRefreshRef.current = scheduleRefresh;
  }, [scheduleRefresh]);

  const login = useCallback(
    (newToken: string) => {
      localStorage.setItem("auth_token", newToken);
      setToken(newToken);
      scheduleRefresh(newToken);
    },
    [scheduleRefresh],
  );

  useEffect(() => {
    // Rehydrating auth from localStorage is only possible after mount — SSR can't read it.
    const saved = localStorage.getItem("auth_token");
    if (saved) {
      const exp = getTokenExp(saved);
      if (exp && exp * 1000 > Date.now()) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setToken(saved);
        scheduleRefresh(saved);
      } else {
        // Token already expired — clear it
        localStorage.removeItem("auth_token");
      }
    }
    setHydrated(true);
    return () => clearRefreshTimer();
  }, [scheduleRefresh, clearRefreshTimer]);

  return (
    <AuthContext.Provider
      value={{
        token,
        hydrated,
        isAuthenticated: !!token,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
