"""Extract the Road Accident Fund tariff from the Government Gazette PDF.

Source: Government Gazette No. 46747, Regulation Gazette No. 11473, 19 August
2022, "Road Accident Fund Tariff 2021/2022". The English tariff is PDF pages
5 to 413 (tariff page n is PDF page n + 3). The Afrikaans translation is PDF
pages 421 to 710 and is used only as a second reading (see crosscheck.py).

The gazette states on its cover that this tariff is interdicted. This script
only reads what is printed. It makes no claim about which price list applies.

Usage:
    python3 db/raf_tariff/extract.py <gazette.pdf> [--out DIR] [--text FILE]

Needs `pdftotext` (poppler) on the PATH. `--text` reuses an existing
`pdftotext -layout` dump instead of running it again.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

PDF_TO_TARIFF_PAGE = 3
ENGLISH_END = 413  # last PDF page of the English tariff

# first PDF page, key, printed title, options
SECTIONS: list[tuple[int, str, str, dict]] = [
    (6, "ambulance", "Ambulance Services",
     {"groups": ["ems_primary_response", "interhospital_transfer"],
      "single_from": (9, "fixed_wing")}),
    (10, "biokinetics", "Biokinetics", {}),
    (11, "chinese_medicine", "Chinese Medicine and Acupuncture", {}),
    (12, "chiropractors", "Chiropractors", {}),
    (13, "clinical_pathology", "Clinical Pathology",
     {"groups": ["pathologist", "other_specialist_or_gp"]}),
    (29, "clinical_technologists", "Clinical Technologists", {}),
    (32, "dental_practitioners", "Dental Practitioners",
     {"groups": ["general_dental_practice_54", "maxillo_facial_oral_surgery_62",
                 "orthodontics_64", "periodontics_92", "prosthodontics_94"],
      "tokens": ["(54)", "(62)", "(64)", "(92)", "(94)"]}),
    (52, "dental_technicians", "Dental Technicians", {}),
    (58, "dental_therapists", "Dental Therapists", {}),
    (61, "dieticians", "Dieticians", {}),
    (63, "genetic_counsellors", "Genetic Counsellors", {}),
    (65, "hearing_aid_acousticians", "Hearing Aid Acousticians", {}),
    (66, "homeopathy", "Homeopathy", {}),
    (69, "hospice", "Hospice", {}),
    (70, "medical_practitioners", "Medical Practitioners",
     {"groups": ["specialist", "general_practitioner", "anaesthesia"],
      "code": r"\d{4}[a-z]?"}),
    (282, "mental_health_facilities", "Mental Health Care Facilities", {}),
    (283, "occupational_art_therapy", "Occupational Therapy and Art Therapy",
     {"groups": ["occupational_therapy_066", "art_therapy_067"]}),
    (287, "optometry", "Optometry", {}),
    (290, "orthoptists", "Orthoptists", {}),
    (291, "orthotics_prosthetics", "Orthotists and Prosthetists",
     {"parser": "orthotics"}),
    (324, "osteopathy", "Osteopathy", {"bare_is_value": True}),
    (326, "pharmacy", "Pharmacy", {"parser": "pharmacy"}),
    (327, "physiotherapists", "Physiotherapists", {}),
    (332, "podiatry", "Podiatry", {}),
    (337, "private_hospitals", "Private Hospitals",
     {"groups": ["column_55700", "column_55800", "column_57700"],
      "tokens": ["55700", "55800", "57700"]}),
    (353, "private_nursing", "Private Nursing", {}),
    (358, "sub_acute_facilities", "Private Sub-Acute Facilities", {}),
    (360, "psychology", "Psychology", {}),
    (363, "psychometry", "Psychometry", {}),
    (364, "radiography", "Radiography", {}),
    (368, "radiology", "Radiology",
     {"groups": ["nuclear_medicine", "radiology"], "code": r"\d{5}"}),
    (402, "registered_counsellors", "Registered Counsellors", {}),
    (403, "rehabilitation_hospitals", "Rehabilitation Hospitals", {}),
    (404, "social_workers", "Social Workers", {}),
    (406, "speech_therapy_audiology", "Speech Therapy and Audiology",
     {"groups": ["speech_therapy", "audiology"], "single_from": (407, "audiology")}),
    (410, "tissue_transportation", "Tissue Transportation", {}),
    (411, "unattached_theatres_day_clinics",
     "Unattached Operating Theatre Units and Day Clinics", {}),
]

NOISE = re.compile(
    r"GOVERNMENT GAZETTE, 19|STAATSKOERANT, 19|Road Accident Fund Tariff 2021/2022"
    r"|Page \d+ of \d+|This gazette is also available"
    r"|^\s*No\. 46747\s+\d+\s*$|^\s*\d+\s+No\. 46747\s*$")

NUM = r"(?:\d{1,3}(?: \d{3})+[.,]\d{2}|\d+[.,]\d+|\d+)"
# one cell at the end of a line: optional R, a number or dash or star, optional letters
CELL_TAIL = re.compile(
    r"(?:(?P<r>R)\s*)?(?P<n>-|\*|" + NUM + r")(?P<suf>[A-Z]{1,2})?\s*$")
UNITS_VALUE = re.compile(r"(?i)\b(units?|value)\b:?")
R_AMOUNT = re.compile(r"(?<![A-Za-z0-9])R\s*(\d{1,3}(?: \d{3})*[.,]\d{2})(?!\d)")


def norm(raw: str) -> str | None:
    """'1 404,46' -> '1404.46'; '-' and '*' -> None."""
    if raw in ("-", "*"):
        return None
    return raw.replace(" ", "").replace(",", ".")


@dataclass
class Cell:
    start: int
    end: int
    raw: str
    rand: bool
    suffix: str = ""

    @property
    def centre(self) -> float:
        return (self.start + self.end) / 2

    @property
    def number(self) -> str | None:
        return norm(self.raw)


@dataclass
class Row:
    section: str
    pdf_page: int
    line_no: int
    code: str
    description: str = ""
    alt_code: str = ""
    category: str = ""
    unit_of_issue: str = ""
    add_on: bool = False
    follows_code: str = ""
    extra: dict = field(default_factory=dict)
    cells: list[Cell] = field(default_factory=list)
    prices: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    desc_col: int = 0
    last_line: int = 0
    anchors: dict = field(default_factory=dict)
    stale: bool = False


def tail_cells(line: str, zone_min: int | None) -> tuple[list[Cell], str]:
    """Peel numeric cells off the right-hand end of a line."""
    cells: list[Cell] = []
    s = line.rstrip()
    while s:
        m = CELL_TAIL.search(s)
        if not m:
            break
        start = m.start()
        before = s[:start]
        has_r = m.group("r") is not None
        if not has_r and re.fullmatch(r"0\d+", m.group("n")):
            break  # a practice-type or item number such as 082, not a quantity
        gap = len(before) - len(before.rstrip())
        if before.strip():
            # a bare number needs clear space before it; an R value may sit
            # one space after its units figure
            if gap < (1 if has_r else 2):
                break
            if has_r and gap < 2 and not cells \
                    and not re.search(r"[\d*-][A-Z]{0,2}$", before.rstrip()):
                break
        if zone_min is not None and start < zone_min and not (
                has_r and cells and m.end("n") > zone_min):
            break
        end = m.end("suf") if m.group("suf") else m.end("n")
        cells.append(Cell(start=start, end=end, raw=m.group("n"), rand=has_r,
                          suffix=m.group("suf") or ""))
        s = before.rstrip()
    cells.reverse()
    return cells, s


def find_anchors(line: str, opts: dict, anchors: dict) -> bool:
    """Record column positions from a header line. Returns True if it was one."""
    tokens = opts.get("tokens")
    if tokens:
        bare = line
        for tok in tokens:
            bare = bare.replace(tok, " ")
        if [w for w in bare.split() if w not in ("Code", "DESCRIPTION")]:
            return False
        hit = False
        for i, tok in enumerate(tokens):
            at = line.find(tok)
            if at >= 0:
                anchors[(i, "value")] = (at, at + len(tok))
                hit = True
        return hit
    found = [(m.group(1).lower().rstrip("s"), m.start(), m.end())
             for m in UNITS_VALUE.finditer(line)]
    if len(found) < 2 or len(found) < len(opts.get("groups", [0])):
        return False
    # a header carries little else; sentences that mention "value" do not count
    words = re.findall(r"[A-Za-z]{3,}", line)
    others = [w for w in words if w.lower() not in ("units", "unit", "value")]
    plain = [w for w in others if not (w.isupper() or w in ("Add", "Codes"))]
    if len(others) > 8 or (plain and (len(found) < 4 or len(plain) > 2)):
        return False
    anchors.clear()
    g = -1
    for kind, a, b in found:
        if kind == "unit" or g < 0:
            g += 1
        anchors[(g, "units" if kind == "unit" else "value")] = (a, b)
    return True


def place(cells: list[Cell], opts: dict, anchors: dict, stale: bool,
          single: str | None) -> tuple[list[tuple[tuple, Cell]], list[str]]:
    """Give every cell a (column group, units|value) key."""
    flags: list[str] = []
    groups = opts.get("groups")
    if not groups or single:
        name = single or "standard"
        return [((name, "value" if (c.rand or opts.get("bare_is_value")) else "units"), c)
                for c in cells], flags
    cells = sorted(cells, key=lambda c: c.start)
    if opts.get("tokens") and len(cells) == len(groups):
        return [((groups[i], "value"), c) for i, c in enumerate(cells)], flags
    if not anchors:
        return [(("unassigned", "value" if c.rand else "units"), c) for c in cells], \
            ["no_column_header"]
    order = sorted(anchors, key=lambda k: anchors[k][0])
    if stale:
        # no header on this page: positions cannot be trusted, so only a full
        # row, read left to right, is assigned
        kinds = ["value" if c.rand else "units" for c in cells]
        full = [k for k in order]
        values_only = [k for k in order if k[1] == "value"]
        for cand in (full, values_only):
            if len(cand) == len(cells) and [k[1] for k in cand] == kinds:
                return [((groups[k[0]], k[1]), c) for k, c in zip(cand, cells)], \
                    ["columns_by_order_no_header_on_page"]
        return [(("unassigned", "value" if c.rand else "units"), c) for c in cells], \
            ["no_column_header_on_page"]
    out = []
    for c in cells:
        if opts.get("tokens"):
            wanted = ["value"]
        elif c.raw in ("-", "*"):
            wanted = ["units", "value"]
        else:
            wanted = ["value"] if c.rand else ["units"]
        cands = sorted((abs(c.centre - (anchors[k][0] + anchors[k][1]) / 2), k)
                       for k in order if k[1] in wanted)
        if not cands:
            flags.append("no_matching_column")
            out.append((("unassigned", wanted[0]), c))
            continue
        dist, k = cands[0]
        if c.raw not in ("-", "*"):
            if len(cands) > 1 and cands[1][0] - dist < 3:
                flags.append("column_ambiguous")
            if dist > 14:
                flags.append("far_from_column")
        out.append(((groups[k[0]] if k[0] < len(groups) else f"group_{k[0]}", k[1]), c))
    return out, flags


def collides(placed: list[tuple[tuple, Cell]]) -> bool:
    keys = [k for k, c in placed if c.raw not in ("-", "*")]
    return len(set(keys)) < len(keys)


def finish(row: Row, opts: dict, single: str | None) -> None:
    if not row.cells:
        return
    placed, flags = place(row.cells, opts, row.anchors, row.stale, single)
    row.flags += flags
    by_group: dict[str, dict] = {}
    for (group, kind), c in placed:
        p = by_group.setdefault(group, {"group": group})
        if kind in p:
            if c.raw not in ("-", "*"):
                row.flags.append("two_cells_one_column")
            continue
        p[kind] = c.number
        p[kind + "_raw"] = c.raw
        if c.suffix:
            p["suffix"] = c.suffix
    names = (opts.get("groups") or []) + ["standard", "unassigned"]
    row.prices = sorted(by_group.values(),
                        key=lambda p: names.index(p["group"]) if p["group"] in names else 99)


ORTHO_PRICED = re.compile(
    r"^(?P<lead>\s*\S.*?)\s{2,}(?:(?P<uoi>[A-Za-z]{2,5})\s+)?R\s+"
    r"(?P<val>\d{1,3}(?: \d{3})*[.,]\d{2})\s*$")
ORTHO_ITEM = re.compile(r"^[A-Z]{1,3}[A-Z0-9]{2,5}$")
ORTHO_ALT = re.compile(r"^A\d{5}(/\d+)?$")
PHARM = re.compile(
    r"^\s*(?:(?P<ptype>60)\s+)?(?P<code>\d{1,2}(?:\([a-c]\))?)\s{2,}(?P<desc>\S.*?)"
    r"\s{2,}(?:(?P<max>[\d.]+)\s+)?Pharmacist(?:\s+(?P<mins>\d+))?"
    r"(?:\s+R\s+(?P<val>[\d .]+?))?\s*$")


def parse_orthotics(pages: list[str], first: int, last: int) -> tuple[list[Row], list[dict]]:
    """Item code, second code, category or supplier code, description, unit, R value.

    Columns are told apart by where they start on the page. Component rows on
    the prosthetics pages carry only the second code; a few rows carry none.
    """
    rows: list[Row] = []
    loose: list[dict] = []
    last_item = ""
    for p in range(first, last + 1):
        parsed = []
        for i, line in enumerate(pages[p - 1].split("\n")):
            if not line.strip() or NOISE.search(line):
                continue
            m = ORTHO_PRICED.match(line)
            lead = m.group("lead") if m else line.rstrip()
            parts = [(x.start(), x.group()) for x in re.finditer(r"\S+(?: \S+)*", lead)]
            parsed.append((i, line, m, parts))
        priced = [x for x in parsed if x[2] and len(x[3]) >= 2]
        if not priced:
            continue

        def mode(vals: list[int]) -> int:
            return max(set(vals), key=vals.count)
        desc_col = mode([parts[-1][0] for _, _, _, parts in priced])
        alts = [st for _, _, _, parts in priced for st, tok in parts if ORTHO_ALT.match(tok)]
        alt_col = mode(alts) if alts else -99
        items = [parts[0][0] for _, _, _, parts in priced if parts[0][0] < alt_col - 3]
        item_col = mode(items) if items else -99
        for i, line, m, parts in parsed:
            item = alt = ""
            cats: list[str] = []
            desc: list[str] = []
            for st, tok in parts:
                if st >= desc_col - 2:
                    desc.append(tok)
                elif abs(st - item_col) <= 3 and not item:
                    head = tok.split(" ")
                    if len(head) == 2 and ORTHO_ALT.match(head[1]):
                        item, alt = head
                    else:
                        item = tok
                elif (abs(st - alt_col) <= 3 or ORTHO_ALT.match(tok)) and not alt:
                    # the second code and the category are sometimes one space apart
                    first_piece, _, more = tok.partition(" ")
                    if more and len(first_piece) >= 6:
                        alt = first_piece
                        cats.append(more)
                    else:
                        alt = tok  # e.g. "A 24051", kept exactly as printed
                else:
                    cats.append(tok)
            if not m:
                # an item code with its description but no price: the parent of
                # the component rows that follow
                if item and ORTHO_ITEM.match(item) and not alt:
                    last_item = item
                    rows.append(Row("orthotics_prosthetics", p, i, item,
                                    category=" ".join(cats), description=" ".join(desc)))
                elif rows and rows[-1].pdf_page == p and i == rows[-1].last_line + 1 \
                        and len(parts) == 1 and abs(parts[0][0] - desc_col) <= 2:
                    rows[-1].description += " " + parts[0][1]
                    rows[-1].last_line = i
                continue
            row = Row("orthotics_prosthetics", p, i, item, alt_code=alt,
                      category=" ".join(cats), description=" ".join(desc), last_line=i)
            uoi = m.group("uoi") or ""
            if not uoi:
                pass
            elif uoi.lower() in ("ea", "pr", "set", "each", "pair"):
                row.unit_of_issue = uoi
            else:
                row.description = (row.description + " " + uoi).strip()
            if item:
                last_item = item
            else:
                row.follows_code = last_item
                row.flags.append("no_item_code_printed" if alt else "no_code_printed")
            if (item and not ORTHO_ITEM.match(item)) or \
                    (alt and not re.match(r"^A\d{5}(/\d+)?$", alt)):
                row.flags.append("code_irregular_as_printed")
            row.prices = [{"group": "standard", "value": norm(m.group("val")),
                           "value_raw": m.group("val")}]
            rows.append(row)
    return rows, loose


def parse_pharmacy(pages: list[str], first: int, last: int) -> tuple[list[Row], list[dict]]:
    rows: list[Row] = []
    for p in range(first, last + 1):
        lines = pages[p - 1].split("\n")
        pending_val, pending_desc = None, ""
        for i, line in enumerate(lines):
            if NOISE.search(line) or not line.strip():
                continue
            if "The following rules" in line:
                break  # a note on two of the codes follows the table; it prices nothing
            m = PHARM.match(line)
            if m:
                desc = (pending_desc + " " + m.group("desc")).strip()
                r = Row("pharmacy", p, i, m.group("code"), desc)
                r.extra = {"practice_type": "60", "max": m.group("max"),
                           "performed_by": "Pharmacist",
                           "time_in_minutes": m.group("mins")}
                val = m.group("val") or pending_val
                if m.group("val") is None and pending_val:
                    r.flags.append("value_on_preceding_line")
                if val:
                    r.prices = [{"group": "standard", "value": norm(val.strip()),
                                 "value_raw": val.strip()}]
                rows.append(r)
                pending_val, pending_desc = None, ""
                continue
            v = re.search(r"\sR\s+([\d .]+?)\s*$", line)
            body = line[:v.start()] if v else line
            text = body.strip()
            col = len(body) - len(body.lstrip())
            if v:
                pending_val = v.group(1)
            # only the description column counts; "performed by" wraps further right
            if not text or col > 60 or not rows or rows[-1].pdf_page != p:
                continue
            if v or text[:1].isupper():
                # the first line of a description printed above its code line
                pending_desc = (pending_desc + " " + text).strip()
            else:
                # the tail of the description of the row above
                rows[-1].description = (rows[-1].description + " " + text).strip()
    return rows, []


def parse_section(pages: list[str], key: str, first: int, last: int,
                  opts: dict) -> tuple[list[Row], list[dict]]:
    if opts.get("parser") == "pharmacy":
        return parse_pharmacy(pages, first, last)
    if opts.get("parser") == "orthotics":
        return parse_orthotics(pages, first, last)
    code_pat = opts.get("code", r"\d{1,6}[A-Z]?")
    wide = re.compile(r"^(?P<ind>\s*)(?P<code>" + code_pat + r")\s{2,}(?P<rest>\S.*)$")
    tight = re.compile(r"^(?P<ind>\s*)(?P<code>" + code_pat + r") (?P<rest>\S.*)$")
    single_from = opts.get("single_from")  # (pdf page, group name)
    rows: list[Row] = []
    dropped: list[dict] = []
    anchors: dict = {}
    anchor_page = 0
    cur: Row | None = None
    last_coded = ""
    held: Row | None = None  # a priced line with no code, waiting to see what follows

    def single_for(p: int) -> str | None:
        return single_from[1] if single_from and p >= single_from[0] else None

    def placed_ok(cells: list[Cell], p: int) -> bool:
        placed, _ = place(cells, opts, anchors, anchor_page != p, single_for(p))
        return not collides(placed)

    def release() -> None:
        """The held line stands on its own: a priced row printed without a code."""
        nonlocal held, cur
        if held is None:
            return
        if all(c.raw in ("-", "*") or not c.raw.strip("0.,") for c in held.cells):
            # a heading or note with empty cells ruled across it
            if cur and cur.pdf_page == held.pdf_page and held.description \
                    and abs(held.desc_col - cur.desc_col) <= 2:
                cur.description = (cur.description + " " + held.description).strip()
        else:
            held.flags.append("no_code_printed")
            held.follows_code = last_coded
            rows.append(held)
            cur = held
        held = None

    for p in range(first, last + 1):
        last_coded = ""
        lines = pages[p - 1].split("\n")
        live = [ln for ln in lines if ln.strip() and not NOISE.search(ln)]
        r_starts = [c.start for ln in live for c in tail_cells(ln, None)[0] if c.rand]
        page_zone = min(r_starts) - 24 if r_starts else None
        code_cols = [m.start("code") for ln in live for m in [wide.match(ln)]
                     if m and re.search(r"[A-Za-z]{2}", m.group("rest"))]
        for i, line in enumerate(lines):
            if not line.strip() or NOISE.search(line):
                continue
            if opts.get("groups") and find_anchors(line, opts, anchors):
                anchor_page = p
                if not wide.match(line):
                    continue
            zone = page_zone
            if opts.get("groups") and anchors and anchor_page == p and not single_for(p):
                zone = min(a for a, _ in anchors.values()) - 10
            cells, rest = tail_cells(line, zone)
            if "Code:" in line:
                cells, rest = [], line.rstrip()
            m = wide.match(line)
            if m and not re.search(r"[A-Za-z]{2}", m.group("rest")) and code_cols \
                    and m.start("code") > max(code_cols) + 6:
                m = None  # a line of figures only, not a code
            if m:
                keep = [c for c in cells if c.start >= m.start("rest")]
                if len(keep) != len(cells):
                    cells, rest = keep, line[:keep[0].start].rstrip() if keep else line.rstrip()
            if not m:
                t = tight.match(line)
                if t and cells and len(t.group("code")) >= 2 and (
                        not code_cols
                        or min(code_cols) - 3 <= t.start("code") <= max(code_cols) + 3):
                    m = t
            if m:
                body = rest[m.start("rest"):] if len(rest) > m.start("rest") else ""
                row = Row(key, p, i, m.group("code"), desc_col=m.start("rest"), last_line=i)
                a = re.search(r"\s{2,}\+$", body)
                if a:
                    row.add_on = True
                    body = body[:a.start()]
                row.description = body.strip()
                if not row.description:
                    row.desc_col = -1  # description is printed on the next line
                row.cells = cells
                row.anchors = dict(anchors)
                row.stale = anchor_page != p
                if held is not None:
                    if held.pdf_page == p and i - held.line_no <= 2 \
                            and placed_ok(held.cells + cells, p):
                        row.cells = held.cells + cells
                        row.flags.append("cells_on_preceding_line")
                        row.description = (held.description + " " + row.description).strip()
                        held = None
                    else:
                        release()
                rows.append(row)
                cur = row
                last_coded = row.code
                continue
            release()
            text = rest.strip()
            start_col = len(rest) - len(rest.lstrip())
            if cells:
                if cur and cur.code and cur.pdf_page == p and i - cur.last_line <= 8 \
                        and (not text or abs(start_col - cur.desc_col) <= 2) \
                        and placed_ok(cur.cells + cells, p):
                    cur.cells = cur.cells + cells
                    cur.last_line = i
                    cur.flags.append("cells_on_continuation_line")
                    if text:
                        cur.description = (cur.description + " " + text).strip()
                elif text:
                    held = Row(key, p, i, "", description=text, desc_col=start_col,
                               last_line=i, cells=cells, anchors=dict(anchors),
                               stale=anchor_page != p)
                else:
                    dropped.append({"section": key, "pdf_page": p, "line_no": i,
                                    "text": re.sub(r"\s{2,}", "  ", line.strip())[:160]})
                continue
            if text and cur and cur.desc_col == -1 and cur.pdf_page == p \
                    and i - cur.last_line <= 2:
                cur.desc_col = start_col
            if text and cur and abs(start_col - cur.desc_col) <= 2:
                same = cur.pdf_page == p or (cur.pdf_page == p - 1 and i < 12)
                if cur.code and same:
                    cur.description = (cur.description + " " + text).strip()
                    if cur.pdf_page == p:
                        cur.last_line = i
                elif not cur.code and cur.pdf_page == p and i == cur.last_line + 1 \
                        and text[:1].islower():
                    cur.description = (cur.description + " " + text).strip()
                    cur.last_line = i
        release()
    for row in rows:
        finish(row, opts, single_for(row.pdf_page))
    if opts.get("groups"):
        columns_from_full_rows(rows, opts)
    return rows, dropped


def columns_from_full_rows(rows: list[Row], opts: dict) -> None:
    """A page with no header of its own: learn the columns from its complete rows."""
    by_page: dict[int, list[Row]] = {}
    for r in rows:
        by_page.setdefault(r.pdf_page, []).append(r)
    for page_rows in by_page.values():
        full = [r for r in page_rows if "columns_by_order_no_header_on_page" in r.flags]
        part = [r for r in page_rows if "no_column_header_on_page" in r.flags]
        if not full or not part:
            continue
        spots: dict[tuple, list[float]] = {}
        for r in full:
            placed, _ = place(r.cells, opts, r.anchors, True, None)
            for key, c in placed:
                spots.setdefault(key, []).append(c.end)
        learned = {k: sum(v) / len(v) for k, v in spots.items()}
        for r in part:
            by_group: dict[str, dict] = {}
            ok = True
            for c in r.cells:
                kind = "value" if c.rand else "units"
                cands = sorted((abs(c.end - x), k) for k, x in learned.items() if k[1] == kind)
                if not cands or cands[0][0] > 4:
                    ok = False
                    break
                pr = by_group.setdefault(cands[0][1][0], {"group": cands[0][1][0]})
                pr[kind] = c.number
                pr[kind + "_raw"] = c.raw
            if ok:
                names = opts["groups"]
                r.prices = sorted(by_group.values(), key=lambda q: names.index(q["group"]))
                r.flags = [f for f in r.flags if f != "no_column_header_on_page"] \
                    + ["columns_from_full_rows_on_page"]


def parse(pages: list[str]) -> tuple[list[Row], list[dict]]:
    all_rows: list[Row] = []
    loose: list[dict] = []
    for n, (first, key, _title, opts) in enumerate(SECTIONS):
        last = (SECTIONS[n + 1][0] - 1) if n + 1 < len(SECTIONS) else ENGLISH_END
        rows, dropped = parse_section(pages, key, first, last, opts)
        all_rows += rows
        loose += dropped
    return all_rows, loose


def unattributed_amounts(pages: list[str], rows: list[Row]) -> list[dict]:
    """Lines that print more rand amounts than the rows on that page account for."""
    out = []
    by_page: dict[int, list[str]] = {}
    for r in rows:
        for pr in r.prices:
            if pr.get("value_raw") and pr.get("value") is not None:
                by_page.setdefault(r.pdf_page, []).append(
                    pr["value_raw"].replace(",", "."))
    first = SECTIONS[0][0]
    for p in range(first, ENGLISH_END + 1):
        have = list(by_page.get(p, []))
        for line in pages[p - 1].split("\n"):
            if NOISE.search(line):
                continue
            for m in R_AMOUNT.finditer(line):
                v = m.group(1).replace(",", ".")
                if v in have:
                    have.remove(v)
                else:
                    out.append({"pdf_page": p, "amount": v,
                                "text": re.sub(r"\s{2,}", "  ", line.strip())[:170]})
    return out


def row_dict(r: Row) -> dict:
    no = next(i + 1 for i, sec in enumerate(SECTIONS) if sec[1] == r.section)
    key, title = r.section, SECTIONS[no - 1][2]
    d = {"discipline_no": no, "discipline": key, "discipline_title": title,
         "pdf_page": r.pdf_page, "tariff_page": r.pdf_page - PDF_TO_TARIFF_PAGE,
         "code": r.code, "description": r.description,
         "kind": "priced" if r.prices else "text_only", "prices": r.prices}
    if r.follows_code:
        d["follows_code"] = r.follows_code
    if r.alt_code:
        d["alt_code"] = r.alt_code
    if r.category:
        d["category"] = r.category
    if r.unit_of_issue:
        d["unit_of_issue"] = r.unit_of_issue
    if r.add_on:
        d["add_on"] = True
    if r.extra:
        d["extra"] = r.extra
    if r.flags:
        d["flags"] = sorted(set(r.flags))
    return d


def conversion_factors(pages: list[str]) -> dict:
    """The rand conversion factors printed at the head of Medical Practitioners.

    That section prints units only; the gazette says fees are units times one
    of these factors. They are recorded as printed and applied to nothing here.
    """
    out: dict = {}
    for p in range(SECTIONS[0][0], ENGLISH_END + 1):
        for m in re.finditer(r"([A-Za-z]+)(?: fees)? RCF - (\d+,\d+)", pages[p - 1]):
            out[m.group(1).lower()] = m.group(2).replace(",", ".")
            out["pdf_page"] = p
    return out


def pdf_text(pdf: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True,
                          capture_output=True, text=True).stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent)
    ap.add_argument("--text", type=Path, help="existing pdftotext -layout dump")
    args = ap.parse_args(argv)
    text = args.text.read_text() if args.text else pdf_text(args.pdf)
    pages = text.split("\f")
    rows, orphans = parse(pages)
    dicts = [row_dict(r) for r in rows]
    missing = unattributed_amounts(pages, rows)
    args.out.mkdir(parents=True, exist_ok=True)
    meta = {
        "source": "Government Gazette No. 46747 (Regulation Gazette No. 11473), 19 August 2022",
        "title": "Road Accident Fund Tariff 2021/2022",
        "status_note": "The gazette cover states that this tariff is interdicted.",
        "english_pdf_pages": [SECTIONS[0][0] - 1, ENGLISH_END],
        "tariff_page_is_pdf_page_minus": PDF_TO_TARIFF_PAGE,
        "medical_practitioner_conversion_factors": conversion_factors(pages),
        "rows": len(dicts),
        "priced_rows": sum(1 for d in dicts if d["kind"] == "priced"),
    }
    # one row per line: small enough to keep in the repository, and diffs stay readable
    body = ",\n".join(json.dumps(d, ensure_ascii=False) for d in dicts)
    (args.out / "raf_tariff_2021_22.json").write_text(
        '{"meta": ' + json.dumps(meta, ensure_ascii=False) + ',\n"rows": [\n' + body + "\n]}\n")
    with (args.out / "raf_tariff_2021_22_prices.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["discipline_no", "discipline", "code", "alt_code", "column",
                    "units", "units_suffix", "value_rand", "units_printed",
                    "value_printed", "unit_of_issue", "add_on",
                    "description", "tariff_page", "pdf_page", "flags"])
        for d in dicts:
            for pr in d["prices"]:
                w.writerow([d["discipline_no"], d["discipline"], d["code"],
                            d.get("alt_code", ""), pr["group"],
                            pr.get("units") or "", pr.get("suffix", ""),
                            pr.get("value") or "", pr.get("units_raw", ""),
                            pr.get("value_raw", ""), d.get("unit_of_issue", ""),
                            "yes" if d.get("add_on") else "", d["description"],
                            d["tariff_page"], d["pdf_page"],
                            " ".join(d.get("flags", []))])
    (args.out / "extract_diagnostics.json").write_text(json.dumps(
        {"cells_without_a_code_line": orphans, "amounts_not_in_any_row": missing},
        indent=1, ensure_ascii=False) + "\n")
    print(f"{meta['rows']} coded rows, {meta['priced_rows']} with at least one figure; "
          f"{len(orphans)} loose cell lines, {len(missing)} amounts not in a row")
    return 0


if __name__ == "__main__":
    sys.exit(main())
