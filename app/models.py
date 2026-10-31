from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

FindingKind = StrEnum(
    "FindingKind",
    "missing_field lines_mismatch tax_line_mismatch total_mismatch invalid_vat_rate invalid_irpf_rate invalid_tax_id"
    " invalid_date exact_duplicate probable_duplicate",
)


def compact_tax_id(value: str) -> str:
    return "".join(value.upper().translate(str.maketrans("", "", "-./,")).split()).removeprefix("ES")


class TaxLine(BaseModel):
    rate: Decimal
    base: Decimal | None = None
    amount: Decimal


class Withholding(BaseModel):
    rate: Decimal
    amount: Decimal


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
    iban: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)


class Finding(BaseModel):
    kind: FindingKind
    rule: str
    evidence: dict[str, str] = Field(default_factory=dict)
    duplicate_of: str | None = None


class Invoice(BaseModel):
    id: str
    sha256: str
    data: CanonicalInvoice = Field(default_factory=CanonicalInvoice)
