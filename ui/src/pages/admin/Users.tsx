// Users. Who may sign in, with which role. A user is never deleted: a person who leaves is
// deactivated, so their name stays on everything they did.

import { KeyRound, Plus, UserCog, UserMinus, UserPlus } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../../api";
import { useAuth } from "../../auth";
import { DataTable, type Column } from "../../ds/DataTable";
import { ROLES } from "../../ds/labels";
import { ConfirmDialog, Dialog, useToast } from "../../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, Select } from "../../ds/primitives";
import type { AdminUser, Role } from "../../types";
import { RecentChanges, SectionHeader, errorText, useList } from "./shared";

type Open = { kind: "add" } | { kind: "role" | "password" | "active"; user: AdminUser } | null;
const MIN_PASSWORD = 8;

export default function UsersAdmin() {
  const toast = useToast();
  const { user: me } = useAuth();
  const { rows, loading, error, reload } = useList(api.adminUsers, "The users could not be loaded.");
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [open, setOpen] = useState<Open>(null);
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const [form, setForm] = useState({ username: "", role: "HANDLER" as Role, password: "", confirm: "" });
  const [attempted, setAttempted] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const shown = useMemo(() => rows.filter((u) =>
    (!q.trim() || u.username.toLowerCase().includes(q.trim().toLowerCase())) && (!role || u.role === role) && (!status || (status === "active") === u.active)),
  [rows, q, role, status]);
  const admins = rows.filter((u) => u.role === "ADMIN" && u.active).length;

  const start = (o: Open) => {
    setForm({ username: "", role: o && "user" in o ? o.user.role : "HANDLER", password: "", confirm: "" });
    setAttempted(false);
    setFormError(null);
    setOpen(o);
  };
  async function run(fn: () => Promise<unknown>, done: string) {
    setBusy(true);
    setFormError(null);
    try {
      await fn();
      toast.success(done);
      setOpen(null);
      setVersion((v) => v + 1);
      await reload();
    } catch (e) {
      setFormError(errorText(e, "The change could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  const nameError = !/^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$/.test(form.username.trim()) ? "Use 2 to 64 letters, digits, dots, dashes or underscores." : rows.some((u) => u.username === form.username.trim()) ? "That user name is taken." : null;
  const passwordError = form.password.length < MIN_PASSWORD ? `Use at least ${MIN_PASSWORD} characters.` : null;
  const confirmError = form.confirm !== form.password ? "The two passwords do not match." : null;
  const passwordFields = (
    <>
      <Field label="New password" required error={attempted ? passwordError : null} hint="Give it to the user directly. They cannot change it themselves yet.">
        <Input type="password" autoComplete="new-password" value={form.password} invalid={attempted && Boolean(passwordError)} onChange={(e) => setForm({ ...form, password: e.target.value })} />
      </Field>
      <Field label="Repeat the password" required error={attempted ? confirmError : null}>
        <Input type="password" autoComplete="new-password" value={form.confirm} invalid={attempted && Boolean(confirmError)} onChange={(e) => setForm({ ...form, confirm: e.target.value })} />
      </Field>
    </>
  );
  const roleField = (
    <Field label="Role" required hint={ROLES[form.role]?.help}>
      <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
        {Object.entries(ROLES).map(([k, r]) => <option key={k} value={k}>{r.label}</option>)}
      </Select>
    </Field>
  );
  const alert = formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{formError}</p>;

  const columns: Column<AdminUser>[] = [
    { key: "user", header: "User", render: (u) => (
      <div className="flex items-center gap-2.5">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink-100 text-[11px] font-semibold uppercase text-ink-600">{u.username.slice(0, 2)}</span>
        <span className="font-medium text-ink-900">{u.username}</span>
        {u.username === me?.username && <Badge tone="brand">You</Badge>}
      </div>
    ) },
    { key: "role", header: "Role", render: (u) => <div><div className="text-ink-800">{ROLES[u.role]?.label ?? u.role}</div><div className="max-w-[44ch] text-xs text-ink-500">{ROLES[u.role]?.help}</div></div> },
    { key: "status", header: "Status", render: (u) => u.active ? <Badge tone="ok" dot>Active</Badge> : <Badge dot>Deactivated</Badge> },
    { key: "actions", header: "", align: "right", render: (u) => {
      const self = u.username === me?.username;
      const lastAdmin = u.role === "ADMIN" && u.active && admins <= 1;
      return (
        <div className="flex justify-end gap-1 whitespace-nowrap">
          <Button size="sm" variant="ghost" icon={UserCog} disabled={lastAdmin} title={lastAdmin ? "This is the last active administrator." : undefined} onClick={() => start({ kind: "role", user: u })}>Change role</Button>
          <Button size="sm" variant="ghost" icon={KeyRound} onClick={() => start({ kind: "password", user: u })}>Reset password</Button>
          {u.active
            ? <Button size="sm" variant="ghost" icon={UserMinus} disabled={self || lastAdmin} title={self ? "You cannot deactivate yourself." : lastAdmin ? "This is the last active administrator." : undefined} onClick={() => start({ kind: "active", user: u })}>Deactivate</Button>
            : <Button size="sm" variant="ghost" icon={UserPlus} onClick={() => start({ kind: "active", user: u })}>Reactivate</Button>}
        </div>
      );
    } },
  ];

  const target = open && "user" in open ? open.user : null;
  return (
    <div>
      <SectionHeader
        title="Users" description="Who may sign in, and with which role. A person who leaves is deactivated, not deleted, so their name stays on the record of what they did."
        actions={<Button variant="primary" icon={Plus} onClick={() => start({ kind: "add" })}>Add user</Button>}
      />
      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-4">
        <Input className="sm:col-span-2" placeholder="User name" aria-label="Search users" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select aria-label="Role" value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">Any role</option>
          {Object.entries(ROLES).map(([k, r]) => <option key={k} value={k}>{r.label}</option>)}
        </Select>
        <Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Active or not</option><option value="active">Active</option><option value="inactive">Deactivated</option>
        </Select>
      </div>
      {error ? <ErrorBlock message={error} onRetry={reload} /> : (
        <DataTable
          columns={columns} rows={shown} rowKey={(u) => u.username} loading={loading}
          empty={<EmptyState title="No user matches" body="Change the search or the filters." />}
          footer={<span className="text-[13px] text-ink-500">{shown.length} of {rows.length} users, {admins} active administrator{admins === 1 ? "" : "s"}</span>}
        />
      )}
      <RecentChanges area="user" version={version} />

      <Dialog
        open={open?.kind === "add"} onClose={() => setOpen(null)} title="Add user"
        footer={<><Button onClick={() => setOpen(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { setAttempted(true); if (!nameError && !passwordError && !confirmError) void run(() => api.createUser({ username: form.username.trim(), role: form.role, password: form.password }), `User ${form.username.trim()} added.`); }}>Add user</Button></>}
      >
        <div className="space-y-4">
          <Field label="User name" required error={attempted ? nameError : null}>
            <Input autoComplete="off" value={form.username} invalid={attempted && Boolean(nameError)} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          </Field>
          {roleField}
          {passwordFields}
          {alert}
        </div>
      </Dialog>

      <Dialog
        open={open?.kind === "role"} onClose={() => setOpen(null)} title={`Change role: ${target?.username ?? ""}`}
        description="The new role applies from the user's next action."
        footer={<><Button onClick={() => setOpen(null)}>Cancel</Button><Button variant="primary" loading={busy} disabled={form.role === target?.role} onClick={() => target && run(() => api.setUserRole(target.username, form.role), `${target.username} is now ${ROLES[form.role].label.toLowerCase()}.`)}>Save role</Button></>}
      >
        <div className="space-y-4">{roleField}{alert}</div>
      </Dialog>

      <Dialog
        open={open?.kind === "password"} onClose={() => setOpen(null)} title={`Reset password: ${target?.username ?? ""}`}
        description="The old password stops working at once."
        footer={<><Button onClick={() => setOpen(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { setAttempted(true); if (target && !passwordError && !confirmError) void run(() => api.resetUserPassword(target.username, form.password), `Password reset for ${target.username}.`); }}>Reset password</Button></>}
      >
        <div className="space-y-4">{passwordFields}{alert}</div>
      </Dialog>

      <ConfirmDialog
        open={open?.kind === "active"} onClose={() => setOpen(null)} busy={busy} danger={Boolean(target?.active)}
        title={target?.active ? `Deactivate ${target.username}?` : `Reactivate ${target?.username ?? ""}?`}
        description={formError ?? (target?.active ? "They can no longer sign in. Their past work stays on the record, and they can be reactivated later." : "They can sign in again with their existing password and role.")}
        confirmLabel={target?.active ? "Deactivate user" : "Reactivate user"}
        onConfirm={() => target && run(() => api.setUserActive(target.username, !target.active), target.active ? `${target.username} deactivated.` : `${target.username} reactivated.`)}
      />
    </div>
  );
}
