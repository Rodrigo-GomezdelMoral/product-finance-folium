import asyncio
import json
from pathlib import Path

from azure.core.exceptions import ResourceExistsError
from azure.cosmos import PartitionKey

from app.config import Clients, clients, settings

DATA = Path(__file__).parent.parent / "data" / "vendors.json"
KEYS = {"invoices": "/id", "audit": "/invoice_id", "vendors": "/tax_id", "exports": "/id"}
KEYS |= {"conversations": "/session_id", "checkpoints": "/workflow_name"}


async def seed(azure: Clients, create: bool) -> int:
    if create:
        await azure.cosmos.create_database_if_not_exists(azure.database.id)
        for name, key in KEYS.items():
            await azure.database.create_container_if_not_exists(name, PartitionKey(key))
        for name in ("originals", "exports"):
            try:
                await azure.blobs.create_container(name)
            except ResourceExistsError:
                continue
    vendors = json.loads(DATA.read_text("utf-8"))
    for vendor in vendors:
        await azure.database.get_container_client("vendors").upsert_item(vendor | {"id": vendor["tax_id"]})
    return len(vendors)


async def main() -> None:
    config = settings()
    async with clients(config) as azure:
        print(await seed(azure, create=config.cosmos_key is not None), "vendors seeded")


if __name__ == "__main__":
    asyncio.run(main())
