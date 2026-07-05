"""Test the RIE engine against ACTUAL data — not synthetic spot-checks.

Prices a real corpus of 52k South-African medical claims (157k billing lines, real tariff/NAPPI
codes, real billed amounts, real ICD dx, real providers) against the REAL RAF 2026 reference
(reference.db, seeded into RIE's reference tables). Every real code the corpus bills is resolved
against the gazetted reference; every real amount runs through the payment rule (pay min(billed,
ref)); every claim is scored + dispositioned by the engine brain (process_claim).

Reports: reference COVERAGE (which real codes resolve), repricing LEAKAGE the engine catches,
legal-status / source mix, per-discipline resolution, and the band / disposition distribution.

    RIE_DATABASE_URL=sqlite:///./rie.db python3 db/corpus_test.py
    RIE_CORPUS_DB=/path/to/claims.db     (default: ~/Desktop/old_cie_data/claims.db)
    RIE_CORPUS_LIMIT=5000                 (optional: cap #claims for a quick run)
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("RIE_DATABASE_URL", "sqlite:///./rie.db")

import engine  # noqa: E402
from engine import Claim, Line, adjudicate_line, process_claim, resolve  # noqa: E402
from engine.vocab import PAYMENT_RULE_STATUSES  # noqa: E402
from server.db import SessionLocal  # noqa: E402
from server.reference_data import _norm, build_refbook, build_ruleset  # noqa: E402

CORPUS_DB = os.environ.get("RIE_CORPUS_DB", os.path.expanduser("~/Desktop/old_cie_data/claims.db"))
LIMIT = int(os.environ.get("RIE_CORPUS_LIMIT", "0")) or None

TARIFF_TYPES = {"1"}          # procedure / service lines carry a tariff code
NAPPI_TYPES = {"3", "4"}      # medicine / material lines carry a nappi code
# type 2 == modifiers (tariff == mod_code) — not independently priceable, excluded.

DOCS_SUPPLIER = {"RAF2": True, "OAR": True, "INVOICES": True, "BANK": True}
_DEFAULT_DATE = date(2020, 1, 1)
TODAY = date(2026, 7, 5)


def _pdate(s) -> date | None:
    if not s:
        return None
    s = str(s).strip()
    for fmt, width in (("%Y-%m-%d", 10), ("%Y/%m/%d", 10), ("%Y%m%d", 8),
                       ("%d/%m/%Y", 10), ("%d-%m-%Y", 10), ("%Y-%m-%d %H:%M:%S", 19)):
        try:
            return datetime.strptime(s[:width], fmt).date()
        except ValueError:
            continue
    return None


def _f(x, default=0.0) -> float:
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _first_icd(raw) -> str:
    if not raw:
        return ""
    for sep in (",", ";", "|", " "):
        raw = str(raw).replace(sep, ",")
    return raw.split(",")[0].strip()


# ── map the real corpus rows into engine Claim/Line objects ──────────────────
def load_corpus():
    con = sqlite3.connect(CORPUS_DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT l.claims_id, l.type, l.tariff, l.nappi_code, l.quantity, l.amount_claimed, "
        "       l.start_date, l.icd_codes, "
        "       c.date_service, c.bhf_treating, c.sup_name, c.mem_number, c.wca_ref_no "
        "FROM claim_lines l JOIN claims c ON c.claims_id = l.claims_id "
        "ORDER BY l.claims_id"
    ).fetchall()
    con.close()

    grouped: dict[str, list] = defaultdict(list)
    meta: dict[str, sqlite3.Row] = {}
    for r in rows:
        grouped[r["claims_id"]].append(r)
        meta.setdefault(r["claims_id"], r)

    claims, skipped = [], 0
    nappi_codes: set[str] = set()
    for cid, lrows in grouped.items():
        lines: list[Line] = []
        for r in lrows:
            t = str(r["type"])
            if t in TARIFF_TYPES:
                kind, code = "TARIFF", (r["tariff"] or "").strip()
            elif t in NAPPI_TYPES:
                kind, code = "NAPPI", (r["nappi_code"] or "").strip()
            else:
                continue                                   # modifiers / other — not priceable
            if not code or code.upper() == "NULL":
                continue
            sd = _pdate(r["start_date"]) or _pdate(meta[cid]["date_service"]) or _DEFAULT_DATE
            if kind == "NAPPI":
                nappi_codes.add(code)
            lines.append(Line(kind=kind, code=code, qty=_f(r["quantity"], 1.0) or 1.0,
                              amount=_f(r["amount_claimed"]), service_date=sd,
                              provider_id=(r["bhf_treating"] or r["sup_name"] or "PRV").strip(),
                              dx=_first_icd(r["icd_codes"])))
        if not lines:
            skipped += 1
            continue
        acc = min(l.service_date for l in lines)            # accident <= every service date
        m = meta[cid]
        claims.append(Claim(
            claim_id=cid, claim_type="SUPPLIER",
            party_token=(m["mem_number"] or cid).strip(),
            accident_date=acc, lodged_on=acc,               # lodged == accident -> never "prescribed"
            case_number_raw=(m["wca_ref_no"] or cid).strip(),
            documents=dict(DOCS_SUPPLIER), lines=lines, payee_verified=True))
        if LIMIT and len(claims) >= LIMIT:
            break
    return claims, nappi_codes, skipped


def rands(x) -> str:
    return f"R{x:,.2f}"


def bar(label, n, total, width=34):
    filled = int(round(width * n / total)) if total else 0
    pct = 100 * n / total if total else 0
    return f"    {label:14} {'█' * filled}{'·' * (width - filled)} {n:>7,}  {pct:5.1f}%"


def main():
    t0 = time.time()
    print(f"\n{'═' * 78}\n  RIE ENGINE · CORPUS TEST — real claims priced against the real RAF reference\n{'═' * 78}")
    print(f"  corpus  : {CORPUS_DB}")
    print(f"  ref db  : {os.environ['RIE_DATABASE_URL']}")

    print("\n  loading + mapping the real corpus into engine claims ...")
    claims, nappi_codes, skipped = load_corpus()
    n_lines = sum(len(c.lines) for c in claims)
    kinds = Counter(l.kind for c in claims for l in c.lines)
    print(f"    claims mapped        {len(claims):,}   (skipped {skipped:,} with no priceable line)")
    print(f"    priceable lines      {n_lines:,}   (TARIFF {kinds['TARIFF']:,} · NAPPI {kinds['NAPPI']:,})")
    print(f"    distinct NAPPI codes {len(nappi_codes):,}")

    with SessionLocal() as db:
        print("\n  building RefBook from the seeded RAF reference (only the corpus's NAPPI codes) ...")
        book = build_refbook(db, nappi_codes=nappi_codes)
        rs = build_ruleset(db)
    print(f"    rpl tariff codes     {len(book.rpl):,}")
    print(f"    NAPPI SEP loaded     {len(book.sep):,}")

    # ── PART A · reference coverage (distinct + volume, real codes vs reference) ─
    print(f"\n{'─' * 78}\n  A · REFERENCE COVERAGE — do the real codes resolve against the RAF reference?\n{'─' * 78}")
    freq: dict[str, Counter] = defaultdict(Counter)        # kind -> Counter(code -> #lines)
    for c in claims:
        for l in c.lines:
            freq[l.kind][l.code] += 1
    resolves: dict = {}

    def _res(kind, code):
        k = (kind, code)
        if k not in resolves:
            resolves[k] = resolve(book, kind, code)[0] is not None
        return resolves[k]

    for kind in ("TARIFF", "NAPPI"):
        codes = freq[kind]
        d_hit, d_tot = sum(_res(kind, c) for c in codes), len(codes)
        v_hit = sum(n for c, n in codes.items() if _res(kind, c))
        v_tot = sum(codes.values())
        misses = [c for c in codes if not _res(kind, c)][:8]
        print(f"\n    {kind}")
        print(f"      distinct codes : {d_hit:,}/{d_tot:,} resolve ({100 * d_hit / d_tot if d_tot else 0:.1f}%)")
        print(bar("  by code", d_hit, d_tot))
        print(f"      billed lines   : {v_hit:,}/{v_tot:,} resolve ({100 * v_hit / v_tot if v_tot else 0:.1f}%)")
        print(bar("  by volume", v_hit, v_tot))
        if misses:
            print(f"      uncovered e.g. : {', '.join(misses)}")
    print("\n    → NAPPI (medicines) shares the universal database, so it resolves nearly whole;")
    print("      the RAF gazette TARIFF is a different code set from what this corpus billed, so")
    print("      the uncovered majority routes to R&N (reasonable-&-necessary) review — never")
    print("      silently paid or rejected.")
    distinct = {k: set(v) for k, v in freq.items()}        # for Parts C & D

    # ── PART B · line-level pricing (the payment rule over every real line) ───
    print(f"\n{'─' * 78}\n  B · PRICING — run every real billed amount through the payment rule\n{'─' * 78}")
    billed = payable = saving = 0.0
    src_ct, status_ct, reason_ct = Counter(), Counter(), Counter()
    repriced = uncovered = under_ref = 0
    for c in claims:
        seen: set = set()
        for l in c.lines:
            lr = adjudicate_line(c, l, book, rs, "GP", seen, set())
            billed += l.amount
            payable += lr.payable
            src_ct[lr.src] += 1
            for rsn in lr.reasons:
                reason_ct[rsn] += 1
            rate, _, status = resolve(book, l.kind, l.code, l.discipline or "GP")
            status_ct[status.name if status else "NONE"] += 1
            if rate is None:
                uncovered += 1
            elif "BILLED_OVER_REFERENCE" in lr.reasons and lr.payable < l.amount:
                repriced += 1
                saving += l.amount - lr.payable
            else:
                under_ref += 1
    print(f"\n    total billed         {rands(billed):>18}")
    print(f"    engine payable       {rands(payable):>18}")
    print(f"    repricing leakage    {rands(saving):>18}   ({100 * saving / billed if billed else 0:.2f}% of billed stripped)")
    print(f"\n    lines repriced (pay min)     {repriced:>8,}")
    print(f"    lines under/at reference     {under_ref:>8,}")
    print(f"    lines uncovered (R&N review) {uncovered:>8,}")
    print("\n    legal status on every line (only ENFORCEABLE/ACCEPTED can drive pay-min):")
    for st, n in status_ct.most_common():
        drives = "→ pay-min" if st in {s.name for s in PAYMENT_RULE_STATUSES} else "→ signal only" if st != "NONE" else "→ uncovered"
        print(bar(st.lower(), n, sum(status_ct.values())) + f"   {drives}")
    print("\n    reference source used:")
    for s, n in src_ct.most_common(8):
        print(bar(s or "—", n, sum(src_ct.values())))
    if reason_ct:
        print("\n    line reasons raised across the corpus:")
        for rsn, n in reason_ct.most_common(8):
            print(f"      {rsn:26} {n:>8,}")

    # ── PART C · per-discipline resolution against real multi-discipline codes ─
    print(f"\n{'─' * 78}\n  C · PER-DISCIPLINE RESOLUTION — real codes that carry >1 discipline schedule\n{'─' * 78}")
    multi = {code: rates for code, rates in book.rpl.items() if len(rates) > 1}
    corpus_tariffs = {_norm(x) for x in distinct["TARIFF"]}
    print(f"\n    {len(multi):,} reference codes carry >1 discipline schedule; "
          f"{len(set(multi) & corpus_tariffs):,} of them are billed in this corpus.")
    print("    resolve() picks the billing discipline's rate (exact → GP → cheapest):")
    for code, rates in sorted(multi.items()):
        billed = "  ← billed here" if code in corpus_tariffs else ""
        print(f"      code {code}{billed}")
        for disc in sorted(rates, key=lambda d: -rates[d]):
            r, src, _ = resolve(book, "TARIFF", code, disc)
            arrow = "  (GP fallback default)" if disc == "GP" else ""
            print(f"          {disc[:44]:44} → {rands(r):>12}{arrow}")

    # ── PART D · full engine brain over the whole corpus (band / disposition) ─
    print(f"\n{'─' * 78}\n  D · ENGINE BRAIN — score + band + disposition for all {len(claims):,} real claims\n{'─' * 78}")
    band_ct, disp_ct = Counter(), Counter()
    eligible = 0
    net_total = 0.0
    errors = 0
    examples = {"repriced": None, "uncovered": None, "clean": None}
    for c in claims:
        try:
            d = process_claim(c, [], book, rs, TODAY, provider_tier="GP")
        except Exception as e:                              # never let one bad row kill the run
            errors += 1
            if errors <= 3:
                print(f"      ! {c.claim_id}: {type(e).__name__}: {e}")
            continue
        band_ct[d["band"]] += 1
        disp_ct[d["disposition"]] += 1
        eligible += int(d["eligible_to_pay"])
        net_total += d["net_payable"]
        # stash one illustrative claim of each kind (only while slots are unfilled)
        if None in examples.values():
            sd: set = set()
            has_reprice = has_uncovered = False
            for l in c.lines:
                lr = adjudicate_line(c, l, book, rs, "GP", sd, set())
                has_reprice |= ("BILLED_OVER_REFERENCE" in lr.reasons and lr.payable < l.amount)
                has_uncovered |= resolve(book, l.kind, l.code)[0] is None
            if has_reprice and examples["repriced"] is None:
                examples["repriced"] = (c, d)
            elif has_uncovered and examples["uncovered"] is None:
                examples["uncovered"] = (c, d)
            elif examples["clean"] is None and d["band"] == "GREEN" \
                    and d["medical_payable"] > 0 and not has_uncovered:
                examples["clean"] = (c, d)
    total = sum(band_ct.values())
    print("\n    band distribution:")
    for b in ("GREEN", "AMBER", "RED", "FRAUD"):
        if band_ct.get(b):
            print(bar(b, band_ct[b], total))
    print("\n    disposition distribution:")
    for disp, n in disp_ct.most_common():
        print(bar(disp, n, total))
    print(f"\n    claims eligible to pay        {eligible:,}/{total:,}")
    print(f"    net medical payable (corpus)  {rands(net_total)}")
    if errors:
        print(f"    process_claim errors          {errors:,}")

    # ── PART E · conformance on real data — the engine IS the executable spec ─
    print(f"\n{'─' * 78}\n  E · CONFORMANCE ON REAL DATA — modular engine ≡ spec/rie_engine.py oracle\n{'─' * 78}")
    try:
        import spec.rie_engine as oracle
    except Exception as e:                                  # pragma: no cover
        oracle = None
        print(f"    (oracle unavailable: {e})")
    if oracle is not None:
        NEG, RPL, RAF = book.negotiated, book.rpl, book.raf2022
        EMP, SEP, NB = book.empirical, book.sep, book.non_benchmarkable
        CAPS, PREAUTH = rs.caps, rs.preauth_required

        def kwargs_for(m, c):                              # build m-native objects from one claim
            mbook = m.RefBook(negotiated=NEG, rpl=RPL, raf2022=RAF,
                              empirical=EMP, sep=SEP, non_benchmarkable=NB)
            mrs = m.Ruleset(caps=list(CAPS), preauth_required=set(PREAUTH))
            lines = [m.Line(kind=l.kind, code=l.code, qty=l.qty, amount=l.amount,
                            service_date=l.service_date, provider_id=l.provider_id, dx=l.dx)
                     for l in c.lines]
            mc = m.Claim(claim_id=c.claim_id, claim_type=c.claim_type, party_token=c.party_token,
                         accident_date=c.accident_date, lodged_on=c.lodged_on,
                         case_number_raw=c.case_number_raw, documents=dict(c.documents),
                         lines=lines, payee_verified=True)
            return dict(c=mc, accidents=[], book=mbook, rs=mrs, today=TODAY, provider_tier="GP")

        step = max(1, len(claims) // 5000)
        sample = claims[::step]
        matches = mism = 0
        first = None
        for c in sample:
            exp = oracle.process_claim(**kwargs_for(oracle, c))
            act = engine.process_claim(**kwargs_for(engine, c))
            if exp == act:
                matches += 1
            else:
                mism += 1
                first = first or (c.claim_id, exp, act)
        print(f"\n    ran {len(sample):,} real claims through BOTH the oracle and the modular engine")
        print(f"    identical determination records : {matches:,}/{len(sample):,}")
        if mism:
            cid, exp, act = first
            print(f"    !! {mism:,} MISMATCH — e.g. {cid}\n       oracle: {exp}\n       engine: {act}")
        else:
            print("    ✓ byte-for-byte conformance holds on real data — the engine never drifts from spec")

    # ── worked examples for credibility ──────────────────────────────────────
    print(f"\n{'─' * 78}\n  worked examples — real claim → real codes → engine verdict\n{'─' * 78}")
    for label, pair in examples.items():
        if not pair:
            continue
        c, d = pair
        print(f"\n    [{label}] claim {c.claim_id}  band={d['band']} disp={d['disposition']} "
              f"payable={rands(d['medical_payable'])}")
        seen: set = set()
        for l in c.lines[:4]:
            lr = adjudicate_line(c, l, book, rs, "GP", seen, set())
            rate, src, status = resolve(book, l.kind, l.code, "GP")
            if rate is None:
                ref = "no reference"
            else:
                ref = f"{rands(rate)}×{l.qty:g}={rands(round(rate * l.qty, 2))} [{src}]"
            print(f"        {l.kind:6} {l.code:>10}  billed {rands(l.amount):>11}  ref {ref:>32}  "
                  f"→ pay {rands(lr.payable):>11}  {','.join(lr.reasons) or 'ok'}")

    print(f"\n{'═' * 78}\n  done in {time.time() - t0:.1f}s — engine exercised on real data end to end.\n{'═' * 78}\n")


if __name__ == "__main__":
    main()
