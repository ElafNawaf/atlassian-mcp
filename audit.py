"""Audit logging (JSONL, redacted)."""
import json
from datetime import datetime
from pathlib import Path

from config import AUDIT_LOG_PATH, get_logger

logger = get_logger("audit")
SENSITIVE_KEYS = {"token", "password", "api_key", "apiKey", "authorization", "cookie"}


def _redact(obj: object) -> object:
    if obj is None:
        return obj
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if any(s in k.lower() for s in SENSITIVE_KEYS) else _redact(v)
            for k, v in obj.items()
        }
    return obj


def audit_log(
    tool: str,
    args: object | None = None,
    result: str = "success",
    error: str | None = None,
) -> None:
    entry = {
        "tool": tool,
        "args": _redact(args),
        "result": result,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    if error:
        entry["error"] = error
    line = json.dumps(entry, default=str) + "\n"
    try:
        Path(AUDIT_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError as e:
        logger.warning("Audit write failed: path=%s error=%s", AUDIT_LOG_PATH, e)
