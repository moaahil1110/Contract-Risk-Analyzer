"""Delete stored PDFs for soft-deleted contracts after a retention window."""

import asyncio
import json
import sys

from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from db.queries import get_deleted_contracts_for_cleanup  # noqa: E402
from services.storage import delete_contract_file  # noqa: E402


async def main() -> None:
    retention_days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    contracts = await get_deleted_contracts_for_cleanup(retention_days)
    deleted = []
    failed = []

    for contract in contracts:
        storage_path = contract.get("storage_path")
        try:
            if storage_path:
                await delete_contract_file(storage_path)
            deleted.append({
                "id": contract.get("id"),
                "storage_path": storage_path,
            })
        except Exception as exc:
            failed.append({
                "id": contract.get("id"),
                "storage_path": storage_path,
                "error": str(exc),
            })

    print(json.dumps({
        "retention_days": retention_days,
        "eligible_count": len(contracts),
        "deleted_count": len(deleted),
        "failed_count": len(failed),
        "deleted": deleted,
        "failed": failed,
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
