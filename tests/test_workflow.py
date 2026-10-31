import json
import sys
from asyncio.subprocess import PIPE, create_subprocess_exec
from decimal import Decimal
from pathlib import Path

from agent_framework.exceptions import ChatClientException
from azure.ai.documentintelligence.models import AnalyzeResult

from app.agents import assistant, merge, normalize, normalizer
from app.extract import to_invoice
from app.models import CanonicalInvoice, Evidence, Finding, Invoice, ReviewDecision, Status, Withholding, leaves
from app.models import FindingKind as Kind
from app.rules import match_vendor
from app.workflow import build, resume
from ops import make_invoices
from tests.doubles import RECORDED, VENDORS, Replay, services

ROOT = Path(__file__).resolve().parent.parent
TRUTH = {sample.file: sample for sample in make_invoices.build(2026)}
CLEAN, IRPF, PLANTED = "inv-016.pdf", "inv-012.pdf", "inv-008.pdf"


def mapped(file: str) -> tuple[CanonicalInvoice, dict[str, Evidence]]:
    return to_invoice(AnalyzeResult(RECORDED[file]["analyze"]))


async def first_request(folder: Path, file: str, client: Replay | None = None) -> tuple[str, Invoice]:
    result = await build(file, services(folder, file, client)).run(Invoice(id=file, sha256=RECORDED[file]["sha256"]))
    [request] = result.get_request_info_events()
    return request.request_id, request.data.invoice


def test_extract_maps_all_fields() -> None:
    assert len(RECORDED) == 8
    for file in RECORDED:
        data, evidence = mapped(file)
        for path, value in leaves(data.model_dump(mode="json")).items():
            proof = evidence.get(path)
            assert value is None or (proof and 0 < proof.confidence <= 1 and proof.page and len(proof.polygon) == 8)
        truth = TRUTH[file].invoice
        assert data.model_dump(exclude={"tax_lines"}) == truth.model_dump(exclude={"tax_lines"}), file
        read = [(line.rate, line.amount, line.base) for line in data.tax_lines]
        assert read in ([], [(line.rate, line.amount, None) for line in truth.tax_lines]), file


async def test_normalizer_cross_check_rejects_invented_values() -> None:
    for file in (file for file, record in RECORDED.items() if record["answer"]):
        proposal = CanonicalInvoice.model_validate_json(RECORDED[file]["answer"])
        data, filled, rejected = merge(mapped(file)[0], proposal, RECORDED[file]["analyze"]["content"])
        assert data == TRUTH[file].invoice and filled == ["tax_lines"] and not rejected, file
    base, text = mapped(IRPF)[0], RECORDED[IRPF]["analyze"]["content"]
    proposal = CanonicalInvoice.model_validate_json(RECORDED[IRPF]["answer"])
    customer = make_invoices.TEMPLATES["customer"][1]
    invented = proposal.model_copy(update={"vendor_tax_id": customer, "total": Decimal("0.01")})
    invented.irpf = Withholding(rate=Decimal(15), amount=Decimal("999.99"))
    data, filled, rejected = merge(base.model_copy(update={"vendor_tax_id": None, "irpf": None}), invented, text)
    assert customer in text and data.vendor_tax_id is None and data.irpf is None and data.total == base.total
    assert filled == ["tax_lines"] and [item.evidence["field"] for item in rejected] == ["irpf"]
    invented.tax_lines = [line.model_copy(update={"base": Decimal("1.23")}) for line in proposal.tax_lines]
    data, filled, rejected = merge(base, invented, text)
    assert data == base and not filled and {item.kind for item in rejected} == {Kind.rejected_model_value}
    client = Replay([RECORDED[IRPF]["answer"]])
    await normalize(normalizer(client), base, text)
    assert base.iban and base.iban in text and base.iban not in client.prompts[0].replace(" ", "")


async def test_vendor_matched_by_tax_id_then_name(tmp_path: Path) -> None:
    known = CanonicalInvoice(vendor_name="ACEITES DEL BAJO ARAGON SL", vendor_tax_id="B36455681")
    assert match_vendor(known, VENDORS) == match_vendor(known.model_copy(update={"vendor_tax_id": "X"}), VENDORS)
    assert match_vendor(known, VENDORS) == "B36455681" and not match_vendor(CanonicalInvoice(vendor_name="X"), VENDORS)
    server = services(tmp_path, CLEAN)
    server.vendors = {}
    result = await build(CLEAN, server).run(Invoice(id=CLEAN, sha256=RECORDED[CLEAN]["sha256"]))
    invoice = result.get_request_info_events()[0].data.invoice
    assert invoice.vendor is None and [item.kind for item in invoice.findings] == [Kind.unknown_vendor]


