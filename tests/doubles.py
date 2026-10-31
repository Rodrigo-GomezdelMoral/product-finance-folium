import asyncio
import json
import sys
from collections.abc import Awaitable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from agent_framework import BaseChatClient, ChatResponse, FileCheckpointStorage, Message
from azure.ai.documentintelligence.models import AnalyzeResult

from app.agents import normalizer
from app.models import Invoice
from app.workflow import CHECKPOINT_TYPES, Services, build

FIXTURES = Path(__file__).parent / "fixtures" / "recorded.json"
RECORDED: dict[str, dict[str, Any]] = json.loads(FIXTURES.read_text("utf-8")) if FIXTURES.exists() else {}
DATA = Path(__file__).parent.parent / "data" / "vendors.json"
VENDORS = {vendor["tax_id"]: vendor["name"] for vendor in json.loads(DATA.read_text("utf-8"))}


class Replay(BaseChatClient[Any]):
    def __init__(self, answers: Sequence[str | Exception], model: str = "replay") -> None:
        super().__init__()
        self.answers, self.model, self.prompts = list(answers), model, list[str]()

    def _inner_get_response(
        self, *, messages: Sequence[Message], stream: bool, options: Mapping[str, Any], **kwargs: Any
    ) -> Awaitable[ChatResponse]:
        self.prompts.append("\n".join(message.text for message in messages))
        answer = self.answers.pop(0)

        async def respond() -> ChatResponse:
            if isinstance(answer, Exception):
                raise answer
            return ChatResponse(messages=[Message(role="assistant", contents=[answer])], model=self.model)

        return respond()


def services(folder: Path, file: str, client: Replay | None = None, others: Iterable[Invoice] = ()) -> Services:
    record = RECORDED[file]
    client = client or Replay([record["answer"]] if record["answer"] else [], record["model"])

    async def analyze(invoice_id: str) -> AnalyzeResult:
        return AnalyzeResult(RECORDED[invoice_id]["analyze"])

    async def shield(text: str) -> bool:
        return bool(record["attack"])

    async def candidates(invoice: Invoice) -> list[Invoice]:
        return list(others)

    storage = FileCheckpointStorage(folder, allowed_checkpoint_types=CHECKPOINT_TYPES)
    return Services(analyze, shield, normalizer(client), VENDORS, candidates, storage)


async def start(folder: Path, file: str) -> None:
    result = await build(file, services(folder, file)).run(Invoice(id=file, sha256=RECORDED[file]["sha256"]))
    print(result.get_request_info_events()[0].request_id, flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(start(Path(sys.argv[1]), sys.argv[2]))
