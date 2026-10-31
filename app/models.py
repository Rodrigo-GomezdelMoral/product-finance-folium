from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

FindingKind = StrEnum(
    "FindingKind",
    "missing_field lines_mismatch tax_line_mismatch total_mismatch invalid_vat_rate invalid_irpf_rate invalid_tax_id"
    " invalid_date exact_duplicate probable_duplicate unknown_vendor rejected_model_value possible_injection"
    " model_unavailable",
)
Status = StrEnum("Status", "queued processing ready with_lead approved rejected exported failed")


def compact_tax_id(value: str) -> str:
    return "".join(value.upper().translate(str.maketrans("", "", "-./,")).split()).removeprefix("ES")


def compact(value: str) -> str:
    return "".join(value.upper().split())


def leaves(value: Any, path: str = "") -> dict[str, Any]:
    items = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else None
    if items is None:
        return {path: value}
    return {key: leaf for name, item in items for key, leaf in leaves(item, f"{path}.{name}".lstrip(".")).items()}


class TaxLine(BaseModel):
    rate: Decimal
    base: Decimal | None = None
    amount: Decimal


class Withholding(BaseModel):
    rate: Decimal
    amount: Annotated[Decimal, AfterValidator(abs)]


class LineItem(BaseModel):
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal


class CanonicalInvoice(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    vendor_name: str | None = None
    vendor_tax_id: Annotated[str, AfterValidator(compact_tax_id)] | None = None
    invoice_number: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    tax_lines: list[TaxLine] = Field(default_factory=list)
    irpf: Withholding | None = None
    total: Decimal | None = None
    iban: Annotated[str, AfterValidator(compact)] | None = None
    line_items: list[LineItem] = Field(default_factory=list)


class Finding(BaseModel):
    kind: FindingKind
    rule: str
    evidence: dict[str, str] = Field(default_factory=dict)
    duplicate_of: str | None = None


class Evidence(BaseModel):
    confidence: float = 0
    page: int | None = None
    polygon: list[float] = Field(default_factory=list)


class Step(BaseModel):
    name: str
    at: datetime
    by: str = "folium"
    detail: dict[str, str] = Field(default_factory=dict)


class Invoice(BaseModel):
    id: str
    sha256: str
    data: CanonicalInvoice = Field(default_factory=CanonicalInvoice)
    status: Status = Status.queued
    pages: int = 0
    vendor: str | None = None
    evidence: dict[str, Evidence] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
    timeline: list[Step] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    invoice: Invoice


class ReviewDecision(BaseModel):
    action: Literal["approve", "reject", "send_to_lead"]
    by: str
    lead: bool = False
    reason: str | None = None
    data: CanonicalInvoice | None = None
