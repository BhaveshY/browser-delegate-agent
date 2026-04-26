"""Browser tool registry for the delegate agent."""
from __future__ import annotations

import ast
import io
import json
from contextlib import redirect_stdout

import helpers
from agent_policy import Policy


SENSITIVE_JS = (
    "document.cookie",
    ".cookie",
    "localstorage",
    "sessionstorage",
    "indexeddb",
    "navigator.credentials",
    "cachestorage",
)
DANGEROUS_CODE_NAMES = {"eval", "exec", "compile", "open", "input", "__import__", "globals", "locals", "vars", "dir", "getattr", "setattr", "delattr"}
DANGEROUS_ATTRS = {"__globals__", "__builtins__", "__dict__", "__class__", "__mro__", "__subclasses__", "__getattribute__", "__code__", "__closure__", "__func__", "__self__"}


def tool_schemas(include_code=True):
    tools = [
        _tool("observe", "Return compact text state for the active page.", {}),
        _tool("navigate", "Open or navigate to a URL.", {
            "url": {"type": "string"},
            "new_tab": {"type": "boolean", "default": True},
        }, ["url"]),
        _tool("click", "Click an element ref from observe or explicit viewport coordinates.", {
            "ref": {"type": "string"},
            "x": {"type": "number"},
            "y": {"type": "number"},
            "button": {"type": "string", "enum": ["left", "middle", "right"], "default": "left"},
            "clicks": {"type": "integer", "default": 1},
        }),
        _tool("type_text", "Type text, optionally after clicking an element ref.", {
            "text": {"type": "string"},
            "ref": {"type": "string"},
        }, ["text"]),
        _tool("press_key", "Press one keyboard key, e.g. Enter, Escape, Tab, ArrowDown.", {
            "key": {"type": "string"},
            "modifiers": {"type": "integer", "default": 0},
        }, ["key"]),
        _tool("scroll", "Scroll the active page around a viewport point.", {
            "x": {"type": "number", "default": 800},
            "y": {"type": "number", "default": 700},
            "dy": {"type": "number", "default": 500},
            "dx": {"type": "number", "default": 0},
        }),
        _tool("wait", "Wait for a number of seconds.", {
            "seconds": {"type": "number", "default": 1.0},
        }),
        _tool("list_tabs", "List browser tabs.", {}),
        _tool("switch_tab", "Activate a tab by target_id or URL/title substring.", {
            "target_id": {"type": "string"},
            "url_contains": {"type": "string"},
            "title_contains": {"type": "string"},
        }),
        _tool("http_get", "Fetch a URL over HTTP for static pages or APIs.", {
            "url": {"type": "string"},
            "timeout": {"type": "number", "default": 20.0},
        }, ["url"]),
        _tool("finish", "Finish the task with a concise user-facing summary.", {
            "summary": {"type": "string"},
        }, ["summary"]),
    ]
    if include_code:
        tools.insert(-1, _tool("run_browser_code", "Run a short restricted Python snippet to batch browser helper calls.", {
            "code": {"type": "string"},
        }, ["code"]))
    return tools


