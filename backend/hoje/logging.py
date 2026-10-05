"""structlog JSON logging to stdout with secret redaction."""

import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

REDACTED = "[REDACTED]"
# Match whole words in snake/kebab-case keys ("new_password", "csrf_token", "recovery_codes",
# "set-cookie") but not look-alikes such as "status_code" or "token_count".
_SENSITIVE_KEY = re.compile(
    r"(^|[_-])(password|passwd|token|secret|cookie|authorization|otp|totp)s?$"
    r"|^(code|codes|mfa_code|recovery_codes?|totp_code|api_?keys?)$",
    re.IGNORECASE,
)


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            k: REDACTED if isinstance(k, str) and _SENSITIVE_KEY.search(k) else _redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [_redact(v) for v in value]
    return value


def redact_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Replace the value of any key that looks sensitive (recursively)."""
    for key in list(event_dict):
        if isinstance(key, str) and _SENSITIVE_KEY.search(key):
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _redact(event_dict[key])
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Route structlog, the stdlib root logger and uvicorn through one JSON pipeline."""
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        redact_processor,
    ]

    structlog.configure(
        processors=[
            *shared,
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "alembic"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
        lg.setLevel(level.upper())
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    # httpx logs every request URL at INFO; for integration syncs that is a vetted address and a
    # query string we do not want in the log stream.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name)
