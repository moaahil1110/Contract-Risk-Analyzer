"""Embedding model configuration and offline-mode helpers."""

import os
from pathlib import Path
from typing import Dict, Any

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def embedding_offline_enabled() -> bool:
    return os.getenv("EMBEDDING_OFFLINE", "false").lower() == "true"


def apply_embedding_offline_env() -> None:
    if embedding_offline_enabled():
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_HUB_OFFLINE", "1")


def embedding_model_source() -> str:
    model_path = os.getenv("EMBEDDING_MODEL_PATH", "").strip()
    if model_path:
        return model_path
    return os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip() or DEFAULT_EMBEDDING_MODEL


def validate_embedding_config() -> Dict[str, Any]:
    apply_embedding_offline_env()
    source = embedding_model_source()
    offline = embedding_offline_enabled()
    configured_path = os.getenv("EMBEDDING_MODEL_PATH", "").strip()

    if configured_path and not Path(configured_path).exists():
        raise RuntimeError(f"EMBEDDING_MODEL_PATH does not exist: {configured_path}")

    return {
        "embedding_offline": offline,
        "embedding_model_source": source,
        "embedding_model_path": configured_path or None,
        "transformers_offline": os.getenv("TRANSFORMERS_OFFLINE"),
        "hf_hub_offline": os.getenv("HF_HUB_OFFLINE"),
    }
