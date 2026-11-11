# RAF tariff extract

The Road Accident Fund Tariff 2021/2022, read out of the gazette that published it.

- Source: Government Gazette No. 46747, Regulation Gazette No. 11473, 19 August 2022.
- The English tariff is PDF pages 5 to 413. Tariff page n is PDF page n + 3.
- Extracted on 11 November 2026.

**Status.** The gazette cover states that this tariff is interdicted. This folder
records what the gazette prints. It does not say which price list a claim should
be paid against, and nothing here is loaded into RIE. A test fails if the
reference loader starts reading this folder.

## Files

| File | What it holds |
|---|---|
| `raf_tariff_2021_22.json` | Every coded row, with its text, page and figures by column. One row per line. |
| `raf_tariff_2021_22_prices.csv` | One line per figure: discipline, code, column, units, rand value, both as numbers and as printed. |
| `extract.py` | Produces the two files above from the gazette PDF. |
| `crosscheck.py` | Compares the extract with the Afrikaans copy in the same gazette. |
| `crosscheck_afrikaans.json` | Result of that comparison. |
| `extract_diagnostics.json` | Lines the extractor could not place, and rand amounts in the text that sit in no row. |

To run it again (needs `pdftotext` from poppler):

    python3 db/raf_tariff/extract.py <gazette.pdf>
    python3 db/raf_tariff/crosscheck.py <gazette.pdf>
    RAF_GAZETTE_PDF=<gazette.pdf> python3 -m pytest tests/test_raf_tariff_extract.py

With `RAF_GAZETTE_PDF` set, the last test extracts from the PDF again and
requires the result to match the stored files byte for byte.

## What was extracted

| No | Discipline | Tariff pages | Coded rows | Rows with a figure | Figures by column |
|---|---|---|---|---|---|
| 1 | Ambulance Services | 3 to 6 | 42 | 27 | 27 |
| 2 | Biokinetics | 7 to 7 | 35 | 26 | 26 |
| 3 | Chinese Medicine and Acupuncture | 8 to 8 | 21 | 14 | 14 |
| 4 | Chiropractors | 9 to 9 | 25 | 13 | 13 |
| 5 | Clinical Pathology | 10 to 25 | 678 | 655 | 1,304 |
| 6 | Clinical Technologists | 26 to 28 | 107 | 104 | 104 |
| 7 | Dental Practitioners | 29 to 48 | 701 | 676 | 1,328 |
| 8 | Dental Technicians | 49 to 54 | 256 | 249 | 207 |
| 9 | Dental Therapists | 55 to 57 | 54 | 46 | 46 |
| 10 | Dieticians | 58 to 59 | 33 | 24 | 24 |
| 11 | Genetic Counsellors | 60 to 61 | 32 | 9 | 9 |
| 12 | Hearing Aid Acousticians | 62 to 62 | 18 | 12 | 12 |
| 13 | Homeopathy | 63 to 65 | 23 | 12 | 12 |
| 14 | Hospice | 66 to 66 | 3 | 2 | 2 |
| 15 | Medical Practitioners | 67 to 278 | 2,685 | 2,418 | 6,587 |
| 16 | Mental Health Care Facilities | 279 to 279 | 8 | 6 | 6 |
| 17 | Occupational Therapy and Art Therapy | 280 to 283 | 115 | 43 | 72 |
| 18 | Optometry | 284 to 286 | 95 | 77 | 77 |
| 19 | Orthoptists | 287 to 287 | 5 | 4 | 4 |
| 20 | Orthotists and Prosthetists | 288 to 320 | 1,601 | 1,588 | 1,588 |
| 21 | Osteopathy | 321 to 322 | 42 | 36 | 36 |
| 22 | Pharmacy | 323 to 323 | 26 | 19 | 19 |
| 23 | Physiotherapists | 324 to 328 | 95 | 60 | 60 |
| 24 | Podiatry | 329 to 333 | 63 | 56 | 56 |
| 25 | Private Hospitals | 334 to 349 | 163 | 155 | 398 |
| 26 | Private Nursing | 350 to 354 | 61 | 47 | 47 |
| 27 | Private Sub-Acute Facilities | 355 to 356 | 15 | 13 | 13 |
| 28 | Psychology | 357 to 359 | 28 | 25 | 25 |
| 29 | Psychometry | 360 to 360 | 13 | 13 | 13 |
| 30 | Radiography | 361 to 364 | 125 | 107 | 107 |
| 31 | Radiology | 365 to 398 | 1,083 | 1,068 | 1,058 |
| 32 | Registered Counsellors | 399 to 399 | 22 | 22 | 22 |
| 33 | Rehabilitation Hospitals | 400 to 400 | 6 | 5 | 5 |
| 34 | Social Workers | 401 to 402 | 32 | 25 | 25 |
| 35 | Speech Therapy and Audiology | 403 to 406 | 103 | 99 | 101 |
| 36 | Tissue Transportation | 407 to 407 | 6 | 5 | 5 |
| 37 | Unattached Operating Theatre Units and Day Clinics | 408 to 410 | 33 | 32 | 32 |
| | **Total** | 3 to 410 | **8,453** | **7,792** | **13,484** |

