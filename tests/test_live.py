import hashlib
import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from agent_framework import ChatContext, FileCheckpointStorage, chat_middleware
from agent_framework.foundry import FoundryChatClient
from azure.ai.contentsafety.aio import ContentSafetyClient
from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.identity.aio import DefaultAzureCredential

from app import extract
from app.agents import assistant, normalizer
from app.models import Invoice, ReviewDecision, Status, leaves
from app.workflow import CHECKPOINT_TYPES, Services, build, resume
from ops import make_invoices
from tests.doubles import FIXTURES, VENDORS

FILES = ["inv-016.pdf", "inv-008.pdf", "inv-012.pdf", "inv-024.jpg", "inv-005.pdf", "inv-020.pdf", "inv-010.pdf"]
FILES += ["inv-039.pdf"]
pytestmark = pytest.mark.skipif("FOUNDRY_ACCOUNT_ENDPOINT" not in os.environ, reason="runs against the shared base")


class Catalog:
    def __init__(self, invoices: list[Invoice]) -> None:
        self.invoices = invoices

    async def find(self, status: str | None, vendor: str | None, finding: str | None) -> list[Invoice]:
        return [item for item in self.invoices if status in (None, item.status)]

    async def get(self, number: str) -> list[Invoice]:
        return [item for item in self.invoices if item.data.invoice_number == number]


async def test_workflow_end_to_end_against_the_shared_base(tmp_path: Path) -> None:
    samples, endpoint = (
        {sample.file: sample for sample in make_invoices.write(2026, tmp_path)},
        os.environ["FOUNDRY_ACCOUNT_ENDPOINT"],
    )
    recorded: dict[str, dict[str, Any]] = {}
    answers: list[tuple[str, str]] = []

    @chat_middleware
    async def record(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        await call_next()
        result: Any = context.result
        answers.append((result.text, str(result.model)))

    credential = DefaultAzureCredential()
    async with (
        credential,
        DocumentIntelligenceClient(endpoint, credential) as di,
        ContentSafetyClient(endpoint, credential) as safety,
    ):
        client = FoundryChatClient(credential=credential, middleware=[record])

        async def analyze(invoice_id: str) -> AnalyzeResult:
            result = await extract.analyze(di, (tmp_path / "invoices" / invoice_id).read_bytes())
            raw = result.as_dict()
            kept = {key: raw[key] for key in ("apiVersion", "modelId", "content", "documents")}
            recorded[invoice_id] = kept | {"pages": [{"pageNumber": page["pageNumber"]} for page in raw["pages"]]}
            return result

        async def shield(text: str) -> bool:
            return await extract.attacked(safety, text)

        async def candidates(invoice: Invoice) -> list[Invoice]:
            return []

        storage = FileCheckpointStorage(tmp_path / "checkpoints", allowed_checkpoint_types=CHECKPOINT_TYPES)
        services = Services(analyze, shield, normalizer(client), VENDORS, candidates, storage)
        fixtures, pending = dict[str, dict[str, Any]](), dict[str, tuple[str, Invoice]]()
        for file in FILES:
            sha256, asked = hashlib.sha256((tmp_path / "invoices" / file).read_bytes()).hexdigest(), len(answers)
            result = await build(file, services).run(Invoice(id=file, sha256=sha256))
            [request] = result.get_request_info_events()
            invoice = request.data.invoice
            pending[file] = (request.request_id, invoice)
            attack = "possible_injection" in [item.kind for item in invoice.findings]
            answer, model = answers[asked] if len(answers) > asked else (None, None)
            fixtures[file] = {
                "sha256": sha256,
                "analyze": recorded[file],
                "attack": attack,
                "answer": answer,
                "model": model,
            }
            assert invoice.status in (Status.ready, Status.with_lead) and invoice.data.iban
            canary = samples[file].canary
            assert not canary or canary not in json.dumps(leaves(invoice.data.model_dump(mode="json")))

        request_id, invoice = pending["inv-016.pdf"]
        decision = ReviewDecision(action="approve", by="lead", lead=True, reason="checked against the original")
        resumed = await resume("inv-016.pdf", request_id, decision, services)
        assert resumed is not None and [item.status for item in resumed.get_outputs()] == [Status.approved]

        helper = assistant(client, Catalog([invoice for _, invoice in pending.values()]))
        reply = await helper.run("Which invoices are waiting for the lead?")
        assert "[INV-" in reply.text

    if os.environ.get("RECORD_FIXTURES"):
        FIXTURES.parent.mkdir(exist_ok=True)
        FIXTURES.write_text(json.dumps(fixtures, ensure_ascii=False, indent=1) + "\n", "utf-8")
