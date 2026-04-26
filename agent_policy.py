"""Execution policy for delegate browser tools."""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse


READ_TOOLS = {"observe", "list_tabs", "wait", "http_get", "finish"}
MUTATION_TOOLS = {"click", "type_text", "press_key", "run_browser_code"}
NAVIGATION_TOOLS = {"navigate", "switch_tab", "scroll"}
VALID_POLICIES = {"autonomous", "confirm", "dry-run"}


@dataclass
class Policy:
    mode: str = "autonomous"
    allow_domains: set[str] = field(default_factory=set)
    deny_domains: set[str] = field(default_factory=set)

    def __post_init__(self):
        if self.mode not in VALID_POLICIES:
            raise ValueError(f"policy must be one of {sorted(VALID_POLICIES)}")

    @classmethod
    def from_env(cls, mode="autonomous"):
        import os
        return cls(
            mode=mode,
            allow_domains=_split_domains(os.environ.get("BH_AGENT_ALLOW_DOMAINS", "")),
            deny_domains=_split_domains(os.environ.get("BH_AGENT_DENY_DOMAINS", "")),
        )

    def check(self, tool_name: str, args: dict) -> tuple[bool, str]:
        url = args.get("url") or args.get("href") or ""
        if url:
            host = (urlparse(url).hostname or "").lower()
            if self.deny_domains and _domain_matches(host, self.deny_domains):
                return False, f"domain denied by policy: {host}"
            if self.allow_domains and host and not _domain_matches(host, self.allow_domains):
                return False, f"domain not in allowlist: {host}"

        if self.mode == "dry-run" and tool_name != "finish":
            return False, f"dry-run: would execute {tool_name}"

        if self.mode == "confirm" and (tool_name in MUTATION_TOOLS or tool_name == "navigate"):
            if not _confirm(tool_name, args):
                return False, f"user denied {tool_name}"

        return True, "ok"


def _split_domains(raw: str) -> set[str]:
    return {d.strip().lower().lstrip(".") for d in raw.split(",") if d.strip()}


def _domain_matches(host: str, domains: set[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def _confirm(tool_name: str, args: dict) -> bool:
    preview = {k: v for k, v in args.items() if k not in {"text", "code"}}
    if "text" in args:
        preview["text"] = _short(args["text"])
    if "code" in args:
        preview["code"] = _short(args["code"])
    try:
        ans = input(f"delegate wants to run {tool_name} {preview}. allow? [y/N] ").strip().lower()
    except EOFError:
        return False
    return ans.startswith("y")


def _short(value, limit=160):
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "..."
