"""Logging with a request / session id attached to every line."""

import logging
from contextvars import ContextVar

request_id: ContextVar[str] = ContextVar("request_id", default="-")
session_id: ContextVar[str] = ContextVar("session_id", default="-")


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        record.session_id = session_id.get()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.addFilter(_ContextFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s req=%(request_id)s sess=%(session_id)s %(message)s"
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
