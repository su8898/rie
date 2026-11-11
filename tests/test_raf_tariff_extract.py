"""The RAF tariff extract (db/raf_tariff).

Three kinds of test:
- the parser on small made-up pages, so its rules are pinned down;
- the stored extract against rows that were read off the printed gazette pages
  by eye when the extract was made;
- if RAF_GAZETTE_PDF points at the gazette, a fresh extraction must reproduce
  the stored files exactly.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent / "db" / "raf_tariff"
sys.path.insert(0, str(HERE))
import crosscheck  # noqa: E402
import extract  # noqa: E402


# ---------------------------------------------------------------- the parser

def cells(line, zone=None):
    return [(c.raw, c.rand, c.suffix) for c in extract.tail_cells(line, zone)[0]]


def test_units_and_value_are_read_from_the_end_of_a_line():
    assert cells("  301   Consultation 5-10 minutes        7.5 R     184.08") == [
        ("7.5", False, ""), ("184.08", True, "")]
    assert cells("  14410   MR of the mandible   98.640 R 13 844.60") == [
        ("98.640", False, ""), ("13 844.60", True, "")]


def test_a_number_inside_the_description_is_not_a_cell():
    line = "  109   Each additional 15 mins. A maximum of four instances"
    assert cells(line) == []
    assert cells("  1100   Pure Tone Audiogram (3273)        15 R 288.03") == [
        ("15", False, ""), ("288.03", True, "")]


def test_anaesthetic_markers_dashes_and_stars_are_kept_as_printed():
    assert cells("  0997  Mandible   302.00     241.60     3.00TM") == [
        ("302.00", False, ""), ("241.60", False, ""), ("3.00", False, "TM")]
    assert cells("  8303  Pulp cap   R  205.15   R   -   R   -") == [
        ("205.15", True, ""), ("-", True, ""), ("-", True, "")]
    assert cells("  0996  Open reduction          *          *") == [
        ("*", False, ""), ("*", False, "")]


def test_a_practice_type_number_is_not_a_quantity():
    assert cells("                      082") == []


def test_decimal_commas_and_thousands_spaces_are_normalised():
    assert extract.norm("1 404,46") == "1404.46"
    assert extract.norm("10,000") == "10.000"
    assert extract.norm("-") is None


PAGE = """
                                   Road Accident Fund Tariff 2021/2022
  Code   Description                          UNITS      VALUE      UNITS      VALUE
  3740   Factors V and VII                     7.20 R   146.20       4.80
  3742   Coagulation factor assay              4.50                  3.00
  3867   Miscellaneous (body fluids,           4.90 R    99.42
         scrapings, etc.)                                            3.30
  3999   By arrangement
"""


def section(page, opts, key="t"):
    rows, loose = extract.parse_section(["", page], key, 2, 2, opts)
    return {r.code: r for r in rows}, rows, loose


def test_columns_come_from_the_header_positions():
    by_code, _, _ = section(PAGE, {"groups": ["pathologist", "other"]})
    assert by_code["3740"].prices == [
        {"group": "pathologist", "units": "7.20", "units_raw": "7.20",
         "value": "146.20", "value_raw": "146.20"},
        {"group": "other", "units": "4.80", "units_raw": "4.80"}]
    assert [p["group"] for p in by_code["3742"].prices] == ["pathologist", "other"]
    assert by_code["3999"].prices == []


def test_a_figure_on_the_wrapped_line_joins_its_row():
    by_code, _, _ = section(PAGE, {"groups": ["pathologist", "other"]})
    row = by_code["3867"]
    assert {p["group"]: p.get("units") for p in row.prices} == {
        "pathologist": "4.90", "other": "3.30"}
    assert "cells_on_continuation_line" in row.flags
    assert row.description.endswith("scrapings, etc.)")


def test_a_priced_line_without_a_code_is_kept_and_flagged():
    page = """
  39920   Infection localisation planar, static              18.040 R  2 492.97
          Infection localisation planar, static,             31.450 R  4 346.14
          multiple studies
  39930   Infection localisation planar, static and SPECT    31.450 R  4 346.14
"""
    _, rows, _ = section(page, {})
    assert [r.code for r in rows] == ["39920", "", "39930"]
    loose = rows[1]
    assert loose.flags == ["no_code_printed"] and loose.follows_code == "39920"
    assert loose.prices[0]["value"] == "4346.14"
    assert loose.description.endswith("multiple studies")


def test_a_value_printed_above_its_code_line_joins_that_code():
    page = """
  1615   Eye Visualization - binocular                       35 R 635.71
         Oculo-motor tests using electro-nystagmography.        R 516.69
  1620   Cannot be used with item 1625.                      25
