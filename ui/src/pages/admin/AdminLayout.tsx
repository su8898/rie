// Administration. One page per setting, grouped by purpose in a side menu, so each has its own
// address and its own change history. Administrators only.

import { Suspense } from "react";
import { NavLink, Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../../auth";
import { LoadingBlock, PageHeader, cx } from "../../ds/primitives";

export const ADMIN_SECTIONS: { group: string; items: { to: string; label: string }[] }[] = [
  { group: "Access", items: [{ to: "users", label: "Users" }, { to: "channel", label: "Channel access" }] },
  { group: "Pricing", items: [{ to: "rates", label: "Dated rates" }, { to: "negotiated", label: "Negotiated rates" }] },
  { group: "Rules", items: [
    { to: "cap", label: "Statutory cap" }, { to: "preauth", label: "Pre-authorisation codes" },
    { to: "coding-rules", label: "Coding rules" }, { to: "signals", label: "Signal modes" },
  ] },
  { group: "Reference data", items: [
    { to: "diagnosis-codes", label: "Diagnosis codes" }, { to: "exclusions", label: "Flat-rate exclusions" },
    { to: "crosswalk", label: "Code crosswalk" },
  ] },
  { group: "Oversight", items: [{ to: "audit", label: "Audit log" }] },
];

export default function AdminLayout() {
  const { user } = useAuth();
  if (user && user.role !== "ADMIN") return <Navigate to="/dashboard" replace />;
  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Setup" }, { label: "Administration" }]}
        title="Administration"
        subtitle="Who may use the system, what the Fund pays against, and the rules claims are checked by. Every change is recorded."
      />
      <div className="gap-6 lg:flex">
        <nav aria-label="Administration sections" className="mb-4 flex gap-1 overflow-x-auto border-b border-line pb-2 lg:mb-0 lg:w-52 lg:shrink-0 lg:flex-col lg:gap-0 lg:overflow-visible lg:border-b-0 lg:pb-0">
          {ADMIN_SECTIONS.map((section) => (
            <div key={section.group} className="flex shrink-0 gap-1 lg:mb-4 lg:block">
              <div className="hidden px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-400 lg:block">{section.group}</div>
              {section.items.map((it) => (
                <NavLink
                  key={it.to} to={it.to}
                  className={({ isActive }) => cx(
                    "block whitespace-nowrap rounded-md px-3 py-1.5 text-sm transition",
                    isActive ? "bg-ink-900 font-medium text-white" : "text-ink-700 hover:bg-ink-100",
                  )}
                >
                  {it.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="min-w-0 flex-1"><Suspense fallback={<LoadingBlock />}><Outlet /></Suspense></div>
      </div>
    </div>
  );
}
