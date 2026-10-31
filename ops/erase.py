import argparse
import asyncio
from datetime import UTC, date, datetime

from app.config import clients, settings
from app.models import Invoice
from app.store import Store, scrub
from app.workflow import step

RETENTION_YEARS, PERSONAL = 6, ("name", "tax_id", "address", "iban")


async def erase(store: Store, tax_id: str, by: str, today: date) -> int:
    vendor = await store.read("vendors", tax_id)
    if vendor is None or vendor["kind"] != "sole_trader":
        raise ValueError("erasure applies to a sole trader in the vendor master")
    records = await store.records(tax_id=tax_id)
    if any((item.invoice.data.issue_date or today).year >= today.year - RETENTION_YEARS for item in records):
        raise ValueError("an invoice of this vendor is still within the six-year accounting retention")
    values = {str(vendor[key]) for key in PERSONAL if vendor.get(key)} | {tax_id}
    values |= {value for item in records for value in (item.invoice.data.vendor_name, item.invoice.data.iban) if value}
    for record in records:
        invoice = Invoice.model_validate(scrub(record.invoice.model_dump(mode="json"), values))
        if await store.redact(record, values, step(invoice, "erased", by, fields=",".join(PERSONAL))) is None:
            raise RuntimeError("an invoice changed during the erasure; run it again")
    await store.remove("vendors", tax_id)
    return len(records)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Erase a sole trader's personal data after the retention period.")
    parser.add_argument("tax_id")
    parser.add_argument("--by", required=True, help="who requested and runs the erasure")
    args = parser.parse_args()
    async with clients(settings()) as azure:
        erased = await erase(Store(azure.database, azure.blobs), args.tax_id, args.by, datetime.now(UTC).date())
    print(f"{erased} invoices redacted; vendor removed from the vendor master")


if __name__ == "__main__":
    asyncio.run(main())