async def test_injected_invoice_skips_the_normalizer(tmp_path: Path) -> None:
    injected = [file for file in RECORDED if TRUTH[file].canary]
    assert len(injected) == 2
    for file in injected:
        assert RECORDED[file]["attack"] and RECORDED[file]["answer"] is None
        invoice = (await first_request(tmp_path / file, file))[1]
        assert "normalized" not in [item.name for item in invoice.timeline] and invoice.status == Status.with_lead
        assert [item.kind for item in invoice.findings] == [Kind.possible_injection]
        assert str(TRUTH[file].canary) not in json.dumps(invoice.data.model_dump(mode="json"))


async def test_resume_from_checkpoint(tmp_path: Path) -> None:
    child = await create_subprocess_exec(
        sys.executable, "-m", "tests.doubles", str(tmp_path), CLEAN, cwd=ROOT, stdout=PIPE
    )
    request_id = (await child.stdout.readline()).decode().strip() if child.stdout else ""
    child.kill()
    await child.wait()
    decision, server = ReviewDecision(action="approve", by="clerk"), services(tmp_path, CLEAN)
    resumed = await resume(CLEAN, request_id, decision, server)
    assert resumed is not None
    [invoice] = resumed.get_outputs()
    names = ["extracted", "shielded", "normalized", "validated", "deduplicated", "review_requested", "approved"]
    assert invoice.status == Status.approved and [item.name for item in invoice.timeline] == names
    assert invoice.data == TRUTH[CLEAN].invoice and invoice.vendor == TRUTH[CLEAN].vendor
    assert [item.at for item in invoice.timeline] == sorted(item.at for item in invoice.timeline)
    assert invoice.timeline[2].detail["model"] == RECORDED[CLEAN]["model"] and invoice.timeline[-1].by == "clerk"
    assert invoice.timeline[2].detail["prompt"] == "normalizer_v2" and invoice.timeline[0].detail["api"] == "2024-11-30"


async def test_clerk_cannot_approve_findings(tmp_path: Path) -> None:
    request_id, invoice = await first_request(tmp_path, PLANTED)
    assert invoice.status == Status.with_lead and [item.kind for item in invoice.findings] == [Kind.lines_mismatch]
    clerk, lead = ReviewDecision(action="approve", by="clerk"), ReviewDecision(action="approve", by="lead", lead=True)
    for decision in (clerk, lead):
        result = await resume(PLANTED, request_id, decision, services(tmp_path, PLANTED))
        assert result is not None and not result.get_outputs()
        request_id = result.get_request_info_events()[0].request_id


async def test_model_outage_keeps_the_mapping(tmp_path: Path) -> None:
    client = Replay([ChatClientException("429 Too Many Requests")])
    invoice = (await first_request(tmp_path, CLEAN, client))[1]
    assert [item.kind for item in invoice.findings] == [Kind.model_unavailable] and invoice.data == mapped(CLEAN)[0]


async def test_assistant_has_no_write_tool() -> None:
    found = [Finding(kind=Kind.probable_duplicate, rule="same vendor and total, issued within 7 days")]
    stored = Invoice(id="a", sha256="b", data=mapped(CLEAN)[0], evidence=mapped(CLEAN)[1], findings=found)

    class Catalog:
        async def find(self, status: str | None, vendor: str | None, finding: str | None) -> list[Invoice]:
            return [stored]

        async def get(self, number: str) -> list[Invoice]:
            return [stored]

    tools = {tool.name: tool for tool in assistant(Replay([]), Catalog()).default_options["tools"]}
    assert tools.keys() == {"find_invoices", "get_invoice"}
    for tool in tools.values():
        result = await tool.invoke(arguments={"number": "x"} if tool.name == "get_invoice" else {})
        output = "".join(item.text or "" for item in result)
        assert stored.data.iban and stored.data.iban not in output and "polygon" not in output
        assert "probable_duplicate" in output and all(
            kind in json.dumps(tools["find_invoices"].parameters()) for kind in Kind
        )
