// The dashboard. First what is waiting for you, as links into each worklist; then the state of
// the whole book of claims: how risky it is, and where claims are held.

import { AlertTriangle, ArrowRight, Banknote, Bell, Briefcase, FileText, Scale } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { DISPOSITIONS, RISK, ROLES } from "../ds/labels";
import { ErrorBlock, PageHeader, Panel, Stat, cx } from "../ds/primitives";
import { rand } from "../format";
import type { Band, Dashboard, Disposition, WorkSummary } from "../types";

interface Queue { to: string; label: string; count: number; note?: string; alert?: boolean }

function QueueCard({ icon: Icon, title, queues, all }: { icon: LucideIcon; title: string; queues: Queue[]; all: { to: string; label: string } }) {
  return (
    <div className="flex flex-col rounded-lg border border-line bg-white shadow-panel">
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        <Icon size={16} className="text-ink-500" aria-hidden />
        <h2 className="text-sm font-semibold text-ink-900">{title}</h2>
      </div>
      <ul className="flex-1 divide-y divide-line">
        {queues.map((q) => (
          <li key={q.label}>
            <Link to={q.to} className="group flex items-center justify-between gap-3 px-4 py-2.5 transition hover:bg-brand-50/40">
              <span className="min-w-0">
                <span className="block text-sm text-ink-800">{q.label}</span>
                {q.note && <span className="block text-xs text-ink-500">{q.note}</span>}
              </span>
              <span className={cx("tnum flex items-center gap-1.5 text-base font-semibold", q.alert && q.count > 0 ? "text-bad-fg" : q.count > 0 ? "text-ink-900" : "text-ink-400")}>
                {q.alert && q.count > 0 && <AlertTriangle size={14} aria-hidden />}{q.count}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <Link to={all.to} className="flex items-center gap-1 border-t border-line px-4 py-2.5 text-[13px] font-medium text-brand-700 hover:underline">{all.label} <ArrowRight size={13} aria-hidden /></Link>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [work, setWork] = useState<WorkSummary | null>(null);
  const [book, setBook] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    Promise.all([api.workSummary(), api.dashboard()])
      .then(([w, b]) => { setWork(w); setBook(b); })
      .catch((e) => setError(e instanceof ApiError ? e.message : "The dashboard could not be loaded."));
  }, []);

  const crumbs = [{ label: "Work" }, { label: "Dashboard" }];
  if (error) return <div><PageHeader crumbs={crumbs} title="Dashboard" /><ErrorBlock message={error} /></div>;

  const held = book ? book.determinations - book.eligible_to_pay : 0;
  const bands: Band[] = ["GREEN", "AMBER", "RED"];
  const barTone: Record<Band, string> = { GREEN: "bg-ok-fg", AMBER: "bg-warn-fg", RED: "bg-bad-fg" };
  const statuses = book ? (Object.entries(book.by_disposition) as [Disposition, number][]).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]) : [];
  const most = Math.max(1, ...statuses.map(([, n]) => n));

  return (
    <div>
      <PageHeader
        crumbs={crumbs}
        title={user ? `Good day, ${user.username}` : "Dashboard"}
        subtitle={user ? `${ROLES[user.role]?.label ?? user.role}. Here is what is waiting, and the state of the book.` : undefined}
      />

      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-500">Waiting for attention</h2>
      <div className="mb-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <QueueCard
          icon={Briefcase} title="Cases" all={{ to: "/cases", label: "All cases" }}
          queues={work ? [
            { to: "/cases?view=mine", label: "Assigned to you", count: work.cases.mine },
            { to: "/cases?view=unassigned", label: "Unassigned", count: work.cases.unassigned },
            { to: "/cases?view=overdue", label: "Past their due date", count: work.cases.overdue, alert: true },
            { to: "/cases?view=escalated", label: "Escalated", count: work.cases.escalated },
          ] : []}
        />
        <QueueCard
          icon={Scale} title="Disputes" all={{ to: "/disputes", label: "All disputes" }}
          queues={work ? [
            { to: "/disputes?view=new", label: "New, not yet started", count: work.disputes.new },
            { to: "/disputes?view=open", label: "Open", count: work.disputes.open },
            { to: "/disputes?view=overdue", label: "Past their deadline", count: work.disputes.overdue, alert: true },
          ] : []}
        />
        <QueueCard
          icon={Banknote} title="Payments" all={{ to: "/payments", label: "All payment runs" }}
          queues={work ? [
            { to: "/payments?tab=ready", label: "Claims ready to pay", count: work.payments.ready, note: rand(work.payments.ready_amount) },
            { to: "/payments?status=OPEN", label: "Runs being assembled", count: work.payments.open_runs },
            { to: "/payments?status=APPROVED", label: "Runs awaiting release", count: work.payments.awaiting_release },
          ] : []}
        />
        <QueueCard
          icon={Bell} title="Notifications" all={{ to: "/notifications", label: "All notifications" }}
          queues={work ? [
            { to: "/notifications?status=PENDING", label: "Waiting to send", count: work.notifications.pending },
            { to: "/notifications?status=FAILED", label: "Failed to send", count: work.notifications.failed, alert: true },
          ] : []}
        />
      </div>

      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-500">The book of claims</h2>
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Claims assessed" value={book ? book.determinations.toLocaleString("en-ZA") : "…"} />
        <Stat label="Cleared for payment" value={book ? book.eligible_to_pay.toLocaleString("en-ZA") : "…"} tone="ok" hint={book ? `${held.toLocaleString("en-ZA")} held` : undefined} />
        <Stat label="Payable now" value={book ? rand(book.net_payable_total) : "…"} hint={book ? `${rand(book.medical_payable_total)} assessed, including held claims` : undefined} />
        <Stat label="Awaiting a pricing review" value={book ? book.needs_review : "…"} tone={book?.needs_review ? "warn" : undefined} hint="A line has no reference price" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Risk" description="How the claims are rated. Each links to those claims." actions={<Link to="/claims" className="inline-flex items-center gap-1 text-[13px] text-brand-700 hover:underline"><FileText size={13} aria-hidden /> Claims</Link>}>
          {book && (
            <>
              <div className="flex h-3 overflow-hidden rounded-full bg-ink-100" role="img" aria-label="Share of claims by risk">
                {bands.map((b) => book.by_band[b] > 0 && <div key={b} className={barTone[b]} style={{ width: `${(100 * book.by_band[b]) / Math.max(1, book.determinations)}%` }} />)}
              </div>
              <ul className="mt-3 divide-y divide-line">
                {bands.map((b) => (
                  <li key={b}>
                    <Link to={`/claims?band=${b}`} className="flex items-center justify-between py-2 text-sm hover:text-brand-700">
                      <span className="flex items-center gap-2"><span className={cx("h-2.5 w-2.5 rounded-full", barTone[b])} aria-hidden />{RISK[b].label} risk</span>
                      <span className="tnum"><span className="font-semibold text-ink-900">{book.by_band[b]}</span> <span className="text-ink-500">({Math.round((100 * book.by_band[b]) / Math.max(1, book.determinations))}%)</span></span>
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Panel>
        <Panel title="Where claims stand" description="The outcome of each claim's latest assessment.">
          <ul className="space-y-2.5">
            {statuses.map(([d, n]) => (
              <li key={d}>
                <Link to={`/claims?disposition=${d}`} className="group block">
                  <div className="flex items-baseline justify-between text-sm"><span className="text-ink-800 group-hover:text-brand-700">{DISPOSITIONS[d]?.label ?? d}</span><span className="tnum font-semibold text-ink-900">{n}</span></div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-ink-100"><div className="h-full rounded-full bg-ink-700" style={{ width: `${(100 * n) / most}%` }} /></div>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
