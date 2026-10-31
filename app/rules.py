import unicodedata
from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from decimal import Decimal

from stdnum.es import nif
from stdnum.eu import vat

from app.models import CanonicalInvoice, Finding, Invoice
from app.models import FindingKind as Kind

TOLERANCE = Decimal("0.01")
VAT_RATES = {Decimal(rate) for rate in (21, 10, 4, 0)}
IRPF_RATES = {Decimal(rate) for rate in (7, 15, 19)}
MANDATORY = ("vendor_name", "vendor_tax_id", "invoice_number", "issue_date", "currency", "total")
PROBABLE_WINDOW = timedelta(days=7)


def squash(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", text.casefold()) if char.isalnum())


def match_vendor(invoice: CanonicalInvoice, vendors: Mapping[str, str]) -> str | None:
    if invoice.vendor_tax_id in vendors:
        return invoice.vendor_tax_id
    key = squash(invoice.vendor_name or "")
    return next((tax_id for tax_id, name in vendors.items() if key and squash(name) == key), None)


def valid_tax_id(tax_id: str) -> bool:
    return bool(nif.is_valid(tax_id) or vat.is_valid(tax_id))


def finding(kind: Kind, rule: str, duplicate_of: str | None = None, **evidence: object) -> Finding:
    values = {name: str(value) for name, value in evidence.items()}
    return Finding(kind=kind, rule=rule, evidence=values, duplicate_of=duplicate_of)


def differs(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) > TOLERANCE


def validate(invoice: CanonicalInvoice, today: date) -> list[Finding]:
    issued, due, irpf = invoice.issue_date, invoice.due_date, invoice.irpf
    subtotal, total = invoice.subtotal, invoice.total
    missing = [name for name in MANDATORY if getattr(invoice, name) in (None, "")]
    missing += [] if invoice.tax_lines else ["tax_lines"]
    found = [finding(Kind.missing_field, "mandatory field is present", field=name) for name in missing]
    lines = sum((item.amount for item in invoice.line_items), Decimal(0))
    if invoice.line_items and subtotal is not None and differs(lines, subtotal):
        found.append(
            finding(Kind.lines_mismatch, "lines add up to the subtotal ± 0.01", lines=lines, subtotal=subtotal)
        )
    for tax in invoice.tax_lines:
        if tax.base is not None and differs(tax.base * tax.rate / 100, tax.amount):
            found.append(finding(Kind.tax_line_mismatch, "base * rate / 100 = tax amount ± 0.01", **tax.model_dump()))
        if tax.rate not in VAT_RATES:
            found.append(finding(Kind.invalid_vat_rate, "VAT rate is 21, 10, 4 or 0 %", rate=tax.rate))
    if irpf and irpf.rate not in IRPF_RATES:
        found.append(finding(Kind.invalid_irpf_rate, "IRPF rate is 7, 15 or 19 %", rate=irpf.rate))
    if invoice.tax_lines and subtotal is not None and total is not None:
        expected = subtotal + sum(tax.amount for tax in invoice.tax_lines) - (irpf.amount if irpf else 0)
        if differs(expected, total):
            found.append(
                finding(Kind.total_mismatch, "subtotal + tax - IRPF = total ± 0.01", expected=expected, total=total)
            )
    if invoice.vendor_tax_id and not valid_tax_id(invoice.vendor_tax_id):
        found.append(finding(Kind.invalid_tax_id, "NIF, CIF or EU VAT checksum", tax_id=invoice.vendor_tax_id))
    if issued and issued > today:
        found.append(finding(Kind.invalid_date, "issue date is not in the future", issue_date=issued, today=today))
    if issued and due and due < issued:
        found.append(finding(Kind.invalid_date, "due date is not before issue date", issue_date=issued, due_date=due))
    return found


def number_key(number: str | None) -> str:
    return "".join((number or "").split()).casefold()


def duplicates(invoice: Invoice, others: Iterable[Invoice]) -> list[Finding]:
    mine, number, found = invoice.data, number_key(invoice.data.invoice_number), list[Finding]()
    for other in (other for other in others if other.id != invoice.id):
        theirs = other.data
        vendor = bool(mine.vendor_tax_id) and mine.vendor_tax_id == theirs.vendor_tax_id
        near = mine.issue_date and theirs.issue_date and abs(mine.issue_date - theirs.issue_date) <= PROBABLE_WINDOW
        if other.sha256 == invoice.sha256:
            found.append(finding(Kind.exact_duplicate, "same file", other.id, sha256=invoice.sha256))
        elif vendor and number and number == number_key(theirs.invoice_number):
            rule = "same vendor tax ID and invoice number"
            found.append(finding(Kind.exact_duplicate, rule, other.id, invoice_number=mine.invoice_number))
        elif vendor and near and mine.total is not None and mine.total == theirs.total:
            rule = "same vendor and total, issued within 7 days"
            found.append(finding(Kind.probable_duplicate, rule, other.id, total=mine.total, issue_date=mine.issue_date))
    return found
