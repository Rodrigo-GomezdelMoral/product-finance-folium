import asyncio
import base64
import hashlib
import json
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from functools import partial
from secrets import token_hex
from typing import Annotated, Any, Literal

from agent_framework import AgentSession
from agent_framework.exceptions import ChatClientException
from agent_framework.foundry import FoundryChatClient
from agent_framework_azure_cosmos import CosmosCheckpointStorage, CosmosHistoryProvider
from azure.ai.contentsafety.aio import ContentSafetyClient
from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.core.exceptions import AzureError
from azure.servicebus import ServiceBusMessage
from azure.servicebus.aio import AutoLockRenewer
from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import doubles, extract, telemetry
from app.agents import BRIEF, assistant, normalizer
from app.config import clients, settings
from app.models import CanonicalInvoice, Invoice, ReviewDecision, Status
from app.rules import duplicates
from app.store import Record, Store
from app.telemetry import event
from app.worker import Runtime, candidates, consume, new_id, process
from app.workflow import CHECKPOINT_TYPES, Services, resume, step

CLERK, LEAD, OID = "Invoice.Process", "Invoice.Approve", "http://schemas.microsoft.com/identity/claims/objectidentifier"
TYPES = {b"%PDF-": "application/pdf", b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}
MAX_FILES, MAX_BYTES, CONSUMERS = 20, 10 * 1024 * 1024, 4
LISTED: dict[str, Any] = {"id": True, "sha256": True, "status": True, "findings": True, "data": BRIEF["data"]}


class Principal(BaseModel):
    id: str
    name: str
    roles: set[str]


class Review(BaseModel):
    action: Literal["approve", "reject", "send_to_lead"]
    reason: str | None = Field(None, max_length=500)
    data: CanonicalInvoice | None = None
    review_seconds: float | None = None


