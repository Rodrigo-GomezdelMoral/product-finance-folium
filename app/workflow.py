from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Never

from agent_framework import (
    Agent,
    CheckpointStorage,
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowRunResult,
    executor,
    handler,
    response_handler,
)
from azure.ai.documentintelligence.models import AnalyzeResult
from pydantic import BaseModel
from pydantic_core import TzInfo

from app.agents import normalize
from app.extract import to_invoice
from app.models import (
    CanonicalInvoice,
    Evidence,
    Finding,
    Invoice,
    LineItem,
    ReviewDecision,
    ReviewRequest,
    Status,
    Step,
    TaxLine,
    Withholding,
    leaves,
)
from app.models import FindingKind as Kind
from app.rules import duplicates, finding, match_vendor, validate

RULES = {Kind.missing_field, Kind.lines_mismatch, Kind.tax_line_mismatch, Kind.total_mismatch, Kind.invalid_vat_rate}
RULES |= {Kind.invalid_irpf_rate, Kind.invalid_tax_id, Kind.invalid_date}


class Draft(BaseModel):
    invoice: Invoice
    content: str = ""
    attack: bool = False


@dataclass
class Services:
    analyze: Callable[[str], Awaitable[AnalyzeResult]]
    shield: Callable[[str], Awaitable[bool]]
    normalizer: Agent[Any] | None
    vendors: Mapping[str, str]
    candidates: Callable[[Invoice], Awaitable[list[Invoice]]]
    checkpoints: CheckpointStorage


MODELS = (Draft, Invoice, CanonicalInvoice, TaxLine, Withholding, LineItem, Finding, Kind, Status, Evidence, Step)
CHECKPOINT_TYPES = [f"{k.__module__}:{k.__qualname__}" for k in (*MODELS, ReviewRequest, ReviewDecision, TzInfo)]


def today() -> date:
    return datetime.now(UTC).date()


def step(invoice: Invoice, name: str, by: str = "folium", /, **detail: object) -> Invoice:
    entry = Step(name=name, at=datetime.now(UTC), by=by, detail={key: str(value) for key, value in detail.items()})
    return invoice.model_copy(update={"timeline": [*invoice.timeline, entry]})


def found(invoice: Invoice, findings: list[Finding], name: str, /, **detail: object) -> Invoice:
    return step(invoice.model_copy(update={"findings": invoice.findings + findings}), name, **detail)


def as_vendor(invoice: Invoice) -> Invoice:
    vendor = invoice.vendor or invoice.data.vendor_tax_id
    return invoice.model_copy(update={"data": invoice.data.model_copy(update={"vendor_tax_id": vendor})})


def corrected(invoice: Invoice, decision: ReviewDecision) -> Invoice:
    if decision.data is None or decision.data == invoice.data:
        return invoice
    before, after = leaves(invoice.data.model_dump(mode="json")), leaves(decision.data.model_dump(mode="json"))
    for path in sorted(before.keys() | after.keys()):
        if before.get(path) != after.get(path):
            invoice = step(
                invoice, "corrected", decision.by, field=path, before=before.get(path), after=after.get(path)
            )
    kept = [item for item in invoice.findings if item.kind not in RULES]
    return invoice.model_copy(update={"data": decision.data, "findings": kept + validate(decision.data, today())})


async def ask(ctx: WorkflowContext[Any, Any], invoice: Invoice, status: Status) -> None:
    invoice = step(invoice.model_copy(update={"status": status}), "review_requested", status=status)
    await ctx.request_info(ReviewRequest(invoice=invoice), ReviewDecision)


class Review(Executor):
    def __init__(self) -> None:
        super().__init__(id="review")

    @handler
    async def request(self, draft: Draft, ctx: WorkflowContext) -> None:
        await ask(ctx, draft.invoice, Status.with_lead if draft.invoice.findings else Status.ready)

    @response_handler
    async def decide(
        self, request: ReviewRequest, decision: ReviewDecision, ctx: WorkflowContext[Never, Invoice]
    ) -> None:
        invoice, lead = corrected(request.invoice, decision), decision.lead and bool(decision.reason)
        approve = decision.action == "approve" and (lead or not invoice.findings)
        if approve or (decision.action == "reject" and lead):
            status = Status.approved if approve else Status.rejected
            await ctx.yield_output(
                step(invoice.model_copy(update={"status": status}), status, decision.by, reason=decision.reason)
            )
        else:
            await ask(ctx, step(invoice, "sent_to_lead", decision.by, reason=decision.reason), Status.with_lead)


