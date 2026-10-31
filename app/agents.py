import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Protocol

from agent_framework import Agent, HistoryProvider, SupportsChatGetResponse
from agent_framework.exceptions import ChatClientException

from app.models import CanonicalInvoice, Finding, Invoice, leaves
from app.models import FindingKind as Kind
from app.rules import finding

PROMPTS, NORMALIZER, ASSISTANT = Path(__file__).parent / "prompts", "normalizer_v2", "assistant_v2"
PROMPT = {name: (PROMPTS / f"{name}.md").read_text("utf-8") for name in (NORMALIZER, ASSISTANT)}
OPTIONS: dict[str, Any] = {"store": False, "reasoning": {"effort": "minimal"}, "timeout": 15}
FILLABLE = {"irpf", "tax_lines"}
IBAN = re.compile(r"(?i)\biban\b.*|\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")
HIDDEN: dict[str, Any] = {"data": {"iban"}, "evidence": True}
BRIEF: dict[str, Any] = {"data": {"invoice_number", "vendor_name", "issue_date", "total", "currency"}, "status": True}
BRIEF |= {"findings": {"__all__": {"kind"}}}
State = Annotated[str | None, "queued, processing, ready, with_lead, approved, rejected, exported or failed"]
Vendor = Annotated[str | None, "part of the vendor name"]
Kinds = Annotated[str | None, f"one finding kind: {', '.join(Kind)}"]
Client = SupportsChatGetResponse[Any]
type Merged = tuple[CanonicalInvoice, list[str], list[Finding]]
type Normalized = tuple[CanonicalInvoice, list[str], list[Finding], dict[str, str]]


def amounts(text: str) -> set[Decimal]:
    tokens = [token.rstrip(".,") for token in re.findall(r"\d[\d.,]*", text)]
    candidates = {token.replace(group, "").replace(point, ".") for token in tokens for point, group in (",.", ".,")}
    return {Decimal(candidate) for candidate in candidates if re.fullmatch(r"\d+(?:\.\d+)?", candidate)}


def merge(base: CanonicalInvoice, proposed: CanonicalInvoice, text: str) -> Merged:
    data, numbers, filled, rejected = base.model_dump(), amounts(text), list[str](), list[Finding]()
    bases = {(line.rate, line.amount): line.base for line in proposed.tax_lines}
    lines = [line | {"base": bases.get((line["rate"], line["amount"]))} for line in data["tax_lines"]]
    for name, value in (proposed.model_dump(include=FILLABLE) | ({"tax_lines": lines} if lines else {})).items():
        if value in (None, [], data[name]) or (data[name] not in (None, []) and name != "tax_lines"):
            continue
        if unseen := [leaf for leaf in leaves(value).values() if leaf is not None and abs(leaf) not in numbers]:
            rule = "every amount the model proposes is printed in the document"
            rejected.append(finding(Kind.rejected_model_value, rule, field=name, value=unseen[0]))
        else:
            data[name], filled = value, [*filled, name]
    return CanonicalInvoice.model_validate(data), filled, rejected


async def normalize(agent: Agent[Any] | None, base: CanonicalInvoice, text: str) -> Normalized:
    if agent is None:
        return base, [], [], {"normalizer": "off"}
    mapped, document = base.model_dump_json(exclude={"iban"}), IBAN.sub("[IBAN]", text)
    try:
        response = await agent.run(f"Mapped fields:\n{mapped}\n<document>\n{document}\n</document>")
    except ChatClientException as error:
        rule = "the normalizer answers; the invoice keeps the Document Intelligence mapping"
        return base, [], [finding(Kind.model_unavailable, rule, error=type(error).__name__)], {"prompt": NORMALIZER}
    data, filled, rejected = merge(base, response.value or CanonicalInvoice(), text)
    model = str(getattr(response.raw_representation, "model", agent.name))
    return data, filled, rejected, {"model": model, "prompt": NORMALIZER, "filled": ",".join(filled)}


class Catalog(Protocol):
    async def find(self, status: str | None, vendor: str | None, finding: str | None) -> list[Invoice]: ...

    async def get(self, number: str) -> list[Invoice]: ...


class InvoiceTools:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    async def find_invoices(self, status: State = None, vendor: Vendor = None, finding: Kinds = None) -> str:
        """Find invoices by status, vendor or finding kind. Read-only."""
        found = await self.catalog.find(status, vendor, finding)
        return json.dumps([invoice.model_dump(mode="json", include=BRIEF) for invoice in found[:50]])

    async def get_invoice(self, number: Annotated[str, "the invoice number as printed"]) -> str:
        """Read one invoice: fields, findings, duplicates and timeline. Read-only."""
        found = await self.catalog.get(number)
        return json.dumps([invoice.model_dump(mode="json", exclude=HIDDEN) for invoice in found])


def normalizer(client: Client) -> Agent[Any]:
    options = OPTIONS | {"response_format": CanonicalInvoice, "max_tokens": 1500}
    return Agent(client, PROMPT[NORMALIZER], name="Normalizer", default_options=options)


def assistant(client: Client, catalog: Catalog, history: HistoryProvider | None = None) -> Agent[Any]:
    reader, log = InvoiceTools(catalog), [history] if history else []
    tools, opts = [reader.find_invoices, reader.get_invoice], OPTIONS | {"max_tokens": 800}
    return Agent(client, PROMPT[ASSISTANT], name="Assistant", tools=tools, context_providers=log, default_options=opts)