class Ask(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation: str | None = None


class Feedback(BaseModel):
    helpful: bool
    about: str | None = Field(None, max_length=64)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    telemetry.configure()
    config = settings()
    async with clients(config) as azure, AsyncExitStack() as stack:
        endpoint, credential = config.foundry_account_endpoint, azure.credential
        store, box = Store(azure.database, azure.blobs), azure.database.get_container_client
        documents = await stack.enter_async_context(DocumentIntelligenceClient(endpoint, credential))
        safety = await stack.enter_async_context(ContentSafetyClient(endpoint, credential))
        chat = FoundryChatClient(credential=credential)

        async def analyze(invoice_id: str) -> AnalyzeResult:
            return await extract.analyze(documents, await store.fetch("originals", invoice_id) or b"")

        saved = CosmosCheckpointStorage(container_client=box("checkpoints"), allowed_checkpoint_types=CHECKPOINT_TYPES)
        shield, vendors = partial(extract.attacked, safety), await store.vendors()
        load = config.environment == "staging" and config.doubles == "load"
        reader, model = doubles.reader(vendors) if load else analyze, doubles.Model() if load else chat
        workflow = Services(reader, shield, normalizer(model), vendors, partial(candidates, store), saved)
        history = CosmosHistoryProvider(container_client=box("conversations"))
        queue = await stack.enter_async_context(azure.bus.get_queue_sender(config.queue))

        async def send(ids: list[str]) -> None:
            await queue.send_messages([ServiceBusMessage(item, message_id=item) for item in ids])

        app.state.runtime = Runtime(store, workflow, send, assistant(chat, store, history), history)
        renewer = AutoLockRenewer(max_lock_renewal_duration=300)
        stack.push_async_callback(renewer.close)
        receiver = partial(azure.bus.get_queue_receiver, config.queue, auto_lock_renewer=renewer)
        app.state.workers = [asyncio.create_task(consume(app.state.runtime, receiver)) for _ in range(CONSUMERS)]
        yield
        for task in app.state.workers:
            task.cancel()


app = FastAPI(title="Folium", lifespan=lifespan)


def principal(x_ms_client_principal: Annotated[str | None, Header()] = None) -> Principal:
    try:
        data = json.loads(base64.b64decode(x_ms_client_principal or ""))
        claims = [(claim["typ"], claim["val"]) for claim in data["claims"]]
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(401, "sign in required") from error
    roles, found = {val for typ, val in claims if typ in (data.get("role_typ"), "roles")}, dict(claims)
    return Principal(id=found.get(OID) or found.get("oid") or "", name=found.get("name") or "", roles=roles)


def member(*roles: str) -> Callable[[Principal], Principal]:
    def check(user: Annotated[Principal, Depends(principal)]) -> Principal:
        if not user.roles & set(roles):
            raise HTTPException(403, f"requires the role {' or '.join(roles)}")
        return user

    return check


def runtime(request: Request) -> Runtime:
    current: Runtime = request.app.state.runtime
    return current


Clerk = Annotated[Principal, Depends(member(CLERK, LEAD))]
Lead = Annotated[Principal, Depends(member(LEAD))]
Rt = Annotated[Runtime, Depends(runtime)]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


def listed(record: Record) -> dict[str, Any]:
    return record.invoice.model_dump(mode="json", include=LISTED) | {"name": record.name}


async def found(rt: Runtime, invoice_id: str) -> Record:
    if (record := await rt.store.load(invoice_id)) is None:
        raise HTTPException(404, "no such invoice")
    return record


def owner(user: Principal) -> str:
    return hashlib.sha256(user.id.encode()).hexdigest()[:12]


@app.exception_handler(AzureError)
async def unavailable(request: Request, error: AzureError) -> JSONResponse:
    return JSONResponse({"detail": "a dependency is unavailable; retry shortly"}, 503, {"Retry-After": "10"})


@app.get("/healthz")
async def health(request: Request) -> JSONResponse:
    alive = all(not task.done() for task in getattr(request.app.state, "workers", []))
    return JSONResponse({"status": "ok" if alive else "consumer stopped"}, 200 if alive else 503)


@app.get("/api/me")
async def me(user: Annotated[Principal, Depends(principal)]) -> dict[str, Any]:
    return user.model_dump(include={"name", "roles"})


@app.post("/api/invoices", status_code=202)
async def upload(files: list[UploadFile], user: Clerk, rt: Rt) -> list[dict[str, Any]]:
    if len(files) > MAX_FILES or any((file.size or 0) > MAX_BYTES for file in files):
        raise HTTPException(413, f"at most {MAX_FILES} files of 10 MB each")
    contents = [await file.read() for file in files]
    kinds = [next((kind for magic, kind in TYPES.items() if content.startswith(magic)), "") for content in contents]
    if not all(kinds):
        raise HTTPException(415, "only PDF, JPEG and PNG invoices are accepted")
    records, now = [], datetime.now(UTC)
    try:
        for index, (file, content, kind) in enumerate(zip(files, contents, kinds, strict=True)):
            invoice = Invoice(id=new_id(now, index), sha256=hashlib.sha256(content).hexdigest())
            same = duplicates(invoice, [item.invoice for item in await rt.store.candidates(invoice, invoice.id)])
            invoice = step(invoice.model_copy(update={"findings": same}), "uploaded", user.name, file=file.filename)
            records.append(Record(invoice=invoice, name=file.filename or invoice.id, media_type=kind))
            await rt.store.create(records[-1], content)
            event("invoice_uploaded", invoice=invoice.id, size=len(content), duplicate=bool(same))
        await rt.send([record.invoice.id for record in records])
    except AzureError:
        for record in records:
            await process(rt, record.invoice.id, AzureError("the invoice was not queued"))
        raise
    return [listed(record) for record in records]


@app.get("/api/invoices")
async def invoices(user: Clerk, rt: Rt, status: Status | None = None) -> list[dict[str, Any]]:
    return [listed(record) for record in await rt.store.records(100, status=status)]


@app.get("/api/invoices/{invoice_id}")
async def invoice(invoice_id: str, user: Clerk, rt: Rt) -> dict[str, Any]:
    record = await found(rt, invoice_id)
    return record.invoice.model_dump(mode="json") | record.model_dump(include={"name", "media_type", "batch"})


@app.get("/api/invoices/{invoice_id}/original")
async def original(invoice_id: str, user: Clerk, rt: Rt) -> Response:
    record = await found(rt, invoice_id)
    return Response(await rt.store.fetch("originals", invoice_id), media_type=record.media_type)


@app.post("/api/invoices/{invoice_id}/review")
async def review(invoice_id: str, body: Review, user: Clerk, rt: Rt) -> dict[str, Any]:
    record = await found(rt, invoice_id)
    if record.request is None or record.invoice.status not in (Status.ready, Status.with_lead):
        raise HTTPException(409, "the invoice is not waiting for review")
    decision = ReviewDecision(by=user.name, lead=LEAD in user.roles, **body.model_dump(exclude={"review_seconds"}))
    result = await resume(invoice_id, record.request, decision, rt.services)
    requests = result.get_request_info_events() if result else []
    if not (outputs := (result.get_outputs() if result else []) or [item.data.invoice for item in requests]):
        raise HTTPException(409, "the review request is no longer pending")
    pending = requests[0].request_id if requests else None
    if (saved := await rt.store.save(record.model_copy(update={"invoice": outputs[0], "request": pending}))) is None:
        raise HTTPException(409, "the invoice changed; reload it")
    corrections = [item for item in saved.invoice.timeline if item.name == "corrected"]
    for item in corrections[sum(item.name == "corrected" for item in record.invoice.timeline) :]:
        event("field_corrected", invoice=invoice_id, field=item.detail["field"])
    if saved.invoice.status == Status.approved:
        event("invoice_approved", invoice=invoice_id, review_seconds=body.review_seconds, corrections=len(corrections))
    return saved.invoice.model_dump(mode="json")


@app.post("/api/exports")
async def export(user: Lead, rt: Rt, key: Key) -> dict[str, Any]:
    batch_id, now = hashlib.sha256(key.encode()).hexdigest()[:16], datetime.now(UTC).isoformat()
    if (batch := await rt.store.read("exports", batch_id)) is None:
        if not (ids := [record.invoice.id for record in await rt.store.records(status=Status.approved)]):
            raise HTTPException(409, "no approved invoices to export")
        new = {"id": batch_id, "created_at": now, "by": user.name, "invoices": ids}
        batch = await rt.store.write("exports", new) or await rt.store.read("exports", batch_id) or new
    for record in [await rt.store.load(invoice_id) for invoice_id in batch["invoices"]]:
        if record and record.invoice.status == Status.approved:
            sent = step(
                record.invoice.model_copy(update={"status": Status.exported}), "exported", user.name, batch=batch_id
            )
            if await rt.store.save(record.model_copy(update={"invoice": sent, "batch": batch_id})):
                event("invoice_exported", invoice=record.invoice.id, batch=batch_id)
    invoices = [record.invoice for record in await rt.store.records(batch=batch_id)]
    return await rt.store.export(batch, invoices, rt.services.vendors)


@app.get("/api/exports/{batch_id}")
async def exported(batch_id: str, user: Lead, rt: Rt, format: Literal["csv", "json"] = "json") -> Response:
    if (content := await rt.store.fetch("exports", f"folium-{batch_id}.{format}")) is None:
        raise HTTPException(404, "no such export")
    return Response(content, media_type="text/csv" if format == "csv" else "application/json")


@app.post("/api/chat")
async def chat(body: Ask, user: Clerk, rt: Rt) -> StreamingResponse:
    mine = owner(user)
    session = (
        body.conversation if body.conversation and body.conversation.startswith(mine) else f"{mine}-{token_hex(4)}"
    )
    stream = rt.assistant.run(body.message, stream=True, session=AgentSession(session_id=session))

    async def text() -> AsyncIterator[str]:
        try:
            async for update in stream:
                yield update.text
        except ChatClientException:
            yield "The assistant is unavailable right now; try again in a minute."

    return StreamingResponse(text(), media_type="text/plain; charset=utf-8", headers={"X-Conversation": session})


@app.get("/api/conversations")
async def conversations(user: Clerk, rt: Rt) -> list[dict[str, Any]]:
    history, listing = rt.history, list[dict[str, Any]]()
    for session in [item for item in await history.list_sessions() if item.startswith(owner(user))] if history else []:
        messages = await history.get_messages(session) if history else []
        turns = [{"role": item.role, "text": item.text} for item in messages if item.text]
        listing.append({"id": session, "title": turns[0]["text"][:80] if turns else "", "turns": turns})
    return listing


@app.post("/api/feedback", status_code=204)
async def feedback(body: Feedback, user: Clerk) -> None:
    event("feedback", helpful=body.helpful, about=body.about)


app.mount("/", StaticFiles(directory="web/dist", html=True, check_dir=False), name="web")
