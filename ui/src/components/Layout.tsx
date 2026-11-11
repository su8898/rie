// The application shell: an ink sidebar with the product's work grouped by purpose, a top bar
// with global claim search and the signed-in user, and the routed page on a paper canvas.
// On small screens the sidebar becomes a drawer.

import {
  Banknote, Bell, BookOpenText, Briefcase, Building2, Car, ClipboardList, Database, FileText, Gauge, LayoutDashboard, LogOut,
  Menu, Radar, Scale, Search, Settings, ShieldAlert, Stethoscope, X, type LucideIcon,
} from "lucide-react";
import { Suspense, useState, type FormEvent } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { LoadingBlock, cx } from "../ds/primitives";
import type { Role } from "../types";

interface Item { to: string; label: string; icon: LucideIcon; role?: Role }

const NAV: { group: string; items: Item[] }[] = [
  { group: "Work", items: [
    { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/claims", label: "Claims", icon: FileText },
    { to: "/cases", label: "Cases", icon: Briefcase },
    { to: "/disputes", label: "Disputes", icon: Scale },
    { to: "/notifications", label: "Notifications", icon: Bell },
  ] },
  { group: "Finance", items: [{ to: "/payments", label: "Payments", icon: Banknote }] },
  { group: "Providers", items: [{ to: "/practices", label: "Practices", icon: Building2 }] },
  { group: "Integrity", items: [
    { to: "/accidents", label: "Accidents", icon: Car },
    { to: "/intelligence", label: "Party intelligence", icon: Radar },
    { to: "/audit", label: "Recovery audit", icon: ShieldAlert },
    { to: "/coding", label: "Coding analysis", icon: Stethoscope },
    { to: "/governance", label: "Signal governance", icon: Gauge },
  ] },
  { group: "Reference", items: [
    { to: "/reference", label: "Reference data", icon: Database },
    { to: "/price-lists", label: "Price lists", icon: BookOpenText },
    { to: "/reasons", label: "Reason catalogue", icon: ClipboardList },
  ] },
  { group: "Setup", items: [{ to: "/admin", label: "Administration", icon: Settings, role: "ADMIN" }] },
];

const ROLE_LABEL: Record<string, string> = {
  ADMIN: "Administrator", HANDLER: "Claims handler", MEDICAL_OFFICER: "Medical officer",
  INVESTIGATOR: "Investigator", LEGAL: "Legal officer",
};

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [navOpen, setNavOpen] = useState(false);
  const [query, setQuery] = useState("");

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  function search(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    navigate(`/claims?q=${encodeURIComponent(query.trim())}`);
    setQuery("");
  }

  const initials = (user?.username ?? "?").slice(0, 2).toUpperCase();

  return (
    <div className="flex h-screen overflow-hidden bg-paper text-ink-900">
      {navOpen && <div className="fixed inset-0 z-30 bg-ink-950/50 md:hidden" onClick={() => setNavOpen(false)} aria-hidden="true" />}

      <aside
        className={cx(
          "fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-ink-900 text-ink-100 transition-transform duration-200 ease-out md:static md:w-60 md:translate-x-0",
          navOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-white/10 px-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-brand-500 font-mono text-[11px] font-medium tracking-wider text-white">RIE</div>
          <div className="leading-tight">
            <div className="text-sm font-semibold text-white">Integrity Engine</div>
            <div className="text-[11px] text-ink-400">Road Accident Fund</div>
          </div>
          <button onClick={() => setNavOpen(false)} className="ml-auto rounded p-1.5 text-ink-400 hover:bg-white/10 hover:text-white md:hidden" aria-label="Close navigation">
            <X size={18} />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-2.5 py-3" aria-label="Main">
          {NAV.map((section) => {
            const items = section.items.filter((i) => !i.role || user?.role === i.role);
            if (items.length === 0) return null;
            return (
              <div key={section.group} className="mb-4">
                <div className="px-2.5 pb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-ink-400">{section.group}</div>
                {items.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to} to={to} onClick={() => setNavOpen(false)}
                    className={({ isActive }) =>
                      cx(
                        "group relative flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition",
                        isActive ? "bg-white/10 font-medium text-white" : "text-ink-300 hover:bg-white/5 hover:text-white",
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-brand-500" aria-hidden />}
                        <Icon size={16} className={isActive ? "text-brand-200" : "text-ink-400 group-hover:text-ink-200"} aria-hidden />
                        {label}
                      </>
                    )}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>

        <div className="shrink-0 border-t border-white/10 px-4 py-3 font-mono text-[11px] text-ink-400">engine v0.1.0</div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-white px-4 sm:px-6">
          <button onClick={() => setNavOpen(true)} className="-ml-1 rounded p-1.5 text-ink-500 hover:bg-ink-100 md:hidden" aria-label="Open navigation">
            <Menu size={20} />
          </button>
          <form onSubmit={search} className="relative w-full max-w-md" role="search">
            <Search size={15} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden />
            <input
              value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search claims"
              placeholder="Search claims by reference, accident or claimant"
              className="h-9 w-full rounded-md border border-line bg-ink-50 pl-8 pr-3 text-sm text-ink-900 placeholder:text-ink-400 transition focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-brand-100"
            />
          </form>
          <div className="ml-auto flex items-center gap-3">
            <div className="hidden text-right leading-tight sm:block">
              <div className="text-sm font-medium text-ink-900">{user?.username}</div>
              <div className="text-xs text-ink-500">{ROLE_LABEL[user?.role ?? ""] ?? user?.role}</div>
            </div>
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-ink-900 text-xs font-medium text-white" aria-hidden>{initials}</div>
            <button onClick={handleLogout} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-strong px-2.5 text-[13px] font-medium text-ink-700 transition hover:bg-ink-50">
              <LogOut size={14} aria-hidden /> Sign out
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1400px] p-4 sm:p-6">
            <Suspense fallback={<LoadingBlock />}><Outlet /></Suspense>
          </div>
        </main>
      </div>
    </div>
  );
}
