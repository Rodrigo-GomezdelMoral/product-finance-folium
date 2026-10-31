import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from agent_framework import BaseChatClient, ChatResponse, ChatResponseUpdate, Content
from azure.ai.documentintelligence.models import AnalyzeResult

RECORDED = json.loads((Path(__file__).parent / "doubles.json").read_text("utf-8"))
READ_SECONDS, MODEL_SECONDS, ANSWER = 7.5, 4.0, RECORDED["answer"]


def reader(vendors: Mapping[str, str]) -> Callable[[str], Awaitable[AnalyzeResult]]:
    async def analyze(invoice_id: str) -> AnalyzeResult:
        await asyncio.sleep(READ_SECONDS)
        data = json.loads(json.dumps(RECORDED["analyze"]))
        fields, n = data["documents"][0]["fields"], int(hashlib.sha256(invoice_id.encode()).hexdigest(), 16)
        tax_id, back = sorted(vendors)[n % len(vendors)], timedelta(days=8 * (n // len(vendors) % 1000))
        for name, value in {"VendorTaxId": tax_id, "VendorName": vendors[tax_id], "InvoiceId": invoice_id}.items():
            fields[name] |= {"valueString": value, "content": value}
        fields["InvoiceDate"]["valueDate"] = str(date.fromisoformat(fields["InvoiceDate"]["valueDate"]) - back)
        return AnalyzeResult(data)

    return analyze


class Model(BaseChatClient[Any]):
    def _inner_get_response(self, **kwargs: Any) -> Any:
        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            await asyncio.sleep(MODEL_SECONDS)
            yield ChatResponseUpdate(role="assistant", contents=[Content.from_text(ANSWER)], model="load-double")

        return ChatResponse.from_update_generator(updates())
