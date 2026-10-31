import argparse
import dataclasses
import json
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import reportlab
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from app.models import CanonicalInvoice, LineItem, TaxLine, Withholding

DATA = Path(__file__).resolve().parent.parent / "data"
VENDORS: dict[str, dict[str, Any]] = {v["tax_id"]: v for v in json.loads((DATA / "vendors.json").read_text("utf-8"))}
CATALOG: dict[str, list[dict[str, Any]]] = json.loads((DATA / "catalog.json").read_text("utf-8"))
TEMPLATES: dict[str, Any] = json.loads((DATA / "templates.json").read_text("utf-8"))
FONTS = Path(reportlab.__file__).parent / "fonts"
ERRORS = ["missing_number", "lines_mismatch", "tax_line_mismatch", "total_mismatch", "invalid_vat_rate"]
ERRORS += ["invalid_irpf_rate", "invalid_tax_id", "invalid_date", "missing_tax_id", "total_mismatch"]
type Op = tuple[float, float, str, float, bool]


@dataclasses.dataclass
class Sample:
    file: str
    vendor: str
    invoice: CanonicalInvoice
    layout: int
    expected: list[str]
    scan: str = ""
    canary: str | None = None
    note: str | None = None
    duplicate_of: str | None = None


def cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), ROUND_HALF_UP)


def number(tax_id: str, issued: date, seq: int) -> str:
    return str(TEMPLATES["numbers"][sum(map(ord, tax_id)) % len(TEMPLATES["numbers"])].format(y=issued.year, n=seq))


