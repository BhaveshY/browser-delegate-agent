import sys
from types import SimpleNamespace
from unittest.mock import patch

import delegate
from agent_policy import Policy
from agent_provider import ProviderConfig, _collect_stream, resolve_api_key, z_ai_extra_body
from agent_tools import BrowserToolRunner, tool_schemas
from agent_transcript import redact


def test_resolve_api_key_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("BH_AGENT_API_KEY", "default-key")
    monkeypatch.setenv("CUSTOM_KEY", "custom-key")

    assert resolve_api_key("CUSTOM_KEY") == ("custom-key", "CUSTOM_KEY")


def test_z_ai_extra_body_only_for_zai():
    assert z_ai_extra_body(ProviderConfig(base_url="https://api.z.ai/api/paas/v4/")) == {"thinking": {"type": "enabled"}}
    assert z_ai_extra_body(ProviderConfig(base_url="https://example.com/v1")) == {}


def test_collect_stream_reassembles_tool_call():
    stream = [
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=[
            SimpleNamespace(index=0, id="call_1", type="function", function=SimpleNamespace(name="fin", arguments='{"summ'))
        ]))]),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=[
            SimpleNamespace(index=0, id=None, type=None, function=SimpleNamespace(name="ish", arguments='ary":"ok"}'))
        ]))]),
    ]

    msg = _collect_stream(stream).choices[0].message

    assert msg["tool_calls"][0]["function"]["name"] == "finish"
    assert msg["tool_calls"][0]["function"]["arguments"] == '{"summary":"ok"}'


def test_policy_dry_run_blocks_mutating_tool():
    allowed, reason = Policy(mode="dry-run").check("click", {"x": 1, "y": 2})

    assert not allowed
    assert "dry-run" in reason


def test_policy_denies_configured_domain():
    policy = Policy(mode="autonomous", deny_domains={"example.com"})

    allowed, reason = policy.check("navigate", {"url": "https://sub.example.com/path"})

    assert not allowed
    assert "denied" in reason


def test_tool_schemas_can_disable_code_tool():
    names = [t["function"]["name"] for t in tool_schemas(include_code=False)]

    assert "run_browser_code" not in names
    assert "observe" in names


def test_run_browser_code_blocks_dunder_escape():
    result = BrowserToolRunner().execute("run_browser_code", {"code": "print(page_info.__globals__)"})

    assert not result["ok"]
    assert "not available" in result["error"]


def test_transcript_redacts_common_secret_shapes(monkeypatch):
    monkeypatch.setenv("BH_AGENT_API_KEY", "secret-value")

    out = redact('{"Authorization":"Bearer abc.def","api_key":"secret-value"}')

    assert "secret-value" not in out
    assert "abc.def" not in out
    assert "[REDACTED]" in out


def test_delegate_loop_finishes_from_tool_call(monkeypatch):
    class FakeProvider:
        def __init__(self, config):
            self.config = config

        def completion(self, messages, tools=None):
            return SimpleNamespace(choices=[SimpleNamespace(message={
                "role": "assistant",
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "finish", "arguments": '{"summary":"done"}'},
                }],
            })])

    monkeypatch.setenv("BH_AGENT_API_KEY", "key")
    monkeypatch.setattr(delegate, "ensure_daemon", lambda: None)
    monkeypatch.setattr(delegate, "OpenAICompatibleProvider", FakeProvider)

    result = delegate.run_delegate("test", transcript=SimpleNamespace(write=lambda *a, **k: None, path=None), quiet=True)

    assert result["ok"]
    assert result["summary"] == "done"


def test_delegate_cli_reads_stdin_for_dash(monkeypatch):
    seen = {}
    def fake_run(task, **kwargs):
        seen["task"] = task
        return {"ok": True, "summary": "ok"}
    monkeypatch.setattr(delegate, "run_delegate", fake_run)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(read=lambda: "from stdin"))

    code = delegate.run_delegate_cli(["-", "--no-transcript", "--json"])

    assert code == 0
    assert seen["task"] == "from stdin"
