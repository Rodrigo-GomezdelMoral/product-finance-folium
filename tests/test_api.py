import asyncio
import base64
import hashlib
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from agent_framework import FileCheckpointStorage
from azure.core.exceptions import AzureError, HttpResponseError
from httpx import ASGITransport, AsyncClient

from app.agents import assistant
from app.main import MAX_BYTES, app
from app.models import Invoice, leaves
from app.store import AUDIT, Record, to_doc
from app.worker import Runtime, new_id, process
from app.workflow import CHECKPOINT_TYPES
from ops.erase import erase
from tests.doubles import MemoryStore, Replay, recorded

INVOICES, ANSWER = Path(__file__).parent.parent / "eval" / "datasets" / "invoices", "[INV-F2026-0558] waits for you."
Api = tuple[AsyncClient, Runtime]


def principal(*roles: str, name: str = "Ana Clerk") -> dict[str, str]:
    claims = [{"typ": "name", "val": name}, {"typ": "oid", "val": name}] + [{"typ": "roles", "val": r} for r in roles]
    return {"X-MS-CLIENT-PRINCIPAL": base64.b64encode(json.dumps({"claims": claims}).encode()).decode()}


CLERK, LEAD = principal("Invoice.Process"), principal("Invoice.Approve", name="Luis Lead")


@pytest.fixture
async def api(tmp_path: Path) -> AsyncIterator[Api]:
    async def send(ids: list[str]) -> None:
        await asyncio.gather(*(process(runtime, invoice_id) for invoice_id in ids))

    store, checkpoints = MemoryStore(), FileCheckpointStorage(tmp_path, allowed_checkpoint_types=CHECKPOINT_TYPES)
    app.state.runtime = runtime = Runtime(store, recorded(store, checkpoints), send, assistant(Replay([ANSWER]), store))
    async with AsyncClient(transport=ASGITransport(app), base_url="http://folium") as client:
        yield client, runtime
    del app.state.runtime


def read(name: str, extra: bytes = b"") -> tuple[str, bytes]:
    return name, (INVOICES / name).read_bytes() + extra


async def upload(client: AsyncClient, *files: tuple[str, bytes]) -> list[dict[str, Any]]:
    response = await client.post("/api/invoices", files=[("files", file) for file in files], headers=CLERK)
    return [(await client.get(f"/api/invoices/{item['id']}", headers=CLERK)).json() for item in response.json()]


async def review(client: AsyncClient, item: dict[str, Any], who: dict[str, str], **body: Any) -> dict[str, Any]:
    response = await client.post(f"/api/invoices/{item['id']}/review", json={"action": "approve"} | body, headers=who)
    return dict(response.json())


async def export(client: AsyncClient, key: str, who: dict[str, str] = LEAD) -> Any:
    response = await client.post("/api/exports", headers=who | {"Idempotency-Key": key})
    return response.json() if response.status_code == 200 else response.status_code


async def test_upload_batch_hash_and_types(api: Api) -> None:
    client, _ = api
    name, pdf = read("inv-016.pdf")
    response = await client.post("/api/invoices", files=[("files", (name, pdf))] * 2, headers=CLERK)
    first, second = response.json()
    assert response.status_code == 202 and first["status"] == second["status"] == "queued" != first["id"]
    assert first["sha256"] == hashlib.sha256(pdf).hexdigest() and not first["findings"]
    assert [(item["kind"], item["duplicate_of"]) for item in second["findings"]] == [("exact_duplicate", first["id"])]
    big = [(name, b"%PDF-" + bytes(MAX_BYTES))]
    for files, status in (([("a.txt", b"text")], 415), ([(name, pdf)] * 21, 413), (big, 413)):
        response = await client.post("/api/invoices", files=[("files", file) for file in files], headers=CLERK)
        assert response.status_code == status
    assert (await client.get("/api/invoices")).status_code == 401
    assert (await client.get("/api/invoices", headers=principal())).status_code == 403
    listed = (await client.get("/api/invoices", headers=CLERK)).json()
    assert [item["status"] for item in listed] == ["with_lead", "ready"]


async def test_duplicate_blocks_export(api: Api) -> None:
    client, _ = api
    original, copy = await upload(client, read("inv-016.pdf"), read("inv-016.pdf", b"\n"))
    assert original["status"] == "ready" and not original["findings"] and copy["status"] == "with_lead"
    assert [(item["kind"], item["duplicate_of"]) for item in copy["findings"]] == [("exact_duplicate", original["id"])]
    assert (await review(client, copy, CLERK))["status"] == "with_lead"
    assert (await review(client, original, CLERK))["status"] == "approved"
    assert (await export(client, "month-end-01"))["invoices"] == [original["id"]]
    await review(client, copy, LEAD, reason="the vendor confirmed a second delivery")
    assert (await export(client, "month-end-02"))["invoices"] == [copy["id"]]


