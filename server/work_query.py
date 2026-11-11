"""Read models and corrections behind the work screens (cases, disputes, notifications, dashboard).

The state machines stay in their services. This module adds what the screens need around them:
searchable, paged worklists with counts; the history of one item from the transition log; and
corrections to an item that is still open, each written to that same log as an `edit` entry so
the trail shows who changed what.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .clock import utcnow
from . import cases_service, disputes_service, models, payments_service, statemachine as sm

T = models.TransitionLog


# ── history ──────────────────────────────────────────────────────────────────
def history(db: Session, entity_type: str, entity_id) -> list[dict]:
    """Every transition and edit on one item, newest first."""
    return [{"action": r.action, "from_state": r.from_state, "to_state": r.to_state, "actor": r.actor,
             "role": r.role, "at": r.at.isoformat() if r.at else None, "detail": r.detail or {}}
            for r in db.scalars(select(T).where(T.entity_type == entity_type, T.entity_id == str(entity_id))
                                .order_by(T.id.desc()))]


def _log_edit(db: Session, entity_type: str, entity_id, state: str, user: dict, changes: dict) -> None:
    db.add(T(entity_type=entity_type, entity_id=str(entity_id), from_state=state, to_state=state,
             action="edit", actor=user.get("username", "?"), role=user.get("role", "?"),
             detail={"changes": changes}))


def _page(db: Session, stmt, order, limit: int, offset: int):
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    return list(db.scalars(stmt.order_by(*order).limit(limit).offset(offset))), total


# ── cases ────────────────────────────────────────────────────────────────────
CASE_SORTS = {"opened": models.Case.id, "due": models.Case.due_at, "priority": models.Case.priority,
              "stake": models.Case.rand_at_stake}


def search_cases(db: Session, user: dict, *, q: str = "", lane: str = "", status: str = "",
                 mine: bool = False, overdue: bool = False, open_only: bool = False,
                 claim_id: str = "", sort: str = "opened", direction: str = "desc",
                 limit: int = 25, offset: int = 0) -> dict:
    C, now = models.Case, utcnow()
    base = select(C)
    if q and q.strip():
        like = f"%{q.strip()}%"
        conds = [C.claim_id.ilike(like), C.reason.ilike(like), C.assigned_to.ilike(like), C.opened_by.ilike(like)]
        if q.strip().lstrip("#").isdigit():
            conds.append(C.id == int(q.strip().lstrip("#")))
        base = base.where(or_(*conds))
    if lane:
        base = base.where(C.lane == lane)
    if claim_id:
        base = base.where(C.claim_id == claim_id)
    is_overdue = (C.status != "CLOSED") & (C.due_at.is_not(None)) & (C.due_at < now)
    ids = select(base.subquery().c.id)
    counts = dict(db.execute(select(C.status, func.count()).where(C.id.in_(ids)).group_by(C.status)).all())
    counts["OVERDUE"] = db.scalar(select(func.count()).select_from(C).where(C.id.in_(ids), is_overdue)) or 0
    counts["MINE"] = db.scalar(select(func.count()).select_from(C).where(
        C.id.in_(ids), C.assigned_to == user.get("username"), C.status != "CLOSED")) or 0
    stmt = base
    if status:
        stmt = stmt.where(C.status == status)
    if open_only:
        stmt = stmt.where(C.status != "CLOSED")
    if mine:
        stmt = stmt.where(C.assigned_to == user.get("username"), C.status != "CLOSED")
    if overdue:
        stmt = stmt.where(is_overdue)
    col = CASE_SORTS.get(sort, C.id)
    rows, total = _page(db, stmt, (col.asc() if direction == "asc" else col.desc(), C.id.desc()), limit, offset)
    return {"rows": [cases_service.item_dict(c, now) for c in rows], "total": total,
            "counts": {k: counts.get(k, 0) for k in ("OPEN", "IN_REVIEW", "ESCALATED", "CLOSED", "OVERDUE", "MINE")}}


def update_case(db: Session, case_id: int, user: dict, *, priority=None, reason=None,
                rand_at_stake=None) -> "models.Case":
    """Correct an open case: its priority (which resets the due date from when it was opened), its
    reason or the amount at stake. A closed case is a record and cannot be changed."""
    c = db.get(models.Case, case_id)
    if c is None:
        raise sm.IllegalTransition("no such case")
    if c.status == "CLOSED":
        raise sm.GateNotMet("a closed case cannot be changed")
    owner = cases_service.LANE_OWNER.get(c.lane)
    allowed = {"ADMIN", "INVESTIGATOR"} if c.status == "ESCALATED" else {"ADMIN", owner}
    if user.get("role") not in allowed:
        raise sm.WrongActor(f"only {' or '.join(sorted(x for x in allowed if x))} may change this case")
    changes: dict = {}
    if priority is not None:
        try:
            p = int(priority)
        except (TypeError, ValueError):
            raise sm.GateNotMet("priority must be 1..5") from None
        if p not in cases_service.SLA_DAYS:
            raise sm.GateNotMet("priority must be 1..5")
        if p != c.priority:
            changes["priority"] = {"from": c.priority, "to": p}
            c.priority = p
            c.due_at = (c.opened_at or utcnow()) + timedelta(days=cases_service.SLA_DAYS[p])
    if reason is not None:
        text = str(reason).strip()
        if not text:
            raise sm.GateNotMet("a case needs a reason")
        if text != c.reason:
            changes["reason"] = {"from": c.reason, "to": text}
            c.reason = text
    if rand_at_stake is not None:
        try:
            amount = round(float(rand_at_stake), 2)
        except (TypeError, ValueError):
            raise sm.GateNotMet("amount at stake must be a number") from None
        if amount < 0:
            raise sm.GateNotMet("amount at stake cannot be negative")
        if amount != c.rand_at_stake:
            changes["rand_at_stake"] = {"from": c.rand_at_stake, "to": amount}
            c.rand_at_stake = amount
    if changes:
        _log_edit(db, "case", case_id, c.status, user, changes)
        db.commit()
    return c


# ── disputes ─────────────────────────────────────────────────────────────────
DISPUTE_SORTS = {"opened": models.Dispute.id, "deadline": models.Dispute.deadline}
_DISPUTE_OPEN = ("LODGED", "UNDER_RECONSIDERATION", "REJECTED", "REFERRED")


def search_disputes(db: Session, *, q: str = "", subject: str = "", status: str = "", raised_by: str = "",
                    channel: str = "", open_only: bool = False, overdue: bool = False, claim_id: str = "",
                    sort: str = "opened", direction: str = "desc", limit: int = 25, offset: int = 0) -> dict:
    D, now = models.Dispute, utcnow()
    base = select(D)
    if q and q.strip():
        like = f"%{q.strip()}%"
        conds = [D.claim_id.ilike(like), D.grounds.ilike(like), D.linked_ref.ilike(like)]
        if q.strip().lstrip("#").isdigit():
            conds.append(D.id == int(q.strip().lstrip("#")))
        base = base.where(or_(*conds))
    for col, value in ((D.subject, subject), (D.raised_by, raised_by), (D.channel, channel), (D.claim_id, claim_id)):
        if value:
            base = base.where(col == value)
    is_open = D.status.in_(_DISPUTE_OPEN)
    is_overdue = is_open & (D.deadline.is_not(None)) & (D.deadline < now)
    ids = select(base.subquery().c.id)
    counts = dict(db.execute(select(D.status, func.count()).where(D.id.in_(ids)).group_by(D.status)).all())
    counts["OPEN"] = sum(counts.get(s, 0) for s in _DISPUTE_OPEN)
    counts["OVERDUE"] = db.scalar(select(func.count()).select_from(D).where(D.id.in_(ids), is_overdue)) or 0
    stmt = base
    if status:
        stmt = stmt.where(D.status == status)
    if open_only:
        stmt = stmt.where(is_open)
    if overdue:
        stmt = stmt.where(is_overdue)
    col = DISPUTE_SORTS.get(sort, D.id)
    rows, total = _page(db, stmt, (col.asc() if direction == "asc" else col.desc(), D.id.desc()), limit, offset)
    keys = ("OPEN", "OVERDUE", "LODGED", "UNDER_RECONSIDERATION", "REJECTED", "REFERRED", "UPHELD", "RESOLVED", "WITHDRAWN")
    return {"rows": [disputes_service.item_dict(d, now) for d in rows], "total": total,
            "counts": {k: counts.get(k, 0) for k in keys}}


def update_dispute(db: Session, dispute_id: int, user: dict, *, grounds=None) -> "models.Dispute":
    """Correct the recorded grounds of a dispute that is still open (logged)."""
    d = db.get(models.Dispute, dispute_id)
    if d is None:
        raise sm.IllegalTransition("no such dispute")
    if d.status in disputes_service.DISPUTE.terminal:
        raise sm.GateNotMet("a closed dispute cannot be changed")
    if user.get("role") not in ("ADMIN", "HANDLER", "MEDICAL_OFFICER", "LEGAL"):
        raise sm.WrongActor("your role may not change a dispute")
    if grounds is not None:
        text = str(grounds).strip()
        if not text:
            raise sm.GateNotMet("a dispute needs its grounds")
        if text != d.grounds:
            _log_edit(db, "dispute", dispute_id, d.status, user, {"grounds": {"from": d.grounds, "to": text}})
            d.grounds = text
            db.commit()
    return d


# ── notifications ────────────────────────────────────────────────────────────
def search_notifications(db: Session, *, q: str = "", status: str = "", channel: str = "", event: str = "",
                         claim_id: str = "", limit: int = 25, offset: int = 0) -> dict:
    N = models.Notification
    base = select(N)
    if q and q.strip():
        like = f"%{q.strip()}%"
        base = base.where(or_(N.claim_id.ilike(like), N.party_token.ilike(like), N.body.ilike(like)))
    for col, value in ((N.channel, channel), (N.event, event), (N.claim_id, claim_id)):
        if value:
            base = base.where(col == value)
    ids = select(base.subquery().c.id)
    counts = dict(db.execute(select(N.status, func.count()).where(N.id.in_(ids)).group_by(N.status)).all())
    stmt = base.where(N.status == status) if status else base
    rows, total = _page(db, stmt, (N.id.desc(),), limit, offset)
    out = [{"id": n.id, "claim_id": n.claim_id, "party_token": n.party_token, "channel": n.channel,
            "event": n.event, "body": n.body, "status": n.status,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "sent_at": n.sent_at.isoformat() if n.sent_at else None} for n in rows]
    events = sorted(e for e in db.scalars(select(N.event).distinct()) if e)
    return {"rows": out, "total": total, "events": events,
            "counts": {k: counts.get(k, 0) for k in ("PENDING", "SENT", "FAILED", "SUPPRESSED")}}


# ── the dashboard's work summary ─────────────────────────────────────────────
def work_summary(db: Session, user: dict) -> dict:
    """What is waiting, by queue: the figures behind the dashboard's links into each worklist."""
    C, D, N, B = models.Case, models.Dispute, models.Notification, models.PaymentBatch
    now = utcnow()
    case_open = C.status != "CLOSED"
    dispute_open = D.status.in_(_DISPUTE_OPEN)
    count = lambda model, *conds: db.scalar(select(func.count()).select_from(model).where(*conds)) or 0  # noqa: E731
    ready = [r for r in payments_service.queue(db) if r["blocked"] is None and r["source"] and (r["amount"] or 0) > 0]
    runs = dict(db.execute(select(B.status, func.count()).group_by(B.status)).all())
    return {
        "cases": {"open": count(C, case_open),
                  "mine": count(C, case_open, C.assigned_to == user.get("username")),
                  "unassigned": count(C, C.status == "OPEN"),
                  "overdue": count(C, case_open, C.due_at.is_not(None), C.due_at < now),
                  "escalated": count(C, C.status == "ESCALATED")},
        "disputes": {"open": count(D, dispute_open),
                     "new": count(D, D.status == "LODGED"),
                     "overdue": count(D, dispute_open, D.deadline.is_not(None), D.deadline < now)},
        "payments": {"ready": len(ready), "ready_amount": round(sum(r["amount"] for r in ready), 2),
                     "open_runs": runs.get("OPEN", 0), "awaiting_release": runs.get("APPROVED", 0)},
        "notifications": {"pending": count(N, N.status == "PENDING"), "failed": count(N, N.status == "FAILED")},
    }


