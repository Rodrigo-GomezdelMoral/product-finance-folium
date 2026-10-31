from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from os import environ

from azure.cosmos.aio import CosmosClient, DatabaseProxy
from azure.identity.aio import DefaultAzureCredential
from azure.servicebus.aio import ServiceBusClient
from azure.storage.blob.aio import BlobServiceClient
from pydantic import BaseModel


class Settings(BaseModel):
    environment: str = "local"
    doubles: str = ""
    cosmos_endpoint: str
    cosmos_key: str | None = None
    storage: str
    servicebus: str
    foundry_account_endpoint: str = ""
    database: str = "folium"
    queue: str = "invoices"


def settings() -> Settings:
    return Settings.model_validate({key.lower(): value for key, value in environ.items()})


@dataclass
class Clients:
    credential: DefaultAzureCredential
    cosmos: CosmosClient
    database: DatabaseProxy
    blobs: BlobServiceClient
    bus: ServiceBusClient


@asynccontextmanager
async def clients(config: Settings) -> AsyncIterator[Clients]:
    async with AsyncExitStack() as stack:
        credential = await stack.enter_async_context(DefaultAzureCredential())
        cosmos = await stack.enter_async_context(CosmosClient(config.cosmos_endpoint, config.cosmos_key or credential))
        local = "=" in config.storage
        blobs = BlobServiceClient.from_connection_string(config.storage) if local else None
        blobs = await stack.enter_async_context(blobs or BlobServiceClient(config.storage, credential))
        bus = ServiceBusClient.from_connection_string(config.servicebus) if "=" in config.servicebus else None
        bus = await stack.enter_async_context(bus or ServiceBusClient(config.servicebus, credential))
        yield Clients(credential, cosmos, cosmos.get_database_client(config.database), blobs, bus)
