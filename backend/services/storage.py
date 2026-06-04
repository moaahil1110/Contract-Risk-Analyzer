"""Durable PDF storage helpers for web and worker processes."""

import os
from pathlib import Path
from typing import Optional

from db.supabase_client import get_supabase_client, is_supabase_configured

STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "contracts")
LOCAL_UPLOAD_ROOT = Path(os.getenv("LOCAL_UPLOAD_ROOT", Path(__file__).resolve().parent.parent / "uploads"))


def is_dev_mode() -> bool:
    return os.getenv("DEV_MODE", "false").lower() == "true"


def build_storage_path(user_id: Optional[str], contract_id: str) -> str:
    owner = user_id or "anonymous"
    return f"{owner}/{contract_id}/original.pdf"


async def save_contract_file(
    *,
    contract_id: str,
    user_id: Optional[str],
    filename: str,
    file_bytes: bytes,
    mime_type: Optional[str],
) -> str:
    storage_path = build_storage_path(user_id, contract_id)

    if is_supabase_configured() and not is_dev_mode():
        client = get_supabase_client()
        if not client:
            raise RuntimeError("Supabase client is not available")
        client.storage.from_(STORAGE_BUCKET).upload(
            storage_path,
            file_bytes,
            file_options={
                "content-type": mime_type or "application/pdf",
                "upsert": "true",
            },
        )
        return storage_path

    local_dir = LOCAL_UPLOAD_ROOT / contract_id
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / (Path(filename).name or "original.pdf")
    local_path.write_bytes(file_bytes)
    return f"local://{local_path}"


async def load_contract_file(storage_path: str) -> bytes:
    if storage_path.startswith("local://"):
        return Path(storage_path.removeprefix("local://")).read_bytes()

    if is_supabase_configured():
        client = get_supabase_client()
        if not client:
            raise RuntimeError("Supabase client is not available")
        data = client.storage.from_(STORAGE_BUCKET).download(storage_path)
        if isinstance(data, bytes):
            return data
        if hasattr(data, "content"):
            return data.content
        return bytes(data)

    path = Path(storage_path)
    if path.exists():
        return path.read_bytes()

    raise FileNotFoundError(f"Contract file not found: {storage_path}")


async def delete_contract_file(storage_path: str) -> bool:
    if not storage_path:
        return False

    if storage_path.startswith("local://"):
        path = Path(storage_path.removeprefix("local://"))
        if path.exists():
            path.unlink()
        return True

    if is_supabase_configured():
        client = get_supabase_client()
        if not client:
            raise RuntimeError("Supabase client is not available")
        client.storage.from_(STORAGE_BUCKET).remove([storage_path])
        return True

    path = Path(storage_path)
    if path.exists():
        path.unlink()
    return True
