"""JSONL transcripts for delegate runs."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path


SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.I),
    re.compile(r"(api[_-]?key|token|authorization|cookie|password)(['\"]?\s*[:=]\s*['\"]?)[^,'\"\s}]+", re.I),
]


def cache_dir() -> Path:
    if os.environ.get("BH_AGENT_TRANSCRIPT_DIR"):
        return Path(os.environ["BH_AGENT_TRANSCRIPT_DIR"]).expanduser()
    if os.name == "posix" and Path.home().joinpath("Library", "Caches").is_dir():
        return Path.home() / "Library" / "Caches" / "browser-harness"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "browser-harness"


class Transcript:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.path = None
        if enabled:
            d = cache_dir()
            d.mkdir(parents=True, exist_ok=True)
            self.path = d / f"delegate-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"

    def write(self, event: str, data: dict | None = None):
        if not self.enabled or not self.path:
            return
        record = {"ts": time.time(), "event": event, "data": data or {}}
        line = redact(json.dumps(record, ensure_ascii=True, default=str))
        with self.path.open("a") as f:
            f.write(line + "\n")


def redact(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(_redact_match, text)
    for name in ("BH_AGENT_API_KEY", "ZAI_API_KEY", "BROWSER_USE_API_KEY"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[REDACTED]")
    return text


def _redact_match(match):
    if match.lastindex and match.lastindex >= 2:
        return match.group(1) + match.group(2) + "[REDACTED]"
    if match.lastindex == 1:
        return match.group(1) + "[REDACTED]"
    return "[REDACTED]"
