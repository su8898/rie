// One price list: its entries, what it is and where it came from, and every change made to it.
// A draft can be edited. A published list is fixed: a correction is a new edition.

import { Archive, CopyPlus, Download, FileUp, Gavel, Info, Pencil, Plus, Send, ShieldAlert, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { DataTable, Pager, type Column } from "../ds/DataTable";
import { LEGAL_STANDING, PRICE_LIST_STATE, dateTime, describePriceListChange, inEffect } from "../ds/labels";
import { ConfirmDialog, useToast } from "../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Facts, Input, LoadingBlock, PageHeader, Panel, Ref, Select, Stat, Tabs } from "../ds/primitives";
import { rand } from "../format";
import type { PriceListDetail, PriceListEntry, PriceListHistoryEntry } from "../types";
import { EntryFormDialog, ImportEntriesDialog } from "./pricelists/EntryForms";
import { CopyDialog, FactorsDialog, ListFormDialog, RetireDialog, StandingDialog } from "./pricelists/ListForm";

type Tab = "entries" | "overview" | "history";
type Open = "edit" | "standing" | "factors" | "copy" | "retire" | "import" | "publish" | "delete" | null;

const PAGE_SIZE = 50;
const count = (n: number) => n.toLocaleString("en-ZA");
const units = (e: PriceListEntry) => (e.units == null ? null : `${e.units.toLocaleString("en-ZA", { maximumFractionDigits: 3 })}${e.units_suffix}`);
const columnLabel = (c: string) => c.replace(/_/g, " ");

export default function PriceListRecordPage() {
  const { id = "" } = useParams();
  const listId = Number(id);
  const navigate = useNavigate();
  const toast = useToast();
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";
  const [list, setList] = useState<PriceListDetail | null>(null);
  const [history, setHistory] = useState<PriceListHistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("entries");
  const [open, setOpen] = useState<Open>(null);
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [pl, h] = await Promise.all([api.priceList(listId), api.priceListHistory(listId)]);
      setList(pl);
      setHistory(h);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The price list could not be loaded.");
    }
  }, [listId]);
  useEffect(() => { setList(null); setTab("entries"); void load(); }, [load]);

  const crumbs = [{ label: "Reference" }, { label: "Price lists", to: "/price-lists" }, { label: list?.name ?? `List ${id}` }];
  if (error) return <div><PageHeader crumbs={crumbs} title="Price list" /><ErrorBlock message={error} onRetry={load} /></div>;
  if (!list) return <div><PageHeader crumbs={crumbs} title="Price list" /><LoadingBlock /></div>;

  const draft = list.state === "DRAFT";
  const state = PRICE_LIST_STATE[list.state];
  const standing = LEGAL_STANDING[list.legal_status];
  const missing = [
    list.counts.entries === 0 && "at least one entry",
    !list.effective_from && "the date it takes effect",
    !list.source && "where it was published",
  ].filter(Boolean) as string[];
  const changed = (pl: PriceListDetail) => { setList(pl); setOpen(null); setVersion((v) => v + 1); void load(); };
  const entriesChanged = () => { setVersion((v) => v + 1); void load(); };

  async function act(kind: "publish" | "delete") {
    setBusy(true);
    try {
      if (kind === "publish") {
        changed(await api.publishPriceList(list!.id));
        toast.success("Price list published. Its entries are now fixed.");
      } else {
        await api.deletePriceList(list!.id);
        toast.success("Draft deleted.");
        navigate("/price-lists");
      }
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : kind === "publish" ? "The price list could not be published." : "The draft could not be deleted.");
      setOpen(null);
    } finally {
      setBusy(false);
    }
  }

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "entries", label: "Entries", count: list.counts.entries },
    { key: "overview", label: "Overview" },
    { key: "history", label: "History", count: history.length },
  ];

  return (
    <div>
      <PageHeader
        crumbs={crumbs}
        title={list.name}
        meta={<><Badge tone={state.tone} dot>{state.label}</Badge><Badge tone={standing.tone}>{standing.label}</Badge></>}
        subtitle={[list.edition && `Edition ${list.edition}`, list.source].filter(Boolean).join(" · ") || "No edition or source recorded"}
        actions={
          <>
            {list.counts.entries > 0 && <a href={api.priceListExportUrl(list.id)} download><Button icon={Download}>Export</Button></a>}
            {isAdmin && draft && (
              <>
                <Button icon={Pencil} onClick={() => setOpen("edit")}>Edit details</Button>
                <Button icon={FileUp} onClick={() => setOpen("import")}>Load from a file</Button>
                <Button variant="danger" icon={Trash2} onClick={() => setOpen("delete")}>Delete draft</Button>
                <Button variant="primary" icon={Send} disabled={missing.length > 0} title={missing.length ? `Needs ${missing.join(", ")}` : undefined} onClick={() => setOpen("publish")}>Publish</Button>
              </>
            )}
            {isAdmin && list.state === "PUBLISHED" && (
              <>
                <Button icon={Pencil} onClick={() => setOpen("edit")}>Edit notes</Button>
                <Button icon={Gavel} onClick={() => setOpen("standing")}>Change legal standing</Button>
                <Button icon={Archive} onClick={() => setOpen("retire")}>Retire</Button>
              </>
            )}
            {isAdmin && !draft && <Button variant={list.state === "PUBLISHED" ? "primary" : "secondary"} icon={CopyPlus} onClick={() => setOpen("copy")}>New edition</Button>}
          </>
        }
      />

      {list.legal_status === "INTERDICTED" && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-bad-line bg-bad-bg px-4 py-3 text-sm text-bad-fg">
          <ShieldAlert size={16} className="mt-0.5 shrink-0" aria-hidden />
          <div><span className="font-medium">This price list is interdicted.</span> It is kept for comparison only. {list.status_note ? `Reason: ${list.status_note}` : "No reason is recorded."}</div>
        </div>
      )}
      {draft ? (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-warn-line bg-warn-bg px-4 py-3 text-sm text-warn-fg">
          <Info size={16} className="mt-0.5 shrink-0" aria-hidden />
          <div>
            <span className="font-medium">This is a draft.</span> {isAdmin ? "Its entries and details can be changed." : "An administrator is still putting it together."}
            {missing.length > 0 && ` Before it can be published it needs ${missing.join(", ").replace(/, ([^,]*)$/, " and $1")}.`}
          </div>
        </div>
      ) : (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-info-line bg-info-bg px-4 py-3 text-sm text-info-fg">
          <Info size={16} className="mt-0.5 shrink-0" aria-hidden />
          <span>{list.state === "PUBLISHED" ? "This list is published, so its entries are fixed. To correct or update it, start a new edition." : "This list is retired. It is kept for the record."} It does not change what a claim is paid.</span>
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Entries" value={count(list.counts.entries)} hint={`${count(list.counts.codes)} distinct codes`} />
        <Stat label="With a rand value" value={count(list.counts.with_value)} />
        <Stat label="Units only" value={count(list.counts.units_only)} hint={list.counts.units_only ? "No rand value printed" : undefined} tone={list.counts.units_only ? "warn" : undefined} />
        <Stat label="Disciplines" value={count(list.counts.disciplines)} hint={inEffect(list)} />
      </div>

      <Tabs<Tab> tabs={tabs} value={tab} onChange={setTab} />

      <div className="mt-4">
        {tab === "entries" && <Entries list={list} canEdit={isAdmin && draft} version={version} onChanged={entriesChanged} onImport={() => setOpen("import")} />}

        {tab === "overview" && (
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="space-y-4 lg:col-span-2">
              <Panel title="Details">
                <Facts items={[
                  { label: "Name", value: list.name },
                  { label: "Edition", value: list.edition || "—" },
                  { label: "Published in", value: list.source ? <span className="whitespace-normal">{list.source}</span> : "—" },
                  { label: "In effect", value: inEffect(list) },
                  { label: "State", value: <><Badge tone={state.tone} dot>{state.label}</Badge><div className="mt-1 whitespace-normal text-[13px] text-ink-500">{state.help}</div></> },
                  { label: "Legal standing", value: <><Badge tone={standing.tone}>{standing.label}</Badge><div className="mt-1 whitespace-normal text-[13px] text-ink-500">{standing.help}</div></> },
                  { label: "Reason for the standing", value: list.status_note ? <span className="whitespace-normal">{list.status_note}</span> : "—" },
                  ...(list.copied_from ? [{ label: "Issued from", value: list.copied_from_name ? <Link to={`/price-lists/${list.copied_from}`} className="text-brand-700 hover:underline">{list.copied_from_name}</Link> : "An edition that has since been deleted" }] : []),
                  { label: "Created", value: `${dateTime(list.created_at)}${list.created_by ? ` by ${list.created_by}` : ""}` },
                  ...(list.published_at ? [{ label: "Published", value: `${dateTime(list.published_at)} by ${list.published_by}` }] : []),
                  ...(list.retired_at ? [{ label: "Retired", value: `${dateTime(list.retired_at)} by ${list.retired_by}` }] : []),
                  { label: "Notes", value: list.notes ? <span className="whitespace-pre-wrap">{list.notes}</span> : "—" },
                ]} />
              </Panel>
              <Panel title="Disciplines" description="The sections of the list, in the order they appear." flush>
                {list.disciplines.length === 0 ? <EmptyState title="No entries yet" /> : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead><tr className="border-b border-line bg-ink-50/70 text-left text-xs font-medium uppercase tracking-wide text-ink-500">
                        <th className="px-4 py-2">Discipline</th><th className="px-4 py-2 text-right">Entries</th><th className="px-4 py-2 text-right">With a rand value</th><th className="px-4 py-2 text-right">With units</th>
                      </tr></thead>
                      <tbody className="divide-y divide-line">
                        {list.disciplines.map((d) => (
                          <tr key={d.discipline}>
                            <td className="px-4 py-2 text-ink-900">{d.discipline ? columnLabel(d.discipline) : <span className="text-ink-500">None recorded</span>}</td>
                            <td className="tnum px-4 py-2 text-right">{count(d.entries)}</td>
                            <td className="tnum px-4 py-2 text-right">{count(d.with_value)}</td>
                            <td className="tnum px-4 py-2 text-right">{count(d.with_units)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Panel>
            </div>
            <div className="space-y-4">
              <Panel
                title="Conversion factors" description="Rand per unit, as the list states them."
                actions={isAdmin && draft ? <Button size="sm" icon={Pencil} onClick={() => setOpen("factors")}>Edit</Button> : undefined}
              >
                {list.factors.length === 0 ? <p className="text-sm text-ink-500">None recorded.</p> : (
                  <Facts items={list.factors.map((f) => ({ label: columnLabel(f.name), value: <span className="tnum">{rand(f.value)} a unit</span> }))} />
                )}
                {list.counts.units_only > 0 && <p className="mt-3 text-[13px] text-ink-500">{count(list.counts.units_only)} entries print units and no rand value. A factor is recorded here and applied to none of them.</p>}
              </Panel>
              <Panel title="Price columns" description="A code can carry one figure under each.">
                {list.columns.length === 0 ? <p className="text-sm text-ink-500">None yet.</p> : (
                  <div className="flex flex-wrap gap-1.5">{list.columns.map((c) => <Badge key={c}>{columnLabel(c)}</Badge>)}</div>
                )}
              </Panel>
            </div>
          </div>
        )}

        {tab === "history" && (
          <Panel title="History" description="Every change to this price list, with who made it." flush>
            {history.length === 0 ? <EmptyState title="No changes recorded" /> : (
              <ol className="divide-y divide-line">
                {history.map((h) => {
                  const { title, note } = describePriceListChange(h);
                  return (
                    <li key={h.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-3">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-ink-900">{title}</div>
                        {note && <div className="text-[13px] text-ink-600">{note}</div>}
                      </div>
                      <div className="text-[13px] text-ink-500">{h.actor} · {dateTime(h.at)}</div>
                    </li>
                  );
                })}
              </ol>
            )}
          </Panel>
        )}
      </div>

      <ListFormDialog open={open === "edit"} mode="edit" list={list} onClose={() => setOpen(null)} onSaved={changed} />
      <StandingDialog open={open === "standing"} list={list} onClose={() => setOpen(null)} onSaved={changed} />
      <FactorsDialog open={open === "factors"} list={list} onClose={() => setOpen(null)} onSaved={changed} />
      <RetireDialog open={open === "retire"} list={list} onClose={() => setOpen(null)} onSaved={changed} />
      <CopyDialog open={open === "copy"} list={list} onClose={() => setOpen(null)} onSaved={(pl) => { setOpen(null); navigate(`/price-lists/${pl.id}`); }} />
      <ImportEntriesDialog open={open === "import"} list={list} onClose={() => setOpen(null)} onLoaded={entriesChanged} />
      <ConfirmDialog
        open={open === "publish"} onClose={() => setOpen(null)} busy={busy} onConfirm={() => act("publish")}
        title="Publish this price list?" confirmLabel="Publish"
        description={`${count(list.counts.entries)} entries will be fixed as ${standing.label.toLowerCase()}, in effect from ${inEffect(list).replace(/^From /, "")}. After this a correction needs a new edition. Publishing does not change what a claim is paid.`}
      />
      <ConfirmDialog
        open={open === "delete"} onClose={() => setOpen(null)} busy={busy} danger onConfirm={() => act("delete")}
        title="Delete this draft?" confirmLabel="Delete draft"
        description={`The draft and its ${count(list.counts.entries)} entries are removed. This cannot be undone.`}
      />
    </div>
  );
}

function Entries({ list, canEdit, version, onChanged, onImport }: { list: PriceListDetail; canEdit: boolean; version: number; onChanged: () => void; onImport: () => void }) {
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [rows, setRows] = useState<PriceListEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<{ entry: PriceListEntry | null } | null>(null);
  const [removing, setRemoving] = useState<PriceListEntry | null>(null);
  const [busy, setBusy] = useState(false);

  const value = (k: string) => params.get(k) ?? "";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const filtered = ["q", "discipline", "column", "priced"].some((k) => value(k));
  const query = params.toString();
  const set = (changes: Record<string, string | null>, keepPage = false) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v); else next.delete(k);
    }
    if (!keepPage) next.delete("page");
    setParams(next, { replace: true });
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.priceListEntries(list.id, {
        q: value("q"), discipline: value("discipline"), column: value("column"), priced: value("priced"),
        limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE,
      });
      setRows(res.rows);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The entries could not be loaded.");
    } finally {
      setLoading(false);
    }
    // `query` is the whole filter and page state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list.id, query]);
  useEffect(() => { void load(); }, [load, version]);

  async function remove() {
    if (!removing) return;
    setBusy(true);
    try {
      await api.deletePriceListEntry(list.id, removing.id);
      toast.success("Entry removed.");
      setRemoving(null);
      onChanged();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "The entry could not be removed.");
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<PriceListEntry>[] = [
    { key: "code", header: "Code", render: (e) => (
      <div>
        {e.code ? <Ref className="font-medium text-ink-900">{e.code}</Ref> : <span className="text-xs text-ink-500">No code printed</span>}
        {e.alt_code && <div><Ref className="text-xs text-ink-500">{e.alt_code}</Ref></div>}
      </div>
    ) },
    { key: "description", header: "Description", render: (e) => (
      <div className="max-w-[60ch]">
        <div className="line-clamp-2 text-ink-800" title={e.description}>{e.description || <span className="text-ink-400">—</span>}</div>
        {e.note && <div className="mt-0.5 text-xs text-warn-fg">{e.note.replace(/_/g, " ")}</div>}
      </div>
    ) },
    { key: "discipline", header: "Discipline", render: (e) => (
      <div>
        <div className="text-ink-700">{e.discipline ? columnLabel(e.discipline) : <span className="text-ink-400">—</span>}</div>
        {e.price_column !== "standard" && <div className="text-xs text-ink-500">{columnLabel(e.price_column)}</div>}
      </div>
    ) },
    { key: "units", header: "Units", align: "right", render: (e) => units(e) ? <span className="tnum text-ink-700">{units(e)}</span> : <span className="text-ink-400">—</span> },
    { key: "value", header: "Rand value", align: "right", render: (e) => e.value_rand == null ? <span className="text-ink-400">—</span> : (
      <div><span className="tnum font-medium text-ink-900">{rand(e.value_rand)}</span>{e.unit_of_issue && <div className="text-xs text-ink-500">{e.unit_of_issue === "ea" ? "each" : e.unit_of_issue === "pr" ? "a pair" : e.unit_of_issue}</div>}</div>
    ) },
    { key: "page", header: "Page", align: "right", render: (e) => <span className="tnum text-ink-500">{e.source_page || "—"}</span> },
    ...(canEdit ? [{ key: "actions", header: "", align: "right" as const, render: (e: PriceListEntry) => (
      <div className="flex justify-end gap-1">
        <Button size="sm" variant="ghost" icon={Pencil} aria-label={`Edit entry ${e.code || e.description}`} onClick={() => setForm({ entry: e })} />
        <Button size="sm" variant="ghost" icon={Trash2} aria-label={`Remove entry ${e.code || e.description}`} onClick={() => setRemoving(e)} />
      </div>
    ) }] : []),
  ];

  return (
    <div>
      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-2 lg:grid-cols-6">
        <Input className="lg:col-span-2" placeholder="Code or words in the description" aria-label="Search entries" value={value("q")} onChange={(e) => set({ q: e.target.value })} />
        <Select aria-label="Discipline" value={value("discipline")} onChange={(e) => set({ discipline: e.target.value })}>
          <option value="">Any discipline</option>
          {list.disciplines.filter((d) => d.discipline).map((d) => <option key={d.discipline} value={d.discipline}>{columnLabel(d.discipline)}</option>)}
        </Select>
        <Select aria-label="Price column" value={value("column")} onChange={(e) => set({ column: e.target.value })}>
          <option value="">Any price column</option>
          {list.columns.map((c) => <option key={c} value={c}>{columnLabel(c)}</option>)}
        </Select>
        <Select aria-label="What is printed" value={value("priced")} onChange={(e) => set({ priced: e.target.value })}>
          <option value="">Any figure</option>
          <option value="value">With a rand value</option>
          <option value="units_only">Units only</option>
          <option value="none">No figure printed</option>
        </Select>
        <div className="flex items-center justify-end gap-2">
          {filtered && <Button size="sm" variant="ghost" icon={X} onClick={() => set({ q: null, discipline: null, column: null, priced: null })}>Clear</Button>}
          {canEdit && <Button size="sm" variant="primary" icon={Plus} onClick={() => setForm({ entry: null })}>Add entry</Button>}
        </div>
      </div>

      {error ? <ErrorBlock message={error} onRetry={load} /> : (
        <DataTable
          columns={columns} rows={rows} rowKey={(e) => String(e.id)} loading={loading}
          empty={<EmptyState
            title={filtered ? "No entry matches" : "No entries yet"}
            body={filtered ? "Change or clear the filters." : canEdit ? "Add entries one by one, or load them from a CSV file." : "This list has no entries."}
            action={!filtered && canEdit ? <Button icon={FileUp} onClick={onImport}>Load from a file</Button> : undefined}
          />}
          footer={<Pager page={page} pageSize={PAGE_SIZE} total={total} unit="entries" onPage={(p) => set({ page: p > 1 ? String(p) : null }, true)} />}
        />
      )}

      {form && (
        <EntryFormDialog
          open list={list} entry={form.entry} defaults={{ discipline: value("discipline"), column: value("column") }}
          onClose={() => setForm(null)} onSaved={() => { setForm(null); onChanged(); }}
        />
      )}
      <ConfirmDialog
        open={Boolean(removing)} onClose={() => setRemoving(null)} busy={busy} danger onConfirm={remove}
        title="Remove this entry?" confirmLabel="Remove entry"
        description={removing ? `${removing.code || "The line"}${removing.description ? `: ${removing.description.slice(0, 120)}` : ""}. The removal is recorded in the history.` : undefined}
      />
    </div>
  );
}
