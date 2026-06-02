"""Small JSON logging helper for worker observability."""

import json
import logging
from typing import Any


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    payload = {"event": event, **{key: value for key, value in fields.items() if value is not None}}
    logger.log(level, json.dumps(payload, default=str, sort_keys=True))
