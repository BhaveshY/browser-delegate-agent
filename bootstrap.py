"""Self-contained install and delegate bootstrap."""
from __future__ import annotations

import argparse
import getpass
import os
import shlex
import subprocess
import sys
from pathlib import Path

from admin import daemon_alive, run_setup
from agent_provider import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_API_KEY_ENVS,
    ProviderConfig,
    is_placeholder_key,
    resolve_api_key,
)


DEMO_TASK = (
    "Open https://github.com/BhaveshY/browser-delegate-agent and summarize the visible repo name, "
    "description, and page state. Do not star, watch, fork, sign in, or mutate anything."
)


def run_bootstrap_cli(argv=None):
    ns = _parser().parse_args(argv)
    repo = Path(__file__).resolve().parent
    print("browser-harness bootstrap")
    ok = True
    ok = _step("ensure .env file", lambda: ensure_env_file(repo)) and ok
    # Reload env so a freshly-created .env is visible to later steps.
    _reload_env(repo)
    ok = _step("install editable tool", lambda: install_editable(repo)) and ok
    ok = _step("register Codex skill", lambda: install_codex_skill(repo)) and ok
    ok = _step("register Claude Code import", lambda: install_claude_import(repo)) and ok
    ok = _step("attach browser", lambda: attach_browser()) and ok
    provider_ok = _step("configure delegate provider", lambda: configure_provider(repo, yes=ns.yes, no_save=ns.no_save_key))
    ok = provider_ok and ok
    if provider_ok and not ns.no_demo:
        ok = _step("run safe delegate demo", lambda: run_safe_demo(ns)) and ok
    return 0 if ok else 1


def ensure_env_file(repo: Path):
    """Create .env from .env.example if missing, so the user has one place to add the key."""
    env_file = repo / ".env"
    example = repo / ".env.example"
    if env_file.exists():
        return True
    if not example.exists():
        return True
    env_file.write_text(example.read_text())
    try:
        os.chmod(env_file, 0o600)
    except OSError:
        pass
    print(f"  created {env_file} (mode 600) -- edit it to add your API key, then rerun bootstrap")
    return True


def _reload_env(repo: Path):
    """Re-read repo/.env into os.environ so steps after `ensure_env_file` see new values.

    Skips placeholder API keys (centralized in agent_provider.is_placeholder_key).
    """
    env_file = repo / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if not v:
            continue
        if k in DEFAULT_API_KEY_ENVS and is_placeholder_key(v):
            continue
        os.environ.setdefault(k, v)


def install_editable(repo: Path):
    if not _which("uv"):
        raise RuntimeError("uv is required; install uv first")
    # --force makes re-runs idempotent: silently overwrites an existing entry-point
    # rather than failing with "Executable already exists".
    subprocess.run(["uv", "tool", "install", "-e", ".", "--force"], cwd=repo, check=True)
    return True


def install_codex_skill(repo: Path):
    dest = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "skills" / "browser-harness"
    dest.mkdir(parents=True, exist_ok=True)
    link = dest / "SKILL.md"
    target = repo / "SKILL.md"
    if link.exists() or link.is_symlink():
        if link.resolve() == target.resolve():
            return True
        link.unlink()
    link.symlink_to(target)
    return True


def install_claude_import(repo: Path):
    claude_dir = Path.home() / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    claude_md = claude_dir / "CLAUDE.md"
    line = f"@{repo / 'SKILL.md'}"
    if claude_md.exists():
        text = claude_md.read_text()
        if line in text:
            return True
        if text and not text.endswith("\n"):
            text += "\n"
    else:
        text = "# Claude Code global instructions\n\n"
    claude_md.write_text(text + line + "\n")
    return True


def attach_browser():
    if daemon_alive():
        return True
    return run_setup() == 0


def configure_provider(repo: Path, yes=False, no_save=False):
    key, env_name = resolve_api_key()
    if key:
        print(f"  provider key from {env_name}")
        return True
    env_file = repo / ".env"
    if not sys.stdin.isatty():
        raise RuntimeError(
            f"BH_AGENT_API_KEY not set -- edit {env_file} and replace your_api_key_here, "
            f"or export BH_AGENT_API_KEY/ZAI_API_KEY, then rerun bootstrap"
        )
    print("  delegate needs an OpenAI-compatible provider key.")
    print("  Default: Z.AI GLM Coding Plan. Set BH_AGENT_BASE_URL/BH_AGENT_MODEL for other providers.")
    key = getpass.getpass("  API key (input hidden, leave blank to skip): ").strip()
    if not key:
        raise RuntimeError("delegate provider key not configured")
    os.environ["BH_AGENT_API_KEY"] = key
    if not no_save and (yes or _yes("save BH_AGENT_API_KEY to this repo's .env for future runs?", default=False)):
        upsert_env(env_file, "BH_AGENT_API_KEY", key)
        upsert_env(env_file, "BH_AGENT_MODEL", os.environ.get("BH_AGENT_MODEL", DEFAULT_MODEL))
        upsert_env(env_file, "BH_AGENT_BASE_URL", os.environ.get("BH_AGENT_BASE_URL", DEFAULT_BASE_URL))
        try:
            os.chmod(env_file, 0o600)
        except OSError:
            pass
    return True


def run_safe_demo(ns):
    from delegate import run_delegate
    from agent_policy import Policy
    from agent_transcript import Transcript

    result = run_delegate(
        DEMO_TASK,
        config=ProviderConfig(
            model=os.environ.get("BH_AGENT_MODEL", DEFAULT_MODEL),
            base_url=os.environ.get("BH_AGENT_BASE_URL", DEFAULT_BASE_URL),
            timeout=90,
        ),
        policy=Policy(mode="autonomous"),
        max_steps=8,
        start_url="https://github.com/BhaveshY/browser-delegate-agent",
        include_code=False,
        transcript=Transcript(enabled=not ns.no_transcript),
    )
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "delegate demo failed")
    print("  demo summary:", result.get("summary", "").strip())
    return True


def upsert_env(path: Path, key: str, value: str):
    lines = []
    seen = False
    if path.exists():
        lines = path.read_text().splitlines()
    out = []
    for line in lines:
        if line.startswith(key + "="):
            out.append(f"{key}={shlex.quote(value)}")
            seen = True
        else:
            out.append(line)
    if not seen:
        out.append(f"{key}={shlex.quote(value)}")
    path.write_text("\n".join(out).rstrip() + "\n")


def _step(label, fn):
    print(f"* {label}...")
    try:
        fn()
        print(f"  ok")
        return True
    except Exception as e:
        print(f"  FAIL: {e}", file=sys.stderr)
        return False


def _which(cmd):
    from shutil import which
    return which(cmd)


def _yes(question, default=False):
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        ans = input(f"  {question} {suffix} ").strip().lower()
    except EOFError:
        return default
    if not ans:
        return default
    return ans.startswith("y")


def _parser():
    p = argparse.ArgumentParser(prog="browser-harness --bootstrap")
    p.add_argument("--yes", "-y", action="store_true", help="Use yes for bootstrap prompts where safe")
    p.add_argument("--no-save-key", action="store_true", help="Do not offer to save provider key to .env")
    p.add_argument("--no-demo", action="store_true", help="Skip the safe delegate demo")
    p.add_argument("--no-transcript", action="store_true", help="Skip delegate demo transcript")
    return p
