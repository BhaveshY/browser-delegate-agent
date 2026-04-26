"""OpenAI-compatible model client for the browser delegate agent."""
from __future__ import annotations

import os
from dataclasses import dataclass
from types import SimpleNamespace


DEFAULT_MODEL = "glm-5.1"
DEFAULT_BASE_URL = "https://api.z.ai/api/paas/v4/"
DEFAULT_API_KEY_ENVS = ("BH_AGENT_API_KEY", "ZAI_API_KEY")


@dataclass
class ProviderConfig:
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    api_key_env: str | None = None
    timeout: float = 120.0
    temperature: float = 0.2
    stream: bool = True


def resolve_api_key(api_key_env: str | None = None) -> tuple[str | None, str | None]:
    """Return (api_key, env_name) using the explicit env first, then defaults."""
    names = [api_key_env] if api_key_env else []
    names += [n for n in DEFAULT_API_KEY_ENVS if n not in names]
    for name in names:
        if name and os.environ.get(name):
            return os.environ[name], name
    return None, None


def z_ai_extra_body(config: ProviderConfig) -> dict:
    """Z.AI accepts a non-standard `thinking` body; don't send it elsewhere."""
    if "z.ai" not in config.base_url.lower():
        return {}
    thinking = os.environ.get("BH_AGENT_THINKING", "enabled").strip().lower()
    if thinking not in {"enabled", "disabled"}:
        thinking = "enabled"
    return {"thinking": {"type": thinking}}


class OpenAICompatibleProvider:
    def __init__(self, config: ProviderConfig):
        api_key, env_name = resolve_api_key(config.api_key_env)
        if not api_key:
            expected = config.api_key_env or " or ".join(DEFAULT_API_KEY_ENVS)
            raise RuntimeError(f"delegate provider API key missing; set {expected}")
        self.config = config
        self.api_key_env = env_name
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError("openai package missing; run `uv sync` or `uv tool install -e .`") from e
        self.client = OpenAI(api_key=api_key, base_url=config.base_url, timeout=config.timeout)

    def completion(self, messages, tools=None, max_tokens=None):
        kwargs = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        extra_body = z_ai_extra_body(self.config)
        if extra_body:
            kwargs["extra_body"] = extra_body
        if self.config.stream:
            kwargs["stream"] = True
            return _collect_stream(self.client.chat.completions.create(**kwargs))
        return self.client.chat.completions.create(**kwargs)


def message_to_dict(message) -> dict:
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    if isinstance(message, dict):
        return {k: v for k, v in message.items() if v is not None}
    out = {"role": getattr(message, "role", "assistant")}
    content = getattr(message, "content", None)
    if content is not None:
        out["content"] = content
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        out["tool_calls"] = [tool_call_to_dict(t) for t in tool_calls]
    return out


def tool_call_to_dict(tool_call) -> dict:
    if hasattr(tool_call, "model_dump"):
        return tool_call.model_dump(exclude_none=True)
    if isinstance(tool_call, dict):
        return {k: v for k, v in tool_call.items() if v is not None}
    fn = getattr(tool_call, "function", None)
    return {
        "id": getattr(tool_call, "id", ""),
        "type": getattr(tool_call, "type", "function"),
        "function": {
            "name": getattr(fn, "name", ""),
            "arguments": getattr(fn, "arguments", "{}"),
        },
    }


def _collect_stream(stream):
    """Collect streamed Chat Completions chunks into the shape delegate expects."""
    message = {"role": "assistant", "content": ""}
    tool_calls = {}
    for chunk in stream:
        for choice in getattr(chunk, "choices", []) or []:
            delta = getattr(choice, "delta", None)
            if not delta:
                continue
            content = getattr(delta, "content", None)
            if content:
                message["content"] += content
            for tc in getattr(delta, "tool_calls", None) or []:
                idx = getattr(tc, "index", 0)
                entry = tool_calls.setdefault(idx, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                if getattr(tc, "id", None):
                    entry["id"] = tc.id
                if getattr(tc, "type", None):
                    entry["type"] = tc.type
                fn = getattr(tc, "function", None)
                if fn:
                    if getattr(fn, "name", None):
                        entry["function"]["name"] += fn.name
                    if getattr(fn, "arguments", None):
                        entry["function"]["arguments"] += fn.arguments
    if not message["content"]:
        message.pop("content")
    if tool_calls:
        message["tool_calls"] = [tool_calls[i] for i in sorted(tool_calls)]
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])
