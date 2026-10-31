import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from app.models import CanonicalInvoice, FindingKind, Invoice
from app.rules import duplicates, valid_tax_id, validate
from ops import make_invoices

TODAY = date(2026, 10, 30)
TAX_LINES = [{"rate": "21", "base": "60.00", "amount": "12.60"}, {"rate": "10", "base": "40.00", "amount": "4.00"}]
BASE: dict[str, object] = {"vendor_name": "Aceites del Bajo Aragón, S.L.", "vendor_tax_id": "es b-36455681"}
BASE |= {"invoice_number": "F2026-0101", "issue_date": "2026-03-02", "due_date": "2026-04-01", "subtotal": "100.00"}
BASE |= {"tax_lines": TAX_LINES, "irpf": {"rate": "15", "amount": "15.00"}, "total": "101.60", "currency": "EUR"}
BASE |= {"line_items": [{"description": "Olive oil", "amount": "60.00"}, {"amount": "40.00"}]}
WRONG_RATE = [{"rate": "18", "base": "60.00", "amount": "10.80"}, TAX_LINES[1]]
CASES = [
    ({}, None, {}),
    ({"total": "101.61"}, None, {}),
    ({"issue_date": "2026-10-30", "due_date": "2026-10-30"}, None, {}),
    ({"invoice_number": None}, "missing_field", {"field": "invoice_number"}),
    ({"vendor_name": "  "}, "missing_field", {"field": "vendor_name"}),
    ({"vendor_tax_id": "-"}, "missing_field", {"field": "vendor_tax_id"}),
    ({"tax_lines": []}, "missing_field", {"field": "tax_lines"}),
    ({"line_items": [{"amount": "60.00"}, {"amount": "41.00"}]}, "lines_mismatch", {"lines": "101.00"}),
    ({"tax_lines": [{**TAX_LINES[0], "amount": "12.70"}, TAX_LINES[1]], "total": "101.70"}, "tax_line_mismatch", {}),
    ({"tax_lines": WRONG_RATE, "total": "99.80"}, "invalid_vat_rate", {"rate": "18"}),
    ({"irpf": {"rate": "12", "amount": "12.00"}, "total": "104.60"}, "invalid_irpf_rate", {"rate": "12"}),
    ({"total": "101.62"}, "total_mismatch", {"expected": "101.60", "total": "101.62"}),
    ({"vendor_tax_id": "B36455682"}, "invalid_tax_id", {"tax_id": "B36455682"}),
    ({"issue_date": "2026-10-31", "due_date": None}, "invalid_date", {"issue_date": "2026-10-31"}),
    ({"due_date": "2026-03-01"}, "invalid_date", {"due_date": "2026-03-01"}),
]


def invoice(**changes: object) -> CanonicalInvoice:
    return CanonicalInvoice.model_validate(BASE | changes)


def assert_planted(records: list[tuple[Invoice, list[str], str | None]]) -> None:
    seen: list[Invoice] = []
    for record, expected, duplicate_of in records:
        found = validate(record.data, TODAY) + duplicates(record, seen)
        assert [(item.kind, item.duplicate_of) for item in found] == [(kind, duplicate_of) for kind in expected], record
        seen.append(record)


@pytest.mark.parametrize(("changes", "kind", "evidence"), CASES)
def test_rules_type_each_failure_with_its_evidence(
    changes: dict[str, object], kind: str | None, evidence: dict[str, str]
) -> None:
    found = validate(invoice(**changes), TODAY)
    assert [(item.kind, item.evidence.items() >= evidence.items()) for item in found] == [(kind, True)] * bool(kind)


def test_rules_check_nif_cif_and_eu_vat() -> None:
    ids = [vendor["tax_id"] for vendor in make_invoices.VENDORS.values()] + ["X1234567L", "IE1+00000B"]
    assert {tax_id[:2] for tax_id in ids} >= {"PT", "FR", "IT", "DE"} and all(valid_tax_id(tax_id) for tax_id in ids)
    assert not any(valid_tax_id(f"{tax_id[:-2]}{(int(tax_id[-2]) + 1) % 10}{tax_id[-1]}") for tax_id in ids)
    assert not valid_tax_id("GB123456789") and invoice(vendor_tax_id=" ie1+00000b").vendor_tax_id == "IE1+00000B"


def test_duplicates_exact_and_probable() -> None:
    stored = Invoice(id="stored", sha256="aa", data=invoice())
    cases = [
        ("aa", {"invoice_number": "F2026-0999"}, "exact_duplicate"),
        ("bb", {"vendor_tax_id": "ESB36455681", "invoice_number": " f2026-0101"}, "exact_duplicate"),
        ("bb", {"invoice_number": "F2026-0102", "issue_date": "2026-03-09"}, "probable_duplicate"),
        ("bb", {"invoice_number": "F2026-0102", "issue_date": "2026-02-23"}, "probable_duplicate"),
        ("bb", {"invoice_number": "F2026-0102", "issue_date": "2026-03-10"}, None),
        ("bb", {"invoice_number": "F2026-0102", "total": "101.62"}, None),
        ("bb", {"vendor_tax_id": "A16229486"}, None),
    ]
    for sha256, changes, kind in cases:
        found = duplicates(Invoice(id="new", sha256=sha256, data=invoice(**changes)), [stored])
        assert [(item.kind, item.duplicate_of) for item in found] == [(kind, "stored")] * bool(kind), changes
    blank = [Invoice(id=name, sha256=name, data=invoice(vendor_tax_id=name)) for name in ("", "-")]
    assert duplicates(stored, [stored]) == [] and duplicates(blank[0], blank[1:]) == []


def test_rules_on_the_synthetic_set(tmp_path: Path) -> None:
    make_invoices.write(2026, tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "ground_truth.jsonl").read_text("utf-8").splitlines()]
    digest = [hashlib.sha256((tmp_path / "invoices" / row["file"]).read_bytes()).hexdigest() for row in rows]
    records = [
        Invoice(id=row["file"], sha256=sha256, data=row["invoice"]) for row, sha256 in zip(rows, digest, strict=True)
    ]
    assert_planted([(record, row["expected"], row["duplicate_of"]) for record, row in zip(records, rows, strict=True)])
    planted = Counter(kind for row in rows for kind in row["expected"])
    twins = {"missing_field": 2, "total_mismatch": 2, "exact_duplicate": 4, "probable_duplicate": 4}
    assert planted == Counter({kind: 1 for kind in FindingKind} | twins) and len(rows) == 60 and len(set(digest)) == 58
    assert sum(bool(row["canary"]) for row in rows) == 4 and sum(bool(row["scan"]) for row in rows) == 5
    assert {row["layout"] for row in rows} == set(range(5))


def test_planted_findings_hold_for_any_seed() -> None:
    for seed in range(200):
        samples = make_invoices.build(seed)
        assert_planted(
            [(Invoice(id=s.file, sha256=s.file, data=s.invoice), s.expected, s.duplicate_of) for s in samples]
        )
