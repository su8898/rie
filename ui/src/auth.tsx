// Auth context: resolves the current session via GET /api/auth/me on mount,
// exposes login/logout, and gates the app. All routes except /login are
// protected by <RequireAuth>.
//
// Sessions do not outlive the server's view of them (H10): any API call that
// answers 401 raises UNAUTHORIZED_EVENT and the user is dropped, so the next
// render of a protected route redirects to /login. The session is also
// re-checked against /api/auth/me whenever the tab regains focus and on a
// timer, so a demotion or deactivation shows up (role refresh / logout)
// without waiting for the next failed call.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, ApiError, UNAUTHORIZED_EVENT } from "./api";
import type { AuthUser } from "./types";

const RECHECK_MS = 5 * 60 * 1000;

interface AuthState {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    api
      .me()
      .then((u) => {
        if (alive) setUser(u);
      })
      .catch((e) => {
        // 401 = not logged in (expected). Anything else we also treat as logged-out.
        if (!(e instanceof ApiError)) throw e;
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  // Drop the session the moment the server says it is gone (H10).
  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  // Re-check /me on focus and on a timer while logged in: picks up role changes
  // (the server re-reads the role per request) and expiry without a failed call.
  useEffect(() => {
    if (!user) return;
    let alive = true;
    const recheck = () => {
      if (document.visibilityState === "hidden") return;
      api
        .me()
        .then((u) => {
          if (!alive) return;
          setUser((prev) =>
            prev && prev.username === u.username && prev.role === u.role ? prev : u,
          );
        })
        .catch((e) => {
          if (alive && e instanceof ApiError && e.status === 401) setUser(null);
        });
    };
    const timer = window.setInterval(recheck, RECHECK_MS);
    document.addEventListener("visibilitychange", recheck);
    return () => {
      alive = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", recheck);
    };
  }, [user]);

  const login = useCallback(async (username: string, password: string) => {
    const u = await api.login(username, password);
    setUser(u);
    return u;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, loading, login, logout }),
    [user, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

// Route guard. While the session is resolving, show a neutral splash;
// once resolved, redirect to /login if unauthenticated.
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-ink-400">
        Loading session…
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <>{children}</>;
}
