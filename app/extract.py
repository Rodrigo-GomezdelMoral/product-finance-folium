import re
from decimal import Decimal
from io import BytesIO
from typing import Any

from azure.ai.contentsafety.aio import ContentSafetyClient
from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult, DocumentField
from azure.core.rest import HttpRequest

from app.models import CanonicalInvoice, Evidence

MODEL, LOCALE, SHIELD = "prebuilt-invoice", "es-ES", "/text:shieldPrompt?api-version=2024-09-01"
HEADER = {"vendor_name": "VendorName", "vendor_tax_id": "VendorTaxId", "invoice_number": "InvoiceId"}
HEADER |= {"issue_date": "InvoiceDate", "due_date": "DueDate", "subtotal": "SubTotal", "total": "InvoiceTotal"}
LINE = {"description": "Description", "quantity": "Quantity", "unit_price": "UnitPrice", "amount": "Amount"}
LISTS = {"tax_lines": ("TaxDetails", {"rate": "Rate", "amount": "Amount"}), "line_items": ("Items", LINE)}
CHUNK, OVERLAP, DOCUMENTS, CENT = 2000, 200, 5, Decimal("0.01")


def number(text: str) -> Decimal | None:
    digits = re.sub(r"[^\d,.]", "", text)
    digits = digits.replace(".", "").replace(",", ".") if "," in digits else digits
    return Decimal(digits) if re.fullmatch(r"\d+(?:\.\d+)?", digits) else None


def value(field: DocumentField) -> Any:
    if field.type == "currency":
        return None if field.value_currency is None else Decimal(str(field.value_currency.amount)).quantize(CENT)
    if field.type == "number":
        return None if field.value_number is None else Decimal(str(field.value_number))
    return field.value_date if field.type == "date" else field.value_string


def read(fields: dict[str, DocumentField], names: dict[str, str], evidence: dict[str, Evidence]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for name, key in names.items():
        item = value(fields[key]) if key in fields else None
        item = number(item) if name == "rate" and isinstance(item, str) else item
        if item is None:
            continue
        found[name], regions = item, fields[key].bounding_regions or []
        page, polygon = (regions[0].page_number, regions[0].polygon) if regions else (None, [])
        evidence[name] = Evidence(confidence=fields[key].confidence or 0, page=page, polygon=polygon)
    return found


def to_invoice(result: AnalyzeResult) -> tuple[CanonicalInvoice, dict[str, Evidence]]:
    fields = result.documents[0].fields or {} if result.documents else {}
    evidence: dict[str, Evidence] = {}
    data = read(fields, HEADER, evidence)
    for name, (key, names) in LISTS.items():
        data[name] = []
        for item in fields[key].value_array or [] if key in fields else []:
            row_evidence: dict[str, Evidence] = {}
            row = read(item.value_object or {}, names, row_evidence)
            if not {"rate", "amount"} & names.keys() <= row.keys():
                continue
            withheld = name == "tax_lines" and row["amount"] < 0
            target = "irpf" if withheld else f"{name}.{len(data[name])}"
            evidence |= {f"{target}.{path}": proof for path, proof in row_evidence.items()}
            data |= {"irpf": row} if withheld else {name: [*data[name], row]}
    payments = fields["PaymentDetails"].value_array or [] if "PaymentDetails" in fields else []
    data |= read(payments[0].value_object or {}, {"iban": "IBAN"}, evidence) if payments else {}
    total = fields.get("InvoiceTotal") or fields.get("SubTotal")
    money = total.value_currency if total else None
    if money and (code := money.currency_code or ("EUR" if money.currency_symbol == "€" else None)):
        data["currency"], evidence["currency"] = code, evidence.get("total") or evidence["subtotal"]
    return CanonicalInvoice.model_validate(data), evidence


async def analyze(client: DocumentIntelligenceClient, document: bytes) -> AnalyzeResult:
    poller = await client.begin_analyze_document(
        MODEL, BytesIO(document), locale=LOCALE, content_type="application/octet-stream"
    )
    return await poller.result()


async def attacked(client: ContentSafetyClient, text: str) -> bool:
    chunks = [text[start : start + CHUNK] for start in range(0, max(len(text), 1), CHUNK - OVERLAP)]
    for first in range(0, len(chunks), DOCUMENTS):
        body = {"userPrompt": "", "documents": chunks[first : first + DOCUMENTS]}
        response = await client.send_request(HttpRequest("POST", SHIELD, json=body))
        response.raise_for_status()
        if any(document["attackDetected"] for document in response.json()["documentsAnalysis"]):
            return True
    return False
