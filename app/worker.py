import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import token_hex
from typing import Any

from agent_framework import Agent
from agent_framework.exceptions import WorkflowException
from agent_framework_azure_cosmos import CosmosHistoryProvider
from azure.core.exceptions import AzureError
from azure.servicebus.aio import ServiceBusReceiver

from app.models import Invoice, Status, leaves
from app.store import Store
from app.telemetry import LOGGER, event
from app.workflow import Services, build, step

ERRORS = (AzureError, WorkflowException, TimeoutError, ValueError, KeyError, ArithmeticError)
BUSY, DELIVERIES, PATIENCE, WINDOW = {Status.queued, Status.processing}, 5, 40, timedelta(minutes=5)


@dataclass
class Runtime:
    store: Store
    services: Services
    send: Callable[[list[str]], Awaitable[None]]
    assistant: Agent[Any]
    history: CosmosHistoryProvider | None = None


def new_id(at: datetime, index: int = 0) -> str:
    return f"{at:%Y%m%d%H%M%S%f}{index:02}{token_hex(1)}"


async def candidates(store: Store, invoice: Invoice) -> list[Invoice]:
    for _ in range(PATIENCE):
        found = await store.candidates(invoice, new_id(datetime.now(UTC) - WINDOW)[:20])
        if not any(other.invoice.status in BUSY for other in found):
            return [other.invoice for other in found]
        await asyncio.sleep(0.5)
    raise TimeoutError("an earlier upload is still being processed")


async def process(runtime: Runtime, invoice_id: str, error: Exception | None = None) -> None:
    record = await runtime.store.load(invoice_id)
    if record is None or record.invoice.status not in BUSY:
        return
    status = Status.failed if error else Status.processing
    claim = record.invoice.model_copy(update={"status": status})
    claim = step(claim, "failed", error=type(error).__name__) if error else claim
    if (claimed := await runtime.store.save(record.model_copy(update={"invoice": claim}))) is None or error:
        return
    result = await build(invoice_id, runtime.services).run(claim.model_copy(update={"findings": []}))
    [request] = result.get_request_info_events()
    invoice: Invoice = request.data.invoice
    if await runtime.store.save(claimed.model_copy(update={"invoice": invoice, "request": request.request_id})):
        seconds = (invoice.timeline[-1].at - invoice.timeline[0].at).total_seconds()
        count = sum(value is not None for value in leaves(invoice.data.model_dump()).values())
        standard = record.media_type == "application/pdf" and invoice.pages <= 3
        event(
            "invoice_ready", invoice=invoice_id, seconds=seconds, pages=invoice.pages, standard=standard, fields=count
        )


async def consume(runtime: Runtime, receiver: Callable[[], ServiceBusReceiver]) -> None:
    async with receiver() as messages:
        async for message in messages:
            try:
                await process(runtime, str(message))
                await messages.complete_message(message)
            except ERRORS as error:
                LOGGER.warning("invoice %s: %s", message, type(error).__name__)
                with suppress(*ERRORS):
                    if (message.delivery_count or 0) + 1 < DELIVERIES:
                        await messages.abandon_message(message)
                        continue
                    await process(runtime, str(message), error)
                    await messages.dead_letter_message(message, reason=type(error).__name__)