"Coded rows" includes rules, modifiers and headings that carry a number in the
code column. "Rows with a figure" are the rows that print at least one units or
rand figure. Of those, 73 print no item code: 58 prosthetic component rows that
carry only the second code, and 15 lines priced with no code at all.

Things to know when using the figures:

- **Medical Practitioners prints units only.** There are no rand values in that
  section. The gazette gives three conversion factors on tariff page 67:
  consultation 33.69, procedural 16.05, psychiatrists 40.30. They are recorded
  in the JSON `meta` and applied to nothing. Which factor applies to which code
  is not decided here.
- **Columns are named as printed.** Private Hospitals has three columns headed
  55700, 55800 and 57700; they are kept as `column_55700` and so on, with no
  interpretation. Dental Practitioners has five practice-type columns.
- **Anaesthetic units carry letters** (`T` or `TM`) in the gazette. The number
  is in `units` and the letters in `suffix`.
- **Dashes and stars** are kept in the "as printed" fields and have no number.
- **Orthotists and Prosthetists** rows have two codes. `code` is the item code
  (for example `AF0010`) and `alt_code` the second code (`A10010`).
- **Descriptions** include any note printed directly under the row.

## How it was checked

| Check | Result |
|---|---|
| Every rand amount in the English text is in a row | 33 are not. All 33 are amounts quoted inside rules (such as "maximum of R26.00") or product codes that look like amounts (such as "R1.40"). Listed in the diagnostics file. |
| Figures agree with the Afrikaans copy, row by row | 5,882 coded rows compared: 5,877 agree, 5 differ. |
| Orthotics and pharmacy amounts found in the same order in the Afrikaans copy | 1,588 of 1,588 and 19 of 19. |
| Rows compared with the printed page by eye | Eight pages, all correct: tariff pages 4, 14, 43, 145, 278, 296, 335 and 373. |
| Fresh extraction from the PDF reproduces the stored files | Yes. |

The five rows that differ from the Afrikaans copy are rows the two copies lay
out differently (a value printed on the line above its code, or a row with no
code). The figures are the same: Medical Practitioners 0545 and 2880, Radiology
39920, Speech Therapy and Audiology 1615 and 1625.

The Afrikaans copy has printing habits of its own, which the comparison allows
for: it prints a three-decimal units figure with a space ("2 000" for 2.000),
and one dental table prints the spreadsheet error "#VALUE!" in its last column.

## Flags on rows

| Flag | Rows | Meaning |
|---|---|---|
| `no_item_code_printed` | 58 | Prosthetic component row with only the second code. `follows_code` gives the item code above it. |
| `code_irregular_as_printed` | 52 | Orthotics code that does not fit the pattern, for example `JIR!J??3` or `AB0225` where the series runs `A80223`, `A80225`. The gazette prints them this way. They are not corrected. |
| `cells_on_continuation_line` | 28 | Part of the row's figures is printed on a wrapped line. |
| `columns_by_order_no_header_on_page` | 16 | Occupational Therapy, tariff page 278: the page has no column header, and the row fills both columns. |
| `no_code_printed` | 15 | A priced line with no code: 11 air ambulance rates, 3 prosthetic components, and one nuclear medicine study on tariff page 373. |
| `columns_from_full_rows_on_page` | 6 | Same page: a single figure, placed by lining it up with the full rows. Checked by eye. |
| `value_on_preceding_line` | 4 | Pharmacy: the value is printed on the line above the code. |
| `cells_on_preceding_line` | 3 | The same, in two other sections. |

## What the gazette itself gets wrong or leaves odd

These are in the source. They are reproduced, not fixed.

- 52 orthotics codes are garbled in print (see the flag above).
- One nuclear medicine row on tariff page 373 has no code. It sits between
  39920 and 39930.
- 18 rows have a rand-per-unit rate that no other row in their section shares,
  which may be misprints in the source. Both language copies agree on them.
  Eleven are in Clinical Pathology (3716, 3754, 3768, 3769, 3959, 3960, 3961,
  3962, 3980, 4429, 4552). The others: Chinese Medicine 1110, Chiropractors 301,
  Dental Technicians 9391, Genetic Counsellors 205, Podiatry 201, Registered
  Counsellors 490, Social Workers 300.
- Tissue Transportation prints 0 for every item.

## What was not checked

- Column placement was confirmed by eye on eight pages only. The Afrikaans
  comparison confirms the figures on a row, not which column each sits in.
- Descriptions were not compared word for word with the print.
- Rules, notes and annexures that carry no code are not in the extract.
- Whether a code is still in use, and what each discipline's units are worth
  where no rand value is printed, are outside this extract.
