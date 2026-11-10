"""Adapters between the JSON claim payload (RCJ-shaped) and the engine's dataclasses."""
from __future__ import annotations

from datetime import date
from typing import Optional

import engine

from . import models


def _d(s: Optional[str]) -> Optional[date]:
    return date.fromisoformat(s) if s else None


_KINDS = ("TARIFF", "NAPPI")


def _line(l: dict) -> engine.Line:
    if l.get("kind") not in _KINDS:
        raise ValueError(f"line kind must be one of {_KINDS}, got {l.get('kind')!r}")
    qty, amount = float(l["qty"]), float(l["amount"])
    if not (qty > 0):
        raise ValueError(f"line qty must be > 0, got {qty}")
    if not (amount >= 0) or amount != amount or amount in (float("inf"), float("-inf")):
        raise ValueError(f"line amount must be a finite value >= 0, got {amount}")
    return engine.Line(
        kind=l["kind"], code=str(l["code"]), qty=qty, amount=amount,
        service_date=date.fromisoformat(l["service_date"]), provider_id=l["provider_id"],
        dx=l.get("dx") or "", emergency=bool(l.get("emergency", False)),
        scheme_paid=bool(l.get("scheme_paid", False)), discipline=l.get("discipline") or "",
    )


def json_to_claim(p: dict) -> engine.Claim:
    lines = [_line(l) for l in p.get("lines", [])]
    fault = p.get("fault_pct")
    if fault is not None:
        fault = float(fault)
        if not (0.0 <= fault <= 100.0):
            raise ValueError(f"fault_pct must be within 0..100, got {fault}")

    u = None
    if p.get("undertaking"):
        up = p["undertaking"]
        auths = [engine.Authorisation(
            codes=set(a["codes"]), qty_limit=float(a.get("qty_limit", 0.0)),
            ceiling=float(a["ceiling"]), valid_from=date.fromisoformat(a["valid_from"]),
            valid_to=date.fromisoformat(a["valid_to"]), status=a.get("status", "APPROVED"),
        ) for a in up.get("authorisations", [])]
        u = engine.Undertaking(active=bool(up["active"]), scope_dx=set(up.get("scope_dx", [])),
                               scope_coded=bool(up.get("scope_coded", True)), authorisations=auths)

    return engine.Claim(
        claim_id=p["claim_id"], claim_type=p["claim_type"], party_token=p["party_token"],
        accident_date=date.fromisoformat(p["accident_date"]),
        lodged_on=date.fromisoformat(p["lodged_on"]),
        case_number_raw=p.get("case_number_raw"), documents=dict(p.get("documents", {})),
        lines=lines, hit_and_run=bool(p.get("hit_and_run", False)),
        prescription_suspended=bool(p.get("prescription_suspended", False)),
        fault_pct=fault, merits_accepted=p.get("merits_accepted"),
        merits_ground=p.get("merits_ground"), si_accepted=p.get("si_accepted"),
        undertaking=u, claimant_deceased_on=_d(p.get("claimant_deceased_on")),
        payee_verified=bool(p.get("payee_verified", False)),
        attorney_in_standing=bool(p.get("attorney_in_standing", True)),
        provider_registered=bool(p.get("provider_registered", True)),
    )


def accident_to_engine(rec: "models.AccidentRecord") -> engine.Accident:
    return engine.Accident(
        accident_id=rec.accident_id, case_number=rec.case_number, when=rec.when_,
        where=rec.where_ or "", vehicles=set(rec.vehicles or []), parties=set(rec.parties or []),
        oar_occupants=rec.oar_occupants, sources=dict(rec.sources or {}),
        claims=list(rec.claims or []),
    )
