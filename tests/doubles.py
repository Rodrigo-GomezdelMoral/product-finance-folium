import asyncio
import json
import sys
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from functools import partial
from pathlib import Path
from secrets import token_hex
from typing import Any, cast

import agent_framework as af
from agent_framework import BaseChatClient, ChatResponse, Content, FileCheckpointStorage, Message
from azure.ai.documentintelligence.models import AnalyzeResult

from app.agents import normalizer
from app.models import Invoice
from app.store import Doc, Record, Store, to_record
from app.worker import BUSY, candidates
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
    ) -> Any:
        self.prompts.append("\n".join(message.text for message in messages))
        answer = self.answers.pop(0)

        async def updates() -> AsyncIterator[af.ChatResponseUpdate]:
            if isinstance(answer, Exception):
                raise answer
            yield af.ChatResponseUpdate(role="assistant", contents=[Content.from_text(answer)], model=self.model)

        reply = ChatResponse.from_update_generator
        return af.ResponseStream(updates(), finalizer=ChatResponse.from_updates) if stream else reply(updates())


class Recorded(Replay):
    def _inner_get_response(self, *, messages: Sequence[Message], **kwargs: Any) -> Any:
        prompt = "\n".join(message.text for message in messages)
        self.answers = [next(item["answer"] for item in RECORDED.values() if item["analyze"]["content"][:60] in prompt)]
        return super()._inner_get_response(messages=messages, **kwargs)


MATCH: dict[str, Callable[[Record], list[str | None]]] = {"status": lambda item: [item.invoice.status]}
MATCH |= {"batch": lambda item: [item.batch]}
MATCH |= {"tax_id": lambda item: [item.invoice.vendor, item.invoice.data.vendor_tax_id]}


class MemoryStore(Store):
    def __init__(self) -> None:
        self.docs, self.files = defaultdict[str, dict[str, Doc]](dict), dict[str, bytes]()
        self.docs["vendors"] = {item["tax_id"]: item | {"id": item["tax_id"]} for item in json.loads(DATA.read_text())}

    async def read(self, container: str, item: str) -> Doc | None:
        return cast(Doc | None, json.loads(json.dumps(self.docs[container].get(item))))

    async def write(self, container: str, doc: Doc, etag: str | None = None) -> Doc | None:
        stored = self.docs[container].get(doc["id"])
        if (stored is None) != (etag is None) or (stored and stored["_etag"] != etag):
            return None
        self.docs[container][doc["id"]] = json.loads(json.dumps(doc)) | {"_etag": token_hex(4)}
        return await self.read(container, doc["id"])

    async def remove(self, container: str, item: str, key: str | None = None) -> None:
        del self.docs[container][item]

    async def query(self, container: str, sql: str, **params: object) -> list[Doc]:
        found = self.docs[container].values()
        return [dict(doc) for doc in found if all(doc.get(key) == value for key, value in params.items())]

    async def put(self, container: str, name: str, content: bytes, kind: str, **metadata: str) -> None:
        assert container == "exports" or f"{container}/{name}" not in self.files
        self.files[f"{container}/{name}"] = content

    async def fetch(self, container: str, name: str) -> bytes | None:
        return self.files.get(f"{container}/{name}")

    async def drop(self, container: str, name: str) -> None:
        self.files.pop(f"{container}/{name}", None)

    async def records(self, top: int = 0, **filters: str | None) -> list[Record]:
        found = [to_record(doc) for _, doc in sorted(self.docs["invoices"].items(), reverse=True)]
        return [item for item in found if all(v in MATCH[k](item) for k, v in filters.items() if v)][: top or None]

    async def candidates(self, invoice: Invoice, since: str) -> list[Record]:
        ids = {invoice.vendor, invoice.data.vendor_tax_id} - {None}

        def match(other: Invoice) -> bool:
            same = other.sha256 == invoice.sha256 or {other.vendor, other.data.vendor_tax_id} & ids
            return other.id < invoice.id and bool(same or (other.id > since and other.status in BUSY))

        return [item for item in await self.records() if match(item.invoice)]


def recorded(store: Store, checkpoints: af.CheckpointStorage) -> Services:
    async def analyze(invoice_id: str) -> AnalyzeResult:
        record = await store.load(invoice_id)
        return AnalyzeResult(RECORDED[record.name if record else invoice_id]["analyze"])

    async def shield(text: str) -> bool:
        return any(record["attack"] for record in RECORDED.values() if record["analyze"]["content"] == text)

    client = Recorded([], next(record["model"] for record in RECORDED.values() if record["model"]))
    return Services(analyze, shield, normalizer(client), VENDORS, partial(candidates, store), checkpoints)


def services(folder: Path, file: str, client: Replay | None = None) -> Services:
    record, checkpoints = RECORDED[file], FileCheckpointStorage(folder, allowed_checkpoint_types=CHECKPOINT_TYPES)
    built = recorded(MemoryStore(), checkpoints)
    built.normalizer = normalizer(client or Replay([record["answer"]] if record["answer"] else [], record["model"]))
    return built


async def start(folder: Path, file: str) -> None:
    result = await build(file, services(folder, file)).run(Invoice(id=file, sha256=RECORDED[file]["sha256"]))
    print(result.get_request_info_events()[0].request_id, flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(start(Path(sys.argv[1]), sys.argv[2]))
