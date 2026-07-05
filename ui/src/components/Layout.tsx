// App shell: left nav + top bar with the logged-in user and logout. On md+ the
// nav is a static sidebar; on mobile it collapses to an off-canvas drawer
// toggled by a hamburger in the top bar (backdrop + nav-link taps close it).
// The routed page renders in <Outlet />.

import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import type { Role } from "../types";

const NAV: { to: string; label: string; role?: Role }[] = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/claims", label: "Claims" },
  { to: "/submit", label: "Submit" },
  { to: "/payments", label: "Payments" },
  { to: "/cases", label: "Cases" },
  { to: "/disputes", label: "Disputes" },
  { to: "/audit", label: "Audit" },
  { to: "/accidents", label: "Accidents" },
  { to: "/intelligence", label: "Intelligence" },
  { to: "/coding", label: "Coding" },
  { to: "/governance", label: "Governance" },
  { to: "/notifications", label: "Notifications" },
  { to: "/reference", label: "Reference" },
  { to: "/reasons", label: "Reasons" },
  { to: "/admin", label: "Admin", role: "ADMIN" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [navOpen, setNavOpen] = useState(false);

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 text-slate-900">
      {/* Mobile backdrop (tap to close) */}
      {navOpen && (
        <div
          className="fixed inset-0 z-30 bg-slate-900/40 md:hidden"
          onClick={() => setNavOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Left nav — off-canvas drawer on mobile, static sidebar on md+ */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-slate-200 bg-white transition-transform duration-200 ease-out md:static md:z-auto md:w-56 md:translate-x-0 ${
          navOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-14 items-center gap-2 border-b border-slate-200 px-4">
          <div className="flex h-7 w-7 items-center justify-center rounded bg-slate-900 text-xs font-bold text-white">
            RIE
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold">RAF Integrity</div>
            <div className="text-[10px] uppercase tracking-wide text-slate-400">
              Engine
            </div>
          </div>
          <button
            onClick={() => setNavOpen(false)}
            className="ml-auto rounded-md p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 md:hidden"
            aria-label="Close navigation"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
          {NAV.filter((item) => !item.role || user?.role === item.role).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => setNavOpen(false)}
              className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm font-medium transition ${
                  isActive
                    ? "bg-slate-900 text-white"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-200 p-3 text-[11px] text-slate-400">
          engine v0.1.0
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 flex-shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setNavOpen(true)}
              className="-ml-1 rounded-md p-1.5 text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 md:hidden"
              aria-label="Open navigation"
            >
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              >
                <path d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div className="text-sm text-slate-400">Operator Console</div>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right leading-tight">
              <div className="text-sm font-medium text-slate-800">
                {user?.username}
              </div>
              <div className="text-[11px] uppercase tracking-wide text-slate-400">
                {user?.role}
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
            >
              Log out
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-4 sm:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