def compose(rng: random.Random, vendor: dict[str, Any], seq: int, language: str, error: str) -> CanonicalInvoice:
    products, services, bases, items = CATALOG[vendor["category"]], bool(vendor["irpf"]), dict[Decimal, Decimal](), []
    for product in rng.sample(products, k=rng.randint(1, len(products))):
        quantity = Decimal(1 if services else rng.randint(2, 120))
        price = Decimal(product["price"]) + (Decimal(rng.randrange(20000)) / 100 if services else 0)
        amount = cents(quantity * price)
        items.append(LineItem(description=product[language], quantity=quantity, unit_price=price, amount=amount))
        rate = Decimal(18 if error == "invalid_vat_rate" else product["rate"] if vendor["country"] == "ES" else 0)
        bases[rate] = bases.get(rate, Decimal(0)) + amount
    taxes = [TaxLine(rate=rate, base=base, amount=cents(base * rate / 100)) for rate, base in bases.items()]
    taxes[0].amount += Decimal("0.50") * (error == "tax_line_mismatch")
    subtotal = sum((item.amount for item in items), Decimal(0))
    irpf_rate = Decimal(12 if error == "invalid_irpf_rate" else vendor["irpf"] or 0)
    irpf = Withholding(rate=irpf_rate, amount=cents(subtotal * irpf_rate / 100)) if services else None
    total = subtotal + sum(tax.amount for tax in taxes) - (irpf.amount if irpf else 0) + (error == "total_mismatch")
    items[0].amount += error == "lines_mismatch"
    issued, tax_id = date(2026, 1, 2) + timedelta(days=seq // 7), vendor["tax_id"]
    due = issued + timedelta(days=-10 if error == "invalid_date" else rng.choice((30, 60)))
    tax_ids = {"missing_tax_id": None, "invalid_tax_id": f"{tax_id[:-2]}{(int(tax_id[-2]) + 1) % 10}{tax_id[-1]}"}
    fields = {"vendor_name": vendor["name"], "vendor_tax_id": tax_ids.get(error, tax_id), "iban": vendor["iban"]}
    fields |= {"invoice_number": None if error == "missing_number" else number(tax_id, issued, seq)}
    fields |= {"issue_date": issued, "due_date": due if error == "invalid_date" or rng.random() > 0.2 else None}
    fields |= {"currency": vendor["currency"], "subtotal": subtotal, "tax_lines": taxes, "irpf": irpf, "total": total}
    return CanonicalInvoice.model_validate(fields | {"line_items": items})


def build(seed: int) -> list[Sample]:
    rng, samples = random.Random(seed), list[Sample]()
    for i in range(52):
        error = ERRORS[(i - 2) // 5] if i % 5 == 2 and i < 50 else ""
        pool = [v for v in VENDORS.values() if v["tax_id"] not in {sample.vendor for sample in samples[-3:]}]
        vendor = rng.choice([v for v in pool if v["irpf"] or error != "invalid_irpf_rate"])
        scan, language = {11: "pdf", 23: "jpg", 44: "png"}.get(i, ""), TEMPLATES["layouts"][i % 5][0]
        invoice = compose(rng, vendor, i * 37 + rng.randint(1, 30), language, error)
        expected = ["missing_field" if error.startswith("missing") else error] if error else []
        sample = Sample(f"inv-{i + 1:03d}.{scan or 'pdf'}", vendor["tax_id"], invoice, i % 5, expected, scan)
        if i % 15 == 4:
            sample.canary = f"CANARY-{rng.randbytes(4).hex().upper()}"
            sample.note = TEMPLATES["injections"][i // 15].format(sample.canary)
        samples.append(sample)
    clean = [sample for sample in samples if not (sample.expected or sample.scan or sample.canary)]
    for k, original in enumerate(rng.sample(clean, 8)):
        twin = dataclasses.replace(original, expected=["exact_duplicate"], duplicate_of=original.file)
        twin.scan = ("jpg", "png", "")[min(k, 2)]
        if k >= 4:
            shift, old = timedelta(days=rng.choice((-1, 1)) * rng.randint(1, 7)), original.invoice
            issued, due = (old.issue_date or date.min) + shift, old.due_date and old.due_date + shift
            new = {"invoice_number": number(twin.vendor, issued, 37 * k), "issue_date": issued, "due_date": due}
            twin.invoice, twin.expected = old.model_copy(update=new), ["probable_duplicate"]
        samples.append(dataclasses.replace(twin, file=f"inv-{53 + k:03d}.{twin.scan or 'pdf'}"))
    return samples


def page(sample: Sample) -> list[Op]:
    invoice, vendor, currency = sample.invoice, VENDORS[sample.vendor], sample.invoice.currency or "EUR"
    language, form, swap = TEMPLATES["layouts"][sample.layout]
    label, customer = TEMPLATES["labels"][language], TEMPLATES["customer"]

    def cash(value: Decimal | None) -> str:
        text = "" if value is None else f"{value:,.2f}"
        text = text.translate(str.maketrans(",.", ".,")) if language == "es" else text
        symbol = "€" if currency == "EUR" else currency
        return text and (f"{currency} {text}" if language == "en" else f"{text} {symbol}")

    (vx, vr), (cx, cr) = ((190, True), (20, False)) if swap else ((20, False), (190, True))
    tax = f"{label['tax']}: {invoice.vendor_tax_id}" * bool(invoice.vendor_tax_id)
    ops: list[Op] = [(cx, 22, label["title"], 18, cr), (vx, 32, vendor["name"], 12, vr), (vx, 38, tax, 9, vr)]
    ops += [(vx, 43, vendor["address"], 9, vr), (cx, 55, label["customer"], 9, cr), (cx, 61, customer[0], 10, cr)]
    ops += [(cx, 66, f"{label['tax']}: {customer[1]}", 9, cr), (cx, 71, customer[2], 9, cr)]
    meta = [invoice.invoice_number, *(day and day.strftime(form) for day in (invoice.issue_date, invoice.due_date))]
    shown = [f"{label[key]}: {value}" for key, value in zip(("number", "date", "due"), meta, strict=True) if value]
    ops += [(vx, 55 + 6 * row, text, 10, vr) for row, text in enumerate(shown)]
    rows = [[label["description"], label["quantity"], label["price"], label["amount"]]]
    for item in invoice.line_items:
        rows.append([item.description or "", f"{item.quantity or ''}", cash(item.unit_price), cash(item.amount)])
    for row, cells in enumerate(rows):
        ops += [(x, 86 + 7 * row, cell, 9, x > 20) for x, cell in zip((20, 125, 155, 190), cells, strict=True)]
    totals = [(label["subtotal"], invoice.subtotal)]
    totals += [(f"{label['vat']} {tax.rate} % ({cash(tax.base)})", tax.amount) for tax in invoice.tax_lines]
    totals += [(f"{label['irpf']} {invoice.irpf.rate} %", -invoice.irpf.amount)] if invoice.irpf else []
    for row, (name, value) in enumerate([*totals, (label["total"], invoice.total)]):
        size, y = 12 if row == len(totals) else 10, 100 + 7 * len(invoice.line_items) + 6 * row
        ops += [(100, y, name, size, False), (190, y, cash(value), size, True)]
    ops += [(20, 250, f"{label['iban']}: {invoice.iban}", 9, False)]
    ops += [(20, 258, f"{label['notes']}: {sample.note}" * bool(sample.note), 9, False)]
    return [op for op in ops if op[2]]


def pdf(ops: list[Op], path: Path) -> None:
    canvas = Canvas(str(path), pagesize=A4, invariant=True)
    for x, y, text, size, right in ops:
        canvas.setFont("Helvetica-Bold" if size >= 12 else "Helvetica", size)
        (canvas.drawRightString if right else canvas.drawString)(x * mm, (297 - y) * mm, text)
    canvas.save()


def scan(ops: list[Op], path: Path, rng: random.Random) -> None:
    draw, px = ImageDraw.Draw(image := Image.new("L", (1240, 1754), 255)), 150 / 25.4
    for x, y, text, size, right in ops:
        font = ImageFont.truetype(FONTS / ("VeraBd.ttf" if size >= 12 else "Vera.ttf"), size * 150 / 72)
        draw.text((x * px, y * px), text, 0, font, "rs" if right else "ls")
    image = image.rotate(rng.uniform(-2.5, 2.5), Image.Resampling.BICUBIC, fillcolor=255)
    image = image.filter(ImageFilter.GaussianBlur(0.6))
    noise = Image.frombytes("L", image.size, rng.randbytes(image.width * image.height))
    Image.blend(image, noise, 0.08).save(path, dpi=(150, 150), quality=70, creationDate=None, modDate=None)


def write(seed: int, out: Path) -> list[Sample]:
    samples, rng, folder = build(seed), random.Random(seed), out / "invoices"
    folder.mkdir(parents=True, exist_ok=True)
    for sample in samples:
        if sample.scan:
            scan(page(sample), folder / sample.file, rng)
        else:
            pdf(page(sample), folder / sample.file)
    rows = [{**vars(sample), "invoice": sample.invoice.model_dump(mode="json")} for sample in samples]
    lines = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    (out / "ground_truth.jsonl").write_bytes(lines.encode())
    return samples


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Folium's synthetic invoices and their ground truth.")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", type=Path, default=Path("eval/datasets"))
    args = parser.parse_args()
    print(f"{len(write(args.seed, args.out))} invoices and their ground truth in {args.out}")
