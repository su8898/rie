// Login page. On success, stores {username,role} in the auth context and
// redirects to /dashboard (or the page the user was bounced from).

import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api";
import { useAuth } from "../auth";

const DEV_LOGINS = ["admin", "handler", "medical", "investigator", "legal"];

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from =
    (location.state as { from?: { pathname?: string } } | null)?.from
      ?.pathname ?? "/dashboard";

  // Already logged in? Skip the form.
  if (!loading && user) return <Navigate to={from} replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 401 ? "Invalid credentials." : err.message);
      } else {
        setError("Login failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  function quickFill(u: string) {
    // Dev convenience: username == password.
    setUsername(u);
    setPassword(u);
    setError(null);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-900 text-sm font-bold text-white">
            RIE
          </div>
          <div>
            <div className="text-lg font-semibold text-slate-900">
              RAF Integrity Engine
            </div>
            <div className="text-xs text-slate-500">Operator sign-in</div>
          </div>
        </div>

        <form
          onSubmit={onSubmit}
          className="space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
        >
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">
              Username
            </label>
            <input
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500"
              placeholder="handler"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={busy || !username || !password}
            className="w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="mt-4 rounded-lg border border-slate-200 bg-white p-3">
          <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">
            Dev logins (username == password)
          </div>
          <div className="flex flex-wrap gap-1.5">
            {DEV_LOGINS.map((u) => (
              <button
                key={u}
                type="button"
                onClick={() => quickFill(u)}
                className="rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-xs text-slate-600 transition hover:bg-slate-100"
              >
                {u}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
