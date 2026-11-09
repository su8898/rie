"""Full end-to-end walkthrough of RIE against a running server, on real reference data.

Drives one personal claim through the entire journey plus a fraud/recovery scenario, exercising:
reference data + per-discipline pricing, the JWS provider rails, ingest/scoring, the five state
machines (lifecycle, merits, serious injury, offer, ... settlement), payment batches with
segregation of duties, party intelligence, clawback recovery, and the portfolio views.

    WALKTHROUGH_URL=http://localhost:8091 python3 db/walkthrough.py
"""
from __future__ import annotations

import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

from server import jws  # noqa: E402

BASE = os.environ.get("WALKTHROUGH_URL", "http://localhost:8091").rstrip("/")
RAILS_SECRET = os.environ.get("RIE_RAILS_SECRET", "rie-rails-dev-secret")
TODAY = "2026-07-05"
c = httpx.Client(base_url=BASE, timeout=60)


def stage(n, title):
    print(f"\n{'━' * 74}\n  STAGE {n} · {title}\n{'━' * 74}")


def line(k, v):
    print(f"    {k:26} {v}")


def login(user):
    c.post("/api/auth/login", json={"username": user, "password": user}).raise_for_status()


def _sup_line(code, amount, disc="GP", dx="S72", kind="TARIFF", provider="PRV-1"):
    return {"kind": kind, "code": code, "qty": 1, "amount": amount, "service_date": "2026-03-01",
            "provider_id": provider, "dx": dx, "discipline": disc}


def claim(cid, ctype, party, cas, lines, **kw):
    docs = {"RAF1": True, "OAR": True, "ID": True, "BANK": True} if ctype == "PERSONAL" else \
           {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True}
    base = {"claim_id": cid, "claim_type": ctype, "party_token": party,
            "accident_date": "2026-02-01", "lodged_on": "2026-03-01", "case_number_raw": cas,
            "today": TODAY, "payee_verified": True, "documents": docs, "lines": lines}
    base.update(kw)
    return base


