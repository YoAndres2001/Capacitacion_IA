"""Formateador de logs JSON con contexto de petición (RNF-28)."""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
company_id_var: ContextVar[str] = ContextVar("company_id", default="")

_SENSITIVE = {"password", "token", "authorization", "secret", "api_key", "refresh"}


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "user_id": user_id_var.get(),
            "company_id": company_id_var.get(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in getattr(record, "__dict__", {}).items():
            if key.startswith("_") or key in logging.LogRecord.__dict__:
                continue
            if key in {
                "args", "msg", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno",
                "funcName", "created", "msecs", "relativeCreated", "thread",
                "threadName", "processName", "process", "name", "taskName",
            }:
                continue
            if any(s in key.lower() for s in _SENSITIVE):
                payload[key] = "***"
            else:
                payload[key] = _safe(value)

        return json.dumps(payload, ensure_ascii=False, default=str)


def _safe(value: object) -> object:
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    return str(value)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"nexora.{name}")