async def test_correction_recorded(api: Api, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="folium")
    client, _ = api
    [item] = await upload(client, read("inv-008.pdf"))
    assert item["status"] == "with_lead" and [finding["kind"] for finding in item["findings"]] == ["lines_mismatch"]
    assert (await review(client, item, CLERK))["status"] == "with_lead"
    line = item["data"]["line_items"][0]
    fixed = item["data"] | {"line_items": [line | {"amount": str(Decimal(line["amount"]) - 1)}]}
    approved = await review(client, item, CLERK, data=fixed, review_seconds=42)
    [correction] = [entry for entry in approved["timeline"] if entry["name"] == "corrected"]
    assert approved["status"] == "approved" and correction["by"] == "Ana Clerk" and correction["at"]
    assert (await review(client, item, LEAD))["detail"] == "the invoice is not waiting for review"
    after = fixed["line_items"][0]["amount"]
    assert correction["detail"] == {"field": "line_items.0.amount", "before": line["amount"], "after": after}
    events = {record.__dict__.get("microsoft.custom_event.name") for record in caplog.records}
    assert {"invoice_uploaded", "invoice_ready", "field_corrected", "invoice_approved"} <= events


async def test_export_exactly_once(api: Api) -> None:
    client, _ = api
    items = await upload(client, read("inv-016.pdf"), read("inv-039.pdf"))
    assert [(await review(client, item, CLERK))["status"] for item in items] == ["approved"] * 2
    first, again = await export(client, "month-end-01"), await export(client, "month-end-01")
    assert first == again and sorted(first["invoices"]) == sorted(item["id"] for item in items)
    assert await export(client, "month-end-02") == 409 and await export(client, "month-end-03", CLERK) == 403
    rows = (await client.get(f"/api/exports/{first['id']}?format=csv", headers=LEAD)).text
    layout = (await client.get(f"/api/exports/{first['id']}", headers=LEAD)).json()
    assert len(rows.splitlines()) == 1 + sum(len(item["data"]["tax_lines"]) for item in items) == 4
    assert len(layout["invoices"]) == 2 and all(item["data"]["iban"] not in rows + json.dumps(layout) for item in items)


async def test_timeline_complete(api: Api) -> None:
    client, runtime = api
    [item] = await upload(client, read("inv-012.pdf"))
    await review(client, item, CLERK)
    await export(client, "timeline-01")
    item = (await client.get(f"/api/invoices/{item['id']}", headers=CLERK)).json()
    names = ["uploaded", "extracted", "shielded", "normalized", "validated", "deduplicated", "review_requested"]
    names += ["approved", "exported"]
    assert [entry["name"] for entry in item["timeline"]] == names and item["timeline"][-1]["by"] == "Luis Lead"
    assert item["timeline"][3]["detail"]["prompt"] == "normalizer_v2"
    original = (await client.get(f"/api/invoices/{item['id']}/original", headers=CLERK)).content
    assert hashlib.sha256(original).hexdigest() == item["sha256"] == hashlib.sha256(read("inv-012.pdf")[1]).hexdigest()
    audit = await runtime.store.query("audit", AUDIT, invoice_id=item["id"])
    assert [(e["id"], e["name"]) for e in audit] == [(f"{item['id']}-{i:03}", n) for i, n in enumerate(names)]


async def test_erase_redacts_personal_fields(api: Api) -> None:
    client, runtime = api
    [item] = await upload(client, read("inv-012.pdf"))
    tax_id, data = item["vendor"], item["data"]
    with pytest.raises(ValueError, match="retention"):
        await erase(runtime.store, tax_id, "Luis Lead", date(2032, 12, 31))
    assert await erase(runtime.store, tax_id, "Luis Lead", date(2033, 1, 1)) == 1
    record = await runtime.store.load(item["id"])
    audit = await runtime.store.query("audit", AUDIT, invoice_id=item["id"])
    assert record and record.invoice.timeline[-1].name == "erased" and record.invoice.timeline[-1].by == "Luis Lead"
    assert not {tax_id, data["vendor_name"], data["iban"]} & set(leaves([to_doc(record), audit]).values())
    assert not await runtime.store.fetch("originals", item["id"]) and not await runtime.store.read("vendors", tax_id)


async def test_redelivered_message_is_a_noop(api: Api) -> None:
    client, runtime = api
    [item] = await upload(client, read("inv-016.pdf"))
    before = await runtime.store.load(item["id"])
    await process(runtime, item["id"])
    after = await runtime.store.load(item["id"])
    assert before and after and before.etag == after.etag and after.invoice.status == "ready"
    poison = Record(invoice=Invoice(id=new_id(datetime.now(UTC)), sha256="0"), name="x.pdf", media_type="image/png")
    await runtime.store.create(poison, b"%PDF-")
    await process(runtime, poison.invoice.id, AzureError("Document Intelligence unavailable"))
    failed = await runtime.store.load(poison.invoice.id)
    assert failed and failed.invoice.status == "failed" and failed.invoice.timeline[-1].detail["error"] == "AzureError"


async def test_chat_feedback_and_outages(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    client, runtime = api
    response = await client.post("/api/chat", json={"message": "Which invoices wait for the lead?"}, headers=CLERK)
    owner = hashlib.sha256(b"Ana Clerk").hexdigest()[:12]
    assert response.text == ANSWER and response.headers["x-conversation"].startswith(owner)
    assert (await client.post("/api/feedback", json={"helpful": True}, headers=CLERK)).status_code == 204

    async def throttled(invoice_id: str) -> None:
        raise HttpResponseError(message="429 Too Many Requests")

    monkeypatch.setattr(runtime.store, "load", throttled)
    response = await client.get("/api/invoices/any", headers=CLERK)
    assert response.status_code == 503 and response.headers["retry-after"] == "10"
