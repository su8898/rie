// Price lists. Each one is a whole edition of a tariff, kept as it was published: its entries,
// where it came from and its legal standing. An administrator creates and maintains them.
// A price list is a record. Claims are priced from the dated rates, not from this page.

import { Info, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { DataTable, type Column } from "../ds/DataTable";
import { LEGAL_STANDING, PRICE_LIST_STATE, inEffect, shortDate } from "../ds/labels";
import { Badge, Button, EmptyState, ErrorBlock, PageHeader, Stat } from "../ds/primitives";
import type { PriceList } from "../types";
import { ListFormDialog } from "./pricelists/ListForm";

const count = (n: number) => n.toLocaleString("en-ZA");

export default function PriceListsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";
  const [rows, setRows] = useState<PriceList[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await api.priceLists());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The price lists could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const published = rows.filter((r) => r.state === "PUBLISHED");
  const drafts = rows.filter((r) => r.state === "DRAFT");
  const interdicted = published.filter((r) => r.legal_status === "INTERDICTED");

  const columns: Column<PriceList>[] = [
    { key: "name", header: "Price list", render: (r) => (
      <div>
        <div className="font-medium text-ink-900">{r.name}</div>
        <div className="max-w-[52ch] truncate text-xs text-ink-500" title={r.source}>{[r.edition && `Edition ${r.edition}`, r.source].filter(Boolean).join(" · ") || "No edition or source recorded"}</div>
      </div>
    ) },
    { key: "state", header: "State", render: (r) => <Badge tone={PRICE_LIST_STATE[r.state].tone} dot>{PRICE_LIST_STATE[r.state].label}</Badge> },
    { key: "standing", header: "Legal standing", render: (r) => <Badge tone={LEGAL_STANDING[r.legal_status].tone}>{LEGAL_STANDING[r.legal_status].label}</Badge> },
    { key: "effect", header: "In effect", render: (r) => <span className="text-ink-700">{inEffect(r)}</span> },
    { key: "entries", header: "Entries", align: "right", render: (r) => (
      <div>
        <div className="tnum font-medium text-ink-900">{count(r.counts.entries)}</div>
        <div className="tnum text-xs text-ink-500">{count(r.counts.with_value)} with a rand value</div>
      </div>
    ) },
    { key: "by", header: "Last step", render: (r) => {
      const [what, who, when] = r.state === "RETIRED" ? ["Retired", r.retired_by, r.retired_at] : r.state === "PUBLISHED" ? ["Published", r.published_by, r.published_at] : ["Created", r.created_by, r.created_at];
      return <div><div className="text-ink-700">{what} {shortDate(when)}</div><div className="text-xs text-ink-500">{who ? `by ${who}` : ""}</div></div>;
    } },
  ];

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Reference" }, { label: "Price lists" }]}
        title="Price lists"
        subtitle="Each list is one edition of a tariff, kept as it was published, with its source and legal standing."
        actions={isAdmin && <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>New price list</Button>}
      />

      <div className="mb-4 flex items-start gap-2 rounded-lg border border-info-line bg-info-bg px-4 py-3 text-sm text-info-fg">
        <Info size={16} className="mt-0.5 shrink-0" aria-hidden />
        <span>
          A price list is a record of what was published. It does not change what a claim is paid.
          Claims are priced from the dated rates{isAdmin ? <>, under <Link to="/admin/rates" className="font-medium underline">Administration</Link></> : ""}.
        </span>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Published" value={loading ? "…" : published.length} hint="Fixed editions" />
        <Stat label="Drafts" value={loading ? "…" : drafts.length} hint="Still being put together" tone={drafts.length ? "warn" : undefined} />
        <Stat label="Interdicted" value={loading ? "…" : interdicted.length} hint="Published, kept for comparison only" tone={interdicted.length ? "bad" : undefined} />
        <Stat label="Entries held" value={loading ? "…" : count(rows.reduce((n, r) => n + r.counts.entries, 0))} hint="Across every list" />
      </div>

      {error ? <ErrorBlock message={error} onRetry={load} /> : (
        <DataTable
          columns={columns} rows={rows} rowKey={(r) => String(r.id)} loading={loading}
          onRowClick={(r) => navigate(`/price-lists/${r.id}`)}
          empty={<EmptyState
            title="No price lists yet"
            body={isAdmin ? "Create one, then add its entries one by one or load them from a file." : "An administrator creates price lists."}
            action={isAdmin ? <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>New price list</Button> : undefined}
          />}
        />
      )}

      <ListFormDialog
        open={creating} mode="create" onClose={() => setCreating(false)}
        onSaved={(pl) => { setCreating(false); navigate(`/price-lists/${pl.id}`); }}
      />
    </div>
  );
}
