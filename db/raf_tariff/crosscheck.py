"""Second reading of the RAF tariff: compare the English extract with the
Afrikaans translation printed in the same gazette (PDF pages 421 to 710).

The Afrikaans copy is typeset separately (different page breaks, upright
pages, decimal commas), so it is an independent reading of the text layer.
Where the two copies print different figures for the same code, the row is
reported. A difference can be a misreading by the extractor or a difference
between the two printed copies; only looking at the pages tells which.

Usage:
    python3 db/raf_tariff/crosscheck.py <gazette.pdf> [--text FILE] [--out DIR]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import extract as ex  # noqa: E402

AFRIKAANS_FIRST, AFRIKAANS_LAST = 421, 710
CODE = r"\d{1,6}[A-Za-z]?"


def dec(raw: str | None) -> Decimal | None:
    n = ex.norm(raw) if raw else None
    if n is None:
        return None
    try:
        return Decimal(n)
    except InvalidOperation:
        return None


def figures(cells: list[ex.Cell]) -> list[Decimal]:
    out = [dec(c.raw) for c in cells]
    return sorted(x for x in out if x is not None and x != 0)


def af_norm(line: str) -> str:
    """Undo three printing habits of the Afrikaans copy, keeping column positions.

    It prints a three-decimal units figure with a space ("2 000" for 2.000),
    puts a space before the anaesthetic time marker ("5 000 T"), and in one
    dental table prints the spreadsheet error "#VALUE!" in the last column.
    """
    line = line.replace("#VALUE!", "      -")
    line = re.sub(r"(?<![\d,.])(\d{1,3}) (\d{3})(?![\d,.]| \d{3})", r"\1.\2", line)
    line = re.sub(r"(\d) (TM|T|M)(?=\s|$)", r"\1\2 ", line)
    return line


def afrikaans_rows(pages: list[str]) -> list[tuple[int, str, list[Decimal]]]:
    """(pdf page, code, figures) for every coded line, cells on following lines included."""
    wide = re.compile(r"^(?P<ind>\s*)(?P<code>" + CODE + r")\s{2,}(?P<rest>\S.*)$")
    tight = re.compile(r"^(?P<ind>\s*)(?P<code>" + CODE + r") (?P<rest>\S.*)$")
    rows: list[list] = []
    for p in range(AFRIKAANS_FIRST, AFRIKAANS_LAST + 1):
        lines = [af_norm(ln) for ln in pages[p - 1].split("\n")]
        live = [ln for ln in lines if ln.strip() and not ex.NOISE.search(ln)]
        r_starts = [c.start for ln in live for c in ex.tail_cells(ln, None)[0] if c.rand]
        unit_cols = [m.start() for ln in live for m in re.finditer(r"(?i)\beenhede\b", ln)]
        zone = None
        if unit_cols:
            zone = min(unit_cols) - 10
        elif r_starts:
            zone = min(r_starts) - 24
        cur = None
        for i, line in enumerate(lines):
            if not line.strip() or ex.NOISE.search(line):
                continue
            cells, rest = ex.tail_cells(line, zone)
            m = wide.match(line)
            if m and not re.search(r"[A-Za-z]{2}", m.group("rest")) and m.start("code") > 40:
                m = None
            if not m:
                t = tight.match(line)
                if t and cells and len(t.group("code")) >= 2:
                    m = t
            if m:
                cells = [c for c in cells if c.start >= m.start("rest")]
                cur = [p, m.group("code"), list(cells), i]
                rows.append(cur)
            elif cells and cur and cur[0] == p and i - cur[3] <= 8:
                cur[2] += cells
                cur[3] = i
    return [(p, code, figures(cells)) for p, code, cells, _ in rows]


def english_rows(rows: list[ex.Row]) -> list[tuple[ex.Row, list[Decimal]]]:
    out = []
    for r in rows:
        if r.section in ("orthotics_prosthetics", "pharmacy") or not r.code:
            continue
        out.append((r, figures(r.cells)))
    return out


def amounts_on_pages(pages: list[str], first: int, last: int) -> list[Decimal]:
    out = []
    for p in range(first, last + 1):
        for line in pages[p - 1].split("\n"):
            if ex.NOISE.search(line):
                continue
            m = re.search(r"(?<![A-Za-z0-9])R\s*(\d{1,3}(?: \d{3})*[.,]\d{2})\s*$", line)
            if m:
                out.append(Decimal(ex.norm(m.group(1))))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent)
    ap.add_argument("--text", type=Path)
    args = ap.parse_args(argv)
    text = args.text.read_text() if args.text else ex.pdf_text(args.pdf)
    pages = text.split("\f")
    rows, _ = ex.parse(pages)
    eng = english_rows(rows)
    afr = afrikaans_rows(pages)

    sm = difflib.SequenceMatcher(None, [r.code for r, _ in eng], [c for _, c, _ in afr],
                                 autojunk=False)
    agree = differ = 0
    differences, unmatched = [], []
    matched = set()
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            r, ef = eng[a + k]
            ap_, _, af = afr[b + k]
            matched.add(a + k)
            if not ef and not af:
                continue
            if ef == af:
                agree += 1
            else:
                differ += 1
                differences.append({
                    "discipline": r.section, "code": r.code, "english_pdf_page": r.pdf_page,
                    "afrikaans_pdf_page": ap_, "english": [str(x) for x in ef],
                    "afrikaans": [str(x) for x in af],
                    "description": r.description[:90]})
    for n, (r, ef) in enumerate(eng):
        if n not in matched and ef:
            unmatched.append({"discipline": r.section, "code": r.code,
                              "english_pdf_page": r.pdf_page, "english": [str(x) for x in ef]})

    # orthotics and pharmacy: codes do not parse the same way, so compare the
    # run of rand amounts page range against page range
    spans = {}
    for name, e_first, e_last, marker in (
            ("orthotics_prosthetics", 291, 323, None), ("pharmacy", 326, 326, None)):
        e_vals = amounts_on_pages(pages, e_first, e_last)
        spans[name] = {"english_amounts": len(e_vals)}
        # find the same run in the Afrikaans pages
        a_all = [(p, v) for p in range(AFRIKAANS_FIRST, AFRIKAANS_LAST + 1)
                 for v in amounts_on_pages(pages, p, p)]
        vals = [v for _, v in a_all]
        m2 = difflib.SequenceMatcher(None, e_vals, vals, autojunk=False)
        same = sum(size for _, _, size in m2.get_matching_blocks())
        spans[name]["found_in_same_order_in_afrikaans"] = same
        spans[name]["not_found"] = len(e_vals) - same

    result = {"coded_rows_compared": agree + differ, "agree": agree, "differ": differ,
              "english_rows_with_figures_not_matched": len(unmatched),
              "amount_runs": spans, "differences": differences, "unmatched": unmatched}
    (args.out / "crosscheck_afrikaans.json").write_text(
        json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    print({k: v for k, v in result.items() if k not in ("differences", "unmatched")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