def build(invoice_id: str, services: Services) -> Workflow:
    @executor(id="extract")
    async def extract(invoice: Invoice, ctx: WorkflowContext[Draft]) -> None:
        result = await services.analyze(invoice.id)
        data, evidence = to_invoice(result)
        update = {"data": data, "evidence": evidence, "pages": len(result.pages), "status": Status.processing}
        invoice = step(invoice.model_copy(update=update), "extracted", model=result.model_id, api=result.api_version)
        await ctx.send_message(Draft(invoice=invoice, content=result.content))

    @executor(id="shield")
    async def shield(draft: Draft, ctx: WorkflowContext[Draft]) -> None:
        attack = await services.shield(draft.content)
        injection = [finding(Kind.possible_injection, "Prompt Shields detects no document attack")] * attack
        await ctx.send_message(
            Draft(
                invoice=found(draft.invoice, injection, "shielded", attack=attack), content=draft.content, attack=attack
            )
        )

    @executor(id="normalize")
    async def normal(draft: Draft, ctx: WorkflowContext[Draft]) -> None:
        data, filled, rejected, detail = await normalize(services.normalizer, draft.invoice.data, draft.content)
        evidence = {path: proof for path, proof in draft.invoice.evidence.items() if path.split(".")[0] not in filled}
        evidence |= dict.fromkeys(leaves(data.model_dump(include=set(filled))), Evidence())
        invoice = draft.invoice.model_copy(update={"data": data, "evidence": evidence})
        await ctx.send_message(Draft(invoice=found(invoice, rejected, "normalized", **detail), content=draft.content))

    @executor(id="validate")
    async def check(draft: Draft, ctx: WorkflowContext[Draft]) -> None:
        invoice, vendor = draft.invoice, match_vendor(draft.invoice.data, services.vendors)
        unknown = [] if vendor else [finding(Kind.unknown_vendor, "vendor tax ID or name in the vendor master")]
        rules = validate(invoice.data, today()) + unknown
        invoice = found(
            invoice.model_copy(update={"vendor": vendor}), rules, "validated", vendor=vendor, findings=len(rules)
        )
        await ctx.send_message(Draft(invoice=invoice, content=draft.content))

    @executor(id="dedupe")
    async def dedupe(draft: Draft, ctx: WorkflowContext[Draft]) -> None:
        others = [as_vendor(other) for other in await services.candidates(draft.invoice)]
        twins = duplicates(as_vendor(draft.invoice), others)
        await ctx.send_message(Draft(invoice=found(draft.invoice, twins, "deduplicated", duplicates=len(twins))))

    builder = WorkflowBuilder(
        name=f"invoice-{invoice_id}", start_executor=extract, checkpoint_storage=services.checkpoints
    )
    builder.add_edge(extract, shield).add_edge(shield, normal, condition=lambda draft: not draft.attack)
    builder.add_edge(shield, check, condition=lambda draft: draft.attack).add_edge(normal, check)
    return builder.add_edge(check, dedupe).add_edge(dedupe, Review()).build()


async def resume(
    invoice_id: str, request_id: str, decision: ReviewDecision, services: Services
) -> WorkflowRunResult | None:
    checkpoints = await services.checkpoints.list_checkpoints(workflow_name=f"invoice-{invoice_id}")
    pending = [checkpoint for checkpoint in checkpoints if request_id in checkpoint.pending_request_info_events]
    if not pending:
        return None
    latest = max(pending, key=lambda checkpoint: checkpoint.iteration_count).checkpoint_id
    return await build(invoice_id, services).run(checkpoint_id=latest, responses={request_id: decision})