def main():
    # ── 0. reference data + per-discipline pricing ──────────────────────────
    stage(0, "Reference data loaded (real RAF snapshot) + per-discipline pricing")
    login("handler")
    eds = c.get("/api/reference/editions").json()
    for e in eds:
        line(e["kind"], f"n={e['n']:,}  {e['version']}")
    disc = c.get("/api/reference/disciplines").json()
    line("disciplines", f"{len(disc)}: {', '.join(disc[:6])}...")
    for r in c.get("/api/reference/tariffs", params={"code": "4301"}).json():
        line(f"tariff 4301 [{r['discipline']}]", f"R{r['rate']:,.2f}")

    # ── 1. provider rails: JWS-signed submission ────────────────────────────
    stage(1, "Provider→fund rails: a supplier signs an RCJ claim (JWS) and gets a signed verdict")
    body = claim("RCJ-1", "SUPPLIER", "P-rcj", "CAS 5001/02/2026",
                 [_sup_line("10190", 800.0)])       # real tariff 10190 = R587.24 GP
    header = {"alg": "HS256", "jti": str(uuid.uuid4()), "exp": int(time.time()) + 300}
    sig = jws.sign_detached(header, body, RAILS_SECRET)
    r = c.post("/rails/v1/claims", json=body,
               headers={"Idempotency-Key": str(uuid.uuid4()), "X-JWS-Signature": sig}).json()
    v = r["verdict"]
    line("outcome", v["outcome"])
    line("billed -> payableNow", f"R{v['billed']:,.2f} -> R{v['payableNow']:,.2f}  (repriced off R{v['repricedOff']:,.2f})")
    rcpt = dict(r["receipt"]); rsig = rcpt.pop("signature")
    line("fund receipt signature", "VALID" if jws.verify_detached(rsig, rcpt, RAILS_SECRET) else "INVALID")

    # ── 2. personal claim intake + scoring ──────────────────────────────────
    stage(2, "Personal claim lodged (RAF 1) → scored on ingest")
    CID = "R-WALK"
    login("handler")
    rec = c.post("/api/claims", json=claim(CID, "PERSONAL", "P-walk", "CAS 5002/02/2026",
                                           [_sup_line("10190", 1000.0)])).json()
    line("band / disposition", f"{rec['band']} / {rec['disposition']}")
    line("medical_payable", f"R{rec['medical_payable']:,.2f}  (10190 billed 1000 repriced)")
    line("eligible_to_pay / holds", f"{rec['eligible_to_pay']}  {rec['holds']}")

    # ── 3. lifecycle + merits ───────────────────────────────────────────────
    stage(3, "Lifecycle + merits determination")
    wf = c.get(f"/api/claims/{CID}/workflow").json()
    line("lifecycle / merits", f"{wf['lifecycle']['stage']} / {wf['merits']['status']}")
    line("validate", c.post(f"/api/lifecycle/{CID}/validate").json()["stage"])
    line("open_merits", c.post(f"/api/lifecycle/{CID}/open_merits").json()["stage"])
    m = c.post(f"/api/merits/{CID}/accept", json={"fault_pct": 20}).json()
    line("merits accept", f"{m['status']} (fault {m['fault_pct']}%)")
    line("accept_merits", c.post(f"/api/lifecycle/{CID}/accept_merits").json()["stage"])

    # ── 4. serious injury (RAF 4) ───────────────────────────────────────────
    stage(4, "Serious injury (RAF 4) — opens general damages")
    login("medical")
    si = c.post("/api/serious-injury", json={"claim_id": CID, "list_match": True, "wpi": 35}).json()
    line("RAF 4 created", f"#{si['id']} {si['status']} (wpi {si['wpi']})")
    line("accept", c.post(f"/api/serious-injury/{si['id']}/accept").json()["status"])

    # ── 5. offer builder (heads of damage) ──────────────────────────────────
    stage(5, "Offer builder — past medical + Sweatman-capped earnings + SI-gated general damages")
    login("handler")
    offer = c.post(f"/api/offer/{CID}", json={"heads_input": {
        "loss_of_earnings": {"annual_losses": [300000, 500000]},
        "general_damages": {"proposed": 900000, "band_p25": 500000, "band_p75": 1000000}}}).json()
    h = offer["heads"]
    line("past medical", f"R{h['past_medical']:,.2f}  (apportioned 20%)")
    line("loss of earnings", f"R{h['loss_of_earnings']['total']:,.2f}  (yr2 capped at R378,581)")
    line("general damages", f"R{h['general_damages']['amount']:,.2f}")
    line("OFFER TOTAL", f"R{offer['offer_total']:,.2f}  [{offer['status']}]")

    # ── 6. settle ───────────────────────────────────────────────────────────
    stage(6, "Assemble offer → settle")
    line("make_offer", c.post(f"/api/lifecycle/{CID}/make_offer").json()["stage"])
    line("settle", c.post(f"/api/lifecycle/{CID}/settle").json()["stage"])

    # ── 7. payment batch with segregation of duties ─────────────────────────
    stage(7, "Payment batch — segregation of duties (handler assembles, admin approves, treasury pays)")
    login("handler")
    b = c.post("/api/payments/batches", json={"note": "walkthrough settlement"}).json()
    c.post(f"/api/payments/batches/{b['id']}/instructions",
           json={"claim_id": CID, "source": "SETTLEMENT", "amount": offer["offer_total"]})
    line("assembler / status", f"{b['created_by']} / OPEN")
    sod = c.post(f"/api/payments/batches/{b['id']}/approve")
    line("handler self-approve", f"HTTP {sod.status_code} (blocked — role/SoD)")
    login("admin")
    line("admin approve", c.post(f"/api/payments/batches/{b['id']}/approve").json()["status"])
    same = c.post(f"/api/payments/batches/{b['id']}/pay")
    line("admin self-pay", f"HTTP {same.status_code} (blocked — approver may not pay)")
    login("treasury")
    line("treasury pay", c.post(f"/api/payments/batches/{b['id']}/pay").json()["status"])
    login("handler")
    line("lifecycle after pay", c.get(f"/api/claims/{CID}/workflow").json()["lifecycle"]["stage"])
    line("finalize", c.post(f"/api/lifecycle/{CID}/finalize").json()["stage"])

    # ── 8. fraud analytics (party intelligence) ─────────────────────────────
    stage(8, "Party intelligence — a provider with flagged claims scores up (cohort-relative)")
    login("handler")
    clean = []
    for i in range(3):
        cid = f"R-SUS-c{i}"
        c.post("/api/claims", json=claim(cid, "SUPPLIER", f"Pc{i}", f"CAS 610{i}/02/2026",
                                         [_sup_line("10190", 700.0, provider="PRV-SUSPECT")]))
        clean.append(cid)
    for i in range(2):                                  # dx-mismatch -> FRAUD, flags the provider
        c.post("/api/claims", json=claim(f"R-SUS-f{i}", "SUPPLIER", f"Pf{i}", f"CAS 611{i}/02/2026",
                                         [_sup_line("10190", 700.0, dx="K35", provider="PRV-SUSPECT")],
                                         accident_dx_regions=["S72"]))
    login("investigator")
    provs = {p["provider_id"]: p for p in c.get("/api/parties/providers").json()}
    p = provs.get("PRV-SUSPECT", {})
    line("PRV-SUSPECT", f"score {p.get('score')} [{p.get('rating')}]  flag_rate {p.get('flag_rate')}%  cohort {p.get('cohort')}")
    fair = c.get("/api/parties/fairness").json()
    line("fairness (4/5 ratio)", f"{fair['four_fifths_ratio']}  pass={fair['pass']}")

    # ── 9. post-payment clawback recovery ───────────────────────────────────
    stage(9, "Clawback recovery — pay the suspect's clean claims, then sweep + recover")
    login("handler")
    bb = c.post("/api/payments/batches", json={"note": "suspect supplier run"}).json()
    for cid in clean:
        c.post(f"/api/payments/batches/{bb['id']}/instructions", json={"claim_id": cid, "source": "SUPPLIER"})
    login("admin")
    c.post(f"/api/payments/batches/{bb['id']}/approve")
    login("treasury")
    c.post(f"/api/payments/batches/{bb['id']}/pay")
    login("investigator")
    swept = c.post("/api/audit/sweep", params={"threshold": 20}).json()
    line("recovery sweep opened", f"{swept['n']} clawback items (provider now high-risk)")
    if swept["opened"]:
        aid = swept["opened"][0]
        c.post(f"/api/audit/{aid}/review")
        done = c.post(f"/api/audit/{aid}/recover", json={"amount": 500.0}).json()
        line("recover item", f"#{aid} {done['status']} R{done['amount_recovered']:,.2f} ({done['recovery_outcome']})")
    roi = c.get("/api/audit/roi").json()
    line("recovery ROI", f"R{roi['amount_recovered']:,.2f} of R{roi['amount_at_stake']:,.2f} at stake ({roi['recovery_rate']}%)")

    # ── 10. portfolio views ─────────────────────────────────────────────────
    stage(10, "Portfolio — dashboard + leakage accounting")
    login("handler")
    d = c.get("/api/dashboard").json()
    line("determinations", f"{d['determinations']}  bands {d['by_band']}")
    line("dispositions", d["by_disposition"])
    line("net payable / eligible", f"R{d['net_payable_total']:,.2f}  ({d['eligible_to_pay']} eligible)")
    lk = c.get("/api/leakage").json()
    line("leakage: repricing saving", f"R{lk['repricing_saving']:,.2f}")
    line("leakage: over-reference sig", f"R{lk['over_reference_signal']:,.2f}")
    line("leakage: dedupe exposure", f"R{lk['dedupe_exposure']:,.2f}")
    print(f"\n{'━' * 74}\n  Walkthrough complete — one claim R-WALK ran LODGED → FINALIZED end to end.\n{'━' * 74}")


if __name__ == "__main__":
    main()
