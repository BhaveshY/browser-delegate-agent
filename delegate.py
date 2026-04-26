"""CLI and loop for delegating browser tasks to an external model."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from admin import _install_mode, daemon_alive, ensure_daemon
from agent_policy import Policy, VALID_POLICIES
from agent_provider import DEFAULT_BASE_URL, DEFAULT_MODEL, OpenAICompatibleProvider, ProviderConfig, message_to_dict
from agent_tools import BrowserToolRunner, tool_schemas
from agent_transcript import Transcript


SYSTEM_PROMPT = """You are Browser Harness Delegate, a browser-only worker.
You complete browser tasks by calling the provided tools. You do not have shell or file access.
Use observe before deciding where to click. Prefer semantic refs from observe over raw coordinates.
Never ask for credentials or reveal cookies, tokens, localStorage, sessionStorage, or secrets.
For state-changing actions, follow the local policy result exactly. End by calling finish with a concise summary.
"""


def run_delegate_cli(argv=None):
    parser = _parser()
    ns = parser.parse_args(argv)
    if ns.doctor:
        return run_delegate_doctor(ns)
    task = _task_from_args(ns.task)
    if not task:
        parser.error("delegate needs a task string or '-' for stdin")

    config = ProviderConfig(
        model=ns.model,
        base_url=ns.base_url,
        api_key_env=ns.api_key_env,
        timeout=ns.timeout,
        stream=not ns.no_stream,
    )
    policy = Policy.from_env(ns.policy)
    transcript = Transcript(enabled=not ns.no_transcript)
    result = run_delegate(
        task,
        config=config,
        policy=policy,
        max_steps=ns.max_steps,
        start_url=ns.start_url,
        bu_name=ns.bu_name,
        include_code=not ns.no_code_tool,
        transcript=transcript,
        quiet=ns.json,
    )
    if ns.json:
        print(json.dumps(result, ensure_ascii=True, default=str))
    else:
        print(result.get("summary") or result.get("error") or "")
        if result.get("transcript"):
            print(f"transcript: {result['transcript']}", file=sys.stderr)
    return 0 if result.get("ok") else 1


def run_delegate(task, config=None, policy=None, max_steps=60, start_url=None, bu_name=None,
                 include_code=True, transcript=None, quiet=False):
    if bu_name:
        os.environ["BU_NAME"] = bu_name
    ensure_daemon()
    provider = OpenAICompatibleProvider(config or ProviderConfig())
    runner = BrowserToolRunner(policy or Policy(), include_code=include_code)
    transcript = transcript or Transcript()
    transcript.write("start", {"task": task, "model": provider.config.model, "base_url": provider.config.base_url})

    if start_url:
        runner.execute("navigate", {"url": start_url, "new_tab": True})

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Task: {task}\nCall observe first unless you already have enough page state."},
    ]
    tools = tool_schemas(include_code=include_code)
    last_content = ""
    started = time.time()

    for step in range(1, max_steps + 1):
        if not quiet:
            print(f"[delegate] step {step}/{max_steps}", file=sys.stderr)
        transcript.write("model_request", {"step": step, "message_count": len(messages)})
        try:
            resp = provider.completion(messages, tools=tools)
        except Exception as e:
            transcript.write("error", {"stage": "model", "error": str(e)})
            return _result(False, error=str(e), transcript=transcript)

        msg = resp.choices[0].message
        msg_dict = message_to_dict(msg)
        messages.append(msg_dict)
        if msg_dict.get("content"):
            last_content = msg_dict["content"]
            if not quiet:
                print(last_content, file=sys.stderr)
        tool_calls = msg_dict.get("tool_calls") or []
        transcript.write("model_response", {"step": step, "tool_calls": [_tool_call_summary(t) for t in tool_calls]})

        if not tool_calls:
            summary = last_content or "Delegate finished without a final summary."
            return _result(True, summary=summary, steps=step, transcript=transcript, seconds=time.time() - started)

        for call in tool_calls:
            name = call.get("function", {}).get("name", "")
            args = _json_args(call.get("function", {}).get("arguments", "{}"))
            if not quiet:
                print(f"[delegate] tool {name} {args}", file=sys.stderr)
            transcript.write("tool_call", {"step": step, "name": name, "args": args})
            result = runner.execute(name, args)
            transcript.write("tool_result", {"step": step, "name": name, "ok": result.get("ok"), "error": result.get("error")})
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", f"call_{step}"),
                "content": json.dumps(_clip_result(result), ensure_ascii=True, default=str),
            })
            if runner.finished:
                return _result(True, summary=runner.final_summary, steps=step, transcript=transcript, seconds=time.time() - started)

    return _result(False, error=f"delegate hit max_steps={max_steps}", summary=last_content, transcript=transcript)


def run_delegate_doctor(ns) -> int:
    ok = True

    def row(label, passed, detail=""):
        nonlocal ok
        ok = ok and passed
        mark = "ok  " if passed else "FAIL"
        print(f"  [{mark}] {label}{(' - ' + detail) if detail else ''}")

    print("browser-harness delegate doctor")
    row("install mode", _install_mode() != "unknown", _install_mode())
    row("daemon alive", daemon_alive(), "run `browser-harness --setup` if this fails")
    try:
        prev_thinking = os.environ.get("BH_AGENT_THINKING")
        os.environ["BH_AGENT_THINKING"] = "disabled"
        try:
            provider = OpenAICompatibleProvider(ProviderConfig(model=ns.model, base_url=ns.base_url, api_key_env=ns.api_key_env, timeout=30))
            resp = provider.completion([{"role": "user", "content": "Reply with ok."}], max_tokens=64)
        finally:
            if prev_thinking is None:
                os.environ.pop("BH_AGENT_THINKING", None)
            else:
                os.environ["BH_AGENT_THINKING"] = prev_thinking
        msg = resp.choices[0].message
        content = (msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)) or ""
        row("provider call", bool(content), content[:80])
    except Exception as e:
        row("provider call", False, str(e))
    try:
        Policy.from_env(ns.policy)
        row("policy", True, ns.policy)
    except Exception as e:
        row("policy", False, str(e))
    return 0 if ok else 1


def _parser():
    p = argparse.ArgumentParser(prog="browser-harness delegate")
    p.add_argument("task", nargs="*", help="Task to delegate, or '-' to read stdin")
    p.add_argument("--doctor", action="store_true", help="Check delegate provider and harness health")
    p.add_argument("--model", default=os.environ.get("BH_AGENT_MODEL", DEFAULT_MODEL))
    p.add_argument("--base-url", default=os.environ.get("BH_AGENT_BASE_URL", DEFAULT_BASE_URL))
    p.add_argument("--api-key-env", default=os.environ.get("BH_AGENT_API_KEY_ENV"))
    p.add_argument("--policy", default=os.environ.get("BH_AGENT_POLICY", "autonomous"), choices=sorted(VALID_POLICIES))
    p.add_argument("--max-steps", type=int, default=int(os.environ.get("BH_AGENT_MAX_STEPS", "60")))
    p.add_argument("--timeout", type=float, default=float(os.environ.get("BH_AGENT_TIMEOUT", "120")))
    p.add_argument("--start-url")
    p.add_argument("--bu-name")
    p.add_argument("--no-code-tool", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-stream", action="store_true")
    p.add_argument("--no-transcript", action="store_true")
    return p


def _task_from_args(parts):
    if parts == ["-"]:
        return sys.stdin.read().strip()
    return " ".join(parts).strip()


def _json_args(raw):
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def _tool_call_summary(call):
    return {"id": call.get("id"), "name": call.get("function", {}).get("name")}


def _clip_result(result):
    text = json.dumps(result, ensure_ascii=True, default=str)
    if len(text) <= 12000:
        return result
    return {"ok": result.get("ok", False), "truncated": True, "preview": text[:12000]}


def _result(ok, summary="", error="", steps=0, transcript=None, seconds=None):
    out = {"ok": ok, "summary": summary, "error": error, "steps": steps}
    if seconds is not None:
        out["seconds"] = round(seconds, 2)
    if transcript and transcript.path:
        out["transcript"] = str(transcript.path)
    return out