# ── one claim's workflow history ─────────────────────────────────────────────
def claim_workflow_history(db: Session, claim_id: str) -> list[dict]:
    """Every workflow step taken on a claim, across its machines, newest first: the lifecycle,
    merits, each serious-injury assessment, each undertaking and its invoices, each litigation
    matter. `area` and `ref` say which one a step belongs to."""
    ids = lambda model, *where: [str(x) for x in db.scalars(select(model.id).where(*where))]  # noqa: E731
    undertakings = ids(models.Undertaking, models.Undertaking.claim_id == claim_id)
    invoices = ids(models.UndertakingInvoice,
                   models.UndertakingInvoice.undertaking_id.in_([int(u) for u in undertakings])) if undertakings else []
    scope = {
        "claim_lifecycle": [claim_id], "merits": [claim_id],
        "serious_injury": ids(models.SeriousInjury, models.SeriousInjury.claim_id == claim_id),
        "undertaking": undertakings, "undertaking_invoice": invoices,
        "litigation": ids(models.Litigation, models.Litigation.claim_id == claim_id),
    }
    conds = [(T.entity_type == kind) & (T.entity_id.in_(refs)) for kind, refs in scope.items() if refs]
    return [{"area": r.entity_type, "ref": r.entity_id, "action": r.action, "from_state": r.from_state,
             "to_state": r.to_state, "actor": r.actor, "role": r.role,
             "at": r.at.isoformat() if r.at else None, "detail": r.detail or {}}
            for r in db.scalars(select(T).where(or_(*conds)).order_by(T.id.desc()))]