"""
    by_code, rows, _ = section(page, {})
    assert [r.code for r in rows] == ["1615", "1620"]
    assert by_code["1620"].prices == [{"group": "standard", "value": "516.69",
                                       "value_raw": "516.69", "units": "25",
                                       "units_raw": "25"}]
    assert by_code["1615"].prices[0]["value"] == "635.71"


def test_a_heading_ruled_with_empty_cells_is_not_a_price():
    page = """
  8303   Pulp cap - indirect       R   205.15    R     -
         PULPOTOMY                 R        -    R     -
  8307   Pulp amputation           R   200.93    R     -
"""
    _, rows, _ = section(page, {})
    assert [r.code for r in rows] == ["8303", "8307"]


def test_five_dental_columns_are_taken_in_order():
    page = """
   Tariff                                                Orthodontics
   Code                                                      (64)      (92)     (94)
                                    (54)         (62)
   8901   Consultation - MFOS          0    R   319.83          0         0        0
"""
    opts = {"groups": ["a", "b", "c", "d", "e"],
            "tokens": ["(54)", "(62)", "(64)", "(92)", "(94)"]}
    by_code, _, _ = section(page, opts)
    assert [(p["group"], p["value"]) for p in by_code["8901"].prices] == [
        ("a", "0"), ("b", "319.83"), ("c", "0"), ("d", "0"), ("e", "0")]


def test_afrikaans_printing_habits_are_undone_for_the_comparison():
    assert crosscheck.af_norm("  9311   Snoei    2 000 R   31,00").split() == [
        "9311", "Snoei", "2.000", "R", "31,00"]
    assert "5.000T" in crosscheck.af_norm("  3214  Rekonstruksie  255,00  204.00   5 000 T")
    # a real rand amount keeps its thousands space
    assert "R 1 404,46" in crosscheck.af_norm("  950  Saalfooi   R 1 404,46")


# ------------------------------------------------------- the stored extract

@pytest.fixture(scope="module")
def stored():
    return json.loads((HERE / "raf_tariff_2021_22.json").read_text())


@pytest.fixture(scope="module")
def rows(stored):
    return stored["rows"]


def find(rows, discipline, code, page=None):
    hits = [r for r in rows if r["discipline"] == discipline and r["code"] == code
            and (page is None or r["pdf_page"] == page)]
    assert len(hits) == 1, (discipline, code, len(hits))
    return hits[0]


def prices(row):
    return {p["group"]: (p.get("units"), p.get("value")) for p in row["prices"]}


def test_the_extract_says_what_it_is(stored):
    meta = stored["meta"]
    assert "46747" in meta["source"] and "interdicted" in meta["status_note"]
    assert meta["medical_practitioner_conversion_factors"] == {
        "consultation": "33.69", "procedural": "16.05", "psychiatrists": "40.30",
        "pdf_page": 70}


def test_every_discipline_is_present_with_the_expected_row_counts(rows):
    counts = Counter(r["discipline"] for r in rows)
    assert len(counts) == 37 == len(extract.SECTIONS)
    assert len(rows) == 8453
    assert sum(1 for r in rows if r["kind"] == "priced") == 7792
    assert counts["medical_practitioners"] == 2685
    assert counts["orthotics_prosthetics"] == 1601
    assert counts["radiology"] == 1083
    assert counts["dental_practitioners"] == 701
    assert counts["clinical_pathology"] == 678


def test_every_figure_is_a_plain_number(rows):
    for r in rows:
        for p in r["prices"]:
            for kind in ("units", "value"):
                if p.get(kind) is not None:
                    assert Decimal(p[kind]) >= 0, (r["discipline"], r["code"], p)


def test_medical_practitioners_prints_units_and_no_rand_values(rows):
    med = [r for r in rows if r["discipline"] == "medical_practitioners"]
    assert all("value" not in p for r in med for p in r["prices"])
    assert prices(find(rows, "medical_practitioners", "0190")) == {
        "specialist": ("15.00", None), "general_practitioner": ("15.00", None)}


# Rows below were compared with the printed page when the extract was made.

def test_medical_practitioners_page_145(rows):
    r = find(rows, "medical_practitioners", "0997")
    assert prices(r) == {"specialist": ("302.00", None),
                         "general_practitioner": ("241.60", None),
                         "anaesthesia": ("3.00", None)}
    assert r["prices"][2]["suffix"] == "TM"
    star = find(rows, "medical_practitioners", "0996")
    assert [p["units_raw"] for p in star["prices"]] == ["*", "*"]


def test_clinical_pathology_page_14(rows):
    assert prices(find(rows, "clinical_pathology", "3955")) == {
        "pathologist": ("2.25", "45.47"), "other_specialist_or_gp": ("1.50", None)}
    assert prices(find(rows, "clinical_pathology", "3936")) == {
        "pathologist": ("75.00", "1524.50"), "other_specialist_or_gp": ("50.00", None)}


def test_dental_page_43_including_the_wrapped_zero_cells(rows):
    for code in ("9068", "9073", "9080"):
        assert [p["value"] for p in find(rows, "dental_practitioners", code)["prices"]] == [
            "2983.36", "4474.99", "0", "0", "0"]


def test_occupational_therapy_page_278_has_no_header_of_its_own(rows):
    assert prices(find(rows, "occupational_art_therapy", "431")) == {
        "occupational_therapy_066": (None, "1456.92"), "art_therapy_067": (None, "1061.28")}
    # printed under Code 066 only
    assert prices(find(rows, "occupational_art_therapy", "417")) == {
        "occupational_therapy_066": (None, "1942.05")}


def test_private_hospitals_page_335_columns(rows):
    assert prices(find(rows, "private_hospitals", "7", 338)) == {
        "column_55700": (None, "1008.02"), "column_55800": (None, "1008.47"),
        "column_57700": (None, "861.88")}
    assert prices(find(rows, "private_hospitals", "14", 338)) == {
        "column_57700": (None, "379.76")}


def test_radiology_page_373(rows):
    assert prices(find(rows, "radiology", "34100")) == {"radiology": ("10.440", "1465.14")}
    assert prices(find(rows, "radiology", "39900")) == {
        "nuclear_medicine": ("20.740", "2866.24")}
    loose = [r for r in rows if r["discipline"] == "radiology" and not r["code"]]
    assert len(loose) == 1 and loose[0]["follows_code"] == "39920"
    assert prices(loose[0]) == {"nuclear_medicine": ("31.450", "4346.14")}


def test_orthotics_page_296_keeps_codes_as_printed(rows):
    r = find(rows, "orthotics_prosthetics", "FCW217")
    assert (r["alt_code"], r["category"], r["unit_of_issue"]) == ("A80217", "C2.10", "ea")
    assert prices(r) == {"standard": (None, "234.96")}
    odd = find(rows, "orthotics_prosthetics", "FCW223")
    assert odd["alt_code"] == "JIR!J??3" and "code_irregular_as_printed" in odd["flags"]


def test_ambulance_page_4(rows):
    assert prices(find(rows, "ambulance", "100")) == {
        "ems_primary_response": (None, "2004.06")}
    assert prices(find(rows, "ambulance", "130")) == {
        "ems_primary_response": (None, "11.69")}


def test_pharmacy_values_that_sit_above_their_code_line(rows):
    r = find(rows, "pharmacy", "4")
    assert r["description"] == "Preparation of an intravenous admixture or parenteral solution"
    assert prices(r) == {"standard": (None, "205.82")}
    assert find(rows, "pharmacy", "28")["description"] == "Pharmacist Initiated Therapy (PIT)"


def test_the_csv_carries_one_line_per_price_point(rows):
    with (HERE / "raf_tariff_2021_22_prices.csv").open(newline="") as fh:
        lines = list(csv.DictReader(fh))
    assert len(lines) == sum(len(r["prices"]) for r in rows)
    hit = [ln for ln in lines if ln["discipline"] == "hospice" and ln["code"] == "950"]
    assert hit[0]["value_rand"] == "1404.46" and hit[0]["value_printed"] == "1 404.46"


def test_the_afrikaans_copy_agrees():
    res = json.loads((HERE / "crosscheck_afrikaans.json").read_text())
    assert res["coded_rows_compared"] == 5882
    assert res["agree"] == 5877 and res["differ"] == 5
    assert res["english_rows_with_figures_not_matched"] == 0
    for run in res["amount_runs"].values():
        assert run["not_found"] == 0
    # the five are rows the Afrikaans copy lays out differently, not different figures
    assert {(d["discipline"], d["code"]) for d in res["differences"]} == {
        ("medical_practitioners", "0545"), ("medical_practitioners", "2880"),
        ("radiology", "39920"), ("speech_therapy_audiology", "1615"),
        ("speech_therapy_audiology", "1625")}


def test_the_extract_is_not_wired_into_the_reference_loader():
    """Loading it is a decision for the Fund's price-list question, not a side effect."""
    loader = (HERE.parent / "load_reference.py").read_text()
    assert "raf_tariff" not in loader


@pytest.mark.skipif(not os.environ.get("RAF_GAZETTE_PDF"),
                    reason="set RAF_GAZETTE_PDF to the gazette PDF to re-run the extraction")
def test_a_fresh_extraction_reproduces_the_stored_files(tmp_path):
    assert extract.main([os.environ["RAF_GAZETTE_PDF"], "--out", str(tmp_path)]) == 0
    for name in ("raf_tariff_2021_22.json", "raf_tariff_2021_22_prices.csv"):
        assert (tmp_path / name).read_bytes() == (HERE / name).read_bytes(), name
