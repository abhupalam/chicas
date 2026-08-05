"""Structured JSON logging setup."""
from __future__ import annotations
import json
import logging
import traceback as _traceback
from datetime import datetime, timezone
from pathlib import Path


def get_logger(name: str, log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fh = logging.FileHandler(log_dir / "pipeline.jsonl")
        fh.setFormatter(_JsonFormatter())
        logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        logger.addHandler(sh)
    return logger


def log_event(logger: logging.Logger, level: str, event: str, **kwargs):
    """Emit a structured JSON log line.

    If called inside an active exception context and no ``traceback`` kwarg is
    supplied, the current exception's traceback is captured automatically so
    that ERROR events always contain actionable debugging information.
    """
    import sys
    payload: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        # Include severity in every line so log consumers can filter by level
        # without knowing internal event names (e.g. grep '"level": "ERROR"')
        "level": level.upper(),
        "event": event,
        **kwargs,
    }
    # For ERROR/CRITICAL calls, automatically attach the traceback of the active
    # exception if the caller hasn't already provided one. sys.exc_info()[1]
    # returns the current exception inside an except block, or None outside one —
    # so this is a no-op for normal INFO/WARNING calls.
    if level.upper() in ("ERROR", "CRITICAL") and "traceback" not in payload:
        exc = sys.exc_info()[1]
        if exc is not None:
            payload["traceback"] = _traceback.format_exc()
    getattr(logger, level.lower())(json.dumps(payload))


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()
