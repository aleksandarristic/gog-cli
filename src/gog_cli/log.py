"""Logging helpers and secret redaction."""

from __future__ import annotations

import logging
import re

_BEARER_RE = re.compile(r"(Bearer\s+)\S+", re.IGNORECASE)
_PARAM_RE = re.compile(r"((?:access_token|refresh_token|code)=)[^&\s\"']+")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def redact(text: str) -> str:
    text = _BEARER_RE.sub(r"\1[REDACTED]", text)
    text = _PARAM_RE.sub(r"\1[REDACTED]", text)
    return text
