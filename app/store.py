import csv
import io
import json
from collections.abc import Mapping
from contextlib import suppress
from typing import Any, cast

from azure.core import MatchConditions
from azure.core.exceptions import ResourceExistsError, ResourceModifiedError, ResourceNotFoundError
from azure.cosmos.aio import DatabaseProxy
from azure.storage.blob import ContentSettings
from azure.storage.blob.aio import BlobServiceClient
from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from app.models import Invoice

type Doc = dict[str, Any]
CLAUSES = {"status": "c.status = @status", "number": "c.data.invoice_number = @number", "batch": "c.batch = @batch"}
CLAUSES |= {"vendor": "CONTAINS(c.data.vendor_name, @vendor, true)"}
CLAUSES |= {"finding": "EXISTS(SELECT VALUE f FROM f IN c.findings WHERE f.kind = @finding)"}
CLAUSES |= {"tax_id": "(c.vendor = @tax_id OR c.data.vendor_tax_id = @tax_id)"}
CANDIDATES = (
    "SELECT * FROM c WHERE c.id < @id AND (c.sha256 = @sha256 OR ARRAY_CONTAINS(@tax_ids, c.vendor)"
    " OR ARRAY_CONTAINS(@tax_ids, c.data.vendor_tax_id) OR (c.id > @since AND c.status IN ('queued', 'processing')))"
)
COLUMNS = "batch_id invoice_id vendor_tax_id vendor_name invoice_number issue_date due_date currency tax_rate"
COLUMNS += " tax_base tax_amount irpf_rate irpf_amount total approved_at"
AUDIT = "SELECT * FROM c WHERE c.invoice_id = @invoice_id ORDER BY c.id"
CHECKPOINTS = "SELECT c.id, c.workflow_name FROM c WHERE c.workflow_name = @workflow_name"
EXTRA, KINDS = {"name", "media_type", "request", "batch"}, {"csv": "text/csv", "json": "application/json"}


class Record(BaseModel):
    invoice: Invoice
    name: str
    media_type: str
    request: str | None = None
    batch: str | None = None
    etag: str = ""
    audited: int = 0


def to_doc(record: Record) -> Doc:
    return record.invoice.model_dump(mode="json") | record.model_dump(include=EXTRA)


def to_record(doc: Doc) -> Record:
    extra = {key: doc.get(key) for key in EXTRA} | {"etag": doc["_etag"], "audited": len(doc["timeline"])}
    return Record.model_validate({"invoice": Invoice.model_validate(doc)} | extra)


def entry(batch_id: str, invoice: Invoice, vendors: Mapping[str, str]) -> Doc:
    data, irpf, approved = invoice.data, invoice.data.irpf, [s.at for s in invoice.timeline if s.name == "approved"]
    row: Doc = {"batch_id": batch_id, "invoice_id": invoice.id, "vendor_tax_id": invoice.vendor or data.vendor_tax_id}
    row |= {"vendor_name": vendors.get(invoice.vendor or "", data.vendor_name), "approved_at": approved[-1]}
    row |= data.model_dump(include={"invoice_number", "issue_date", "due_date", "currency", "total", "tax_lines"})
    row |= {"irpf_rate": irpf.rate if irpf else 0, "irpf_amount": irpf.amount if irpf else 0}
    return cast(Doc, to_jsonable_python(row | {"line_items": data.line_items}))


def scrub[T](value: T, values: set[str]) -> T:
    text = json.dumps(value)
    for item in values:
        text = text.replace(json.dumps(item)[1:-1], "[erased]")
    return cast(T, json.loads(text))