def _tool(name, description, properties, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


class BrowserToolRunner:
    def __init__(self, policy: Policy | None = None, include_code=True):
        self.policy = policy or Policy()
        self.include_code = include_code
        self.refs = {}
        self.finished = False
        self.final_summary = ""

    def execute(self, name: str, args: dict) -> dict:
        if name == "run_browser_code" and not self.include_code:
            return {"ok": False, "error": "run_browser_code disabled"}
        allowed, reason = self.policy.check(name, args or {})
        if not allowed:
            return {"ok": False, "error": reason, "dry_run": self.policy.mode == "dry-run"}
        try:
            if name == "observe":
                return {"ok": True, "observation": self.observe()}
            if name == "navigate":
                return self.navigate(args["url"], bool(args.get("new_tab", True)))
            if name == "click":
                return self.click(args)
            if name == "type_text":
                return self.type_text(args)
            if name == "press_key":
                helpers.press_key(args["key"], int(args.get("modifiers", 0)))
                return {"ok": True}
            if name == "scroll":
                helpers.scroll(float(args.get("x", 800)), float(args.get("y", 700)), float(args.get("dy", 500)), float(args.get("dx", 0)))
                return {"ok": True, "page": helpers.page_info()}
            if name == "wait":
                helpers.wait(float(args.get("seconds", 1.0)))
                return {"ok": True}
            if name == "list_tabs":
                return {"ok": True, "tabs": helpers.list_tabs(include_chrome=False)}
            if name == "switch_tab":
                return self.switch_tab(args)
            if name == "http_get":
                body = helpers.http_get(args["url"], timeout=float(args.get("timeout", 20.0)))
                return {"ok": True, "text": body[:8000], "truncated": len(body) > 8000}
            if name == "run_browser_code":
                return self.run_browser_code(args["code"])
            if name == "finish":
                self.finished = True
                self.final_summary = args["summary"]
                return {"ok": True, "summary": self.final_summary}
            return {"ok": False, "error": f"unknown tool: {name}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def observe(self) -> dict:
        info = helpers.page_info()
        data = safe_js("""
(() => {
  const text = (document.body?.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 5000);
  const nodes = [...document.querySelectorAll('a[href],button,input,textarea,select,[role="button"],[role="link"],summary,[contenteditable="true"]')];
  const elements = [];
  for (const el of nodes) {
    const r = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    if (r.width < 1 || r.height < 1 || style.visibility === 'hidden' || style.display === 'none') continue;
    const label = (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || el.placeholder || '').replace(/\\s+/g, ' ').trim();
    const href = el.href || el.getAttribute('href') || '';
    elements.push({
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || '',
      label: label.slice(0, 120),
      href: href.slice(0, 220),
      x: Math.round(r.x),
      y: Math.round(r.y),
      w: Math.round(r.width),
      h: Math.round(r.height)
    });
    if (elements.length >= 80) break;
  }
  return JSON.stringify({text, elements});
})()
""")
        parsed = json.loads(data or "{}")
        self.refs = {}
        elements = []
        for i, el in enumerate(parsed.get("elements", []), start=1):
            ref = f"e{i}"
            el = {"ref": ref, **el}
            self.refs[ref] = el
            elements.append(el)
        return {"page": info, "text": parsed.get("text", ""), "elements": elements}

    def navigate(self, url: str, new_tab=True) -> dict:
        if new_tab:
            helpers.new_tab(url)
        else:
            helpers.goto_url(url)
        helpers.wait_for_load()
        helpers.wait(0.5)
        return {"ok": True, "page": helpers.page_info()}

    def click(self, args: dict) -> dict:
        x, y = self._point(args)
        helpers.click_at_xy(x, y, args.get("button", "left"), int(args.get("clicks", 1)))
        helpers.wait(0.4)
        return {"ok": True, "page": helpers.page_info()}

    def type_text(self, args: dict) -> dict:
        if args.get("ref"):
            x, y = self._point(args)
            helpers.click_at_xy(x, y)
            helpers.wait(0.2)
        helpers.type_text(args["text"])
        return {"ok": True}

    def switch_tab(self, args: dict) -> dict:
        tabs = helpers.list_tabs(include_chrome=False)
        target = args.get("target_id")
        if not target:
            url_sub = (args.get("url_contains") or "").lower()
            title_sub = (args.get("title_contains") or "").lower()
            for t in tabs:
                if url_sub and url_sub in t.get("url", "").lower():
                    target = t["targetId"]
                    break
                if title_sub and title_sub in t.get("title", "").lower():
                    target = t["targetId"]
                    break
        if not target:
            return {"ok": False, "error": "no matching tab"}
        helpers.switch_tab(target)
        return {"ok": True, "page": helpers.page_info()}

    def run_browser_code(self, code: str) -> dict:
        validate_browser_code(code)
        stdout = io.StringIO()
        env = {
            "__builtins__": {
                "bool": bool, "dict": dict, "enumerate": enumerate, "float": float,
                "int": int, "len": len, "list": list, "max": max, "min": min,
                "print": print, "range": range, "round": round, "str": str, "sum": sum,
            },
            "click_at_xy": helpers.click_at_xy,
            "current_tab": helpers.current_tab,
            "ensure_real_tab": helpers.ensure_real_tab,
            "goto_url": helpers.goto_url,
            "js": safe_js,
            "list_tabs": helpers.list_tabs,
            "new_tab": helpers.new_tab,
            "page_info": helpers.page_info,
            "press_key": helpers.press_key,
            "scroll": helpers.scroll,
            "switch_tab": helpers.switch_tab,
            "type_text": helpers.type_text,
            "wait": helpers.wait,
            "wait_for_load": helpers.wait_for_load,
        }
        with redirect_stdout(stdout):
            exec(code, env, {})
        out = stdout.getvalue()
        return {"ok": True, "stdout": out[-8000:]}

    def _point(self, args: dict) -> tuple[float, float]:
        if args.get("ref"):
            el = self.refs.get(args["ref"])
            if not el:
                raise RuntimeError(f"unknown ref {args['ref']}; call observe again")
            return el["x"] + el["w"] / 2, el["y"] + el["h"] / 2
        if "x" not in args or "y" not in args:
            raise RuntimeError("click requires ref or x/y")
        return float(args["x"]), float(args["y"])


def safe_js(expression: str):
    lower = expression.lower()
    if any(marker in lower for marker in SENSITIVE_JS):
        raise RuntimeError("blocked JS expression: cookies/storage/credentials are not available to delegate code")
    return helpers.js(expression)


def validate_browser_code(code: str):
    tree = ast.parse(code, mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise RuntimeError("imports are not available to delegate code")
        if isinstance(node, ast.Name) and node.id in DANGEROUS_CODE_NAMES:
            raise RuntimeError(f"{node.id} is not available to delegate code")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_") or node.attr in DANGEROUS_ATTRS:
                raise RuntimeError(f"attribute {node.attr} is not available to delegate code")