class Store:
    def __init__(self, database: DatabaseProxy, blobs: BlobServiceClient) -> None:
        self.database, self.blobs = database, blobs

    async def read(self, container: str, item: str) -> Doc | None:
        try:
            return dict(await self.database.get_container_client(container).read_item(item, item))
        except ResourceNotFoundError:
            return None

    async def write(self, container: str, doc: Doc, etag: str | None = None) -> Doc | None:
        client, condition = self.database.get_container_client(container), MatchConditions.IfNotModified
        try:
            if etag is None:
                return dict(await client.create_item(doc))
            return dict(await client.replace_item(doc["id"], doc, etag=etag, match_condition=condition))
        except (ResourceExistsError, ResourceModifiedError):
            return None

    async def remove(self, container: str, item: str, key: str | None = None) -> None:
        await self.database.get_container_client(container).delete_item(item, key or item)

    async def query(self, container: str, sql: str, **params: object) -> list[Doc]:
        parameters = [{"name": f"@{key}", "value": value} for key, value in params.items()]
        items = self.database.get_container_client(container).query_items(sql, parameters=parameters)
        return [dict(item) async for item in items]

    async def put(self, container: str, name: str, content: bytes, kind: str, **metadata: str) -> None:
        blob, settings = self.blobs.get_blob_client(container, name), ContentSettings(content_type=kind)
        await blob.upload_blob(content, overwrite=container == "exports", content_settings=settings, metadata=metadata)

    async def fetch(self, container: str, name: str) -> bytes | None:
        try:
            return await (await self.blobs.get_blob_client(container, name).download_blob()).readall()
        except ResourceNotFoundError:
            return None

    async def drop(self, container: str, name: str) -> None:
        with suppress(ResourceNotFoundError):
            await self.blobs.get_blob_client(container, name).delete_blob()

    async def records(self, top: int = 0, **filters: str | None) -> list[Record]:
        given = {key: value for key, value in filters.items() if value is not None}
        where = " AND ".join(CLAUSES[key] for key in given) or "true"
        sql = f"SELECT {'TOP @top ' if top else ''}* FROM c WHERE {where} ORDER BY c.id DESC"
        return [to_record(doc) for doc in await self.query("invoices", sql, **given, **({"top": top} if top else {}))]

    async def find(self, status: str | None, vendor: str | None, finding: str | None) -> list[Invoice]:
        return [item.invoice for item in await self.records(50, status=status, vendor=vendor, finding=finding)]

    async def get(self, number: str) -> list[Invoice]:
        return [item.invoice for item in await self.records(5, number=number)]

    async def candidates(self, invoice: Invoice, since: str) -> list[Record]:
        tax_ids = [tax_id for tax_id in (invoice.vendor, invoice.data.vendor_tax_id) if tax_id]
        params = {"id": invoice.id, "sha256": invoice.sha256, "tax_ids": tax_ids, "since": since}
        return [to_record(doc) for doc in await self.query("invoices", CANDIDATES, **params)]

    async def load(self, invoice_id: str) -> Record | None:
        doc = await self.read("invoices", invoice_id)
        return None if doc is None else to_record(doc)

    async def create(self, record: Record, content: bytes) -> None:
        await self.put("originals", record.invoice.id, content, record.media_type, sha256=record.invoice.sha256)
        await self.write("invoices", to_doc(record))
        await self.log(record)

    async def save(self, record: Record) -> Record | None:
        if (doc := await self.write("invoices", to_doc(record), record.etag)) is None:
            return None
        await self.log(record)
        return to_record(doc)

    async def log(self, record: Record) -> None:
        for index, step in enumerate(record.invoice.timeline[record.audited :], record.audited):
            doc = {"id": f"{record.invoice.id}-{index:03}", "invoice_id": record.invoice.id}
            await self.write("audit", doc | step.model_dump(mode="json"))

    async def vendors(self) -> dict[str, str]:
        return {doc["tax_id"]: doc["name"] for doc in await self.query("vendors", "SELECT * FROM c")}

    async def export(self, batch: Doc, invoices: list[Invoice], vendors: Mapping[str, str]) -> Doc:
        entries, out = [entry(batch["id"], item, vendors) for item in invoices], io.StringIO()
        writer = csv.DictWriter(out, COLUMNS.split(), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            item | {f"tax_{k}": v for k, v in t.items()} for item in entries for t in item["tax_lines"] or [{}]
        )
        layout = {"batch_id": batch["id"], "created_at": batch["created_at"], "invoices": entries}
        for kind, content in (("csv", out.getvalue()), ("json", json.dumps(layout))):
            await self.put("exports", f"folium-{batch['id']}.{kind}", content.encode(), KINDS[kind])
        summary = {key: value for key, value in batch.items() if not key.startswith("_")}
        return summary | {"invoices": [invoice.id for invoice in invoices]}

    async def redact(self, record: Record, values: set[str], invoice: Invoice) -> Record | None:
        audit = await self.query("audit", AUDIT, invoice_id=record.invoice.id)
        for doc in audit:
            await self.write("audit", scrub(doc, values), doc["_etag"])
        for doc in await self.query("checkpoints", CHECKPOINTS, workflow_name=f"invoice-{record.invoice.id}"):
            await self.remove("checkpoints", doc["id"], doc["workflow_name"])
        await self.drop("originals", record.invoice.id)
        return await self.save(record.model_copy(update={"invoice": invoice, "name": scrub(record.name, values)}))
