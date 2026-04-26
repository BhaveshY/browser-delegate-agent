# Browser Delegate Agent

Self-bootstrapping real-browser delegation for Codex, Claude Code, and OpenAI-compatible models.

Point Codex or Claude Code at this repo and it bootstraps a real-browser delegate agent for you.

Browser Delegate Agent connects to your already-running Chrome, Edge, or Comet profile through CDP. It delegates browser-heavy work to an external OpenAI-compatible model, defaulting to Z.AI `glm-5.1`, so your main coding agent can spend fewer tokens babysitting web pages.

Built on top of the excellent MIT-licensed [`browser-use/browser-harness`](https://github.com/browser-use/browser-harness). See [Credits](#credits).

## 60-second quickstart

Paste this into Codex or Claude Code:

```text
Set up https://github.com/BhaveshY/browser-delegate-agent for me.

Read install.md first. Run `uv run browser-harness --bootstrap` from the checkout. Then read SKILL.md and helpers.py for normal usage. When setup opens a browser permission or verification tab, activate it so I can see it.
```

Bootstrap does the boring parts:

- Installs this checkout globally with `uv tool install -e .`.
- Registers the harness instructions for Codex and Claude Code.
- Attaches to your real browser and opens any required permission tab.
- Configures the delegate provider from `BH_AGENT_API_KEY` or `ZAI_API_KEY`, or prompts for one.
- Runs a safe read-only GitHub demo.

## Delegate browser work

```bash
browser-harness delegate "Open the browser-delegate-agent repo and summarize the visible README"
```

Defaults:

- Model: `glm-5.1`
- Base URL: `https://api.z.ai/api/paas/v4/`
- Policy: `autonomous`
- Tools: browser-only navigation, observe, click, type, scroll, tabs, HTTP fetch, and finish

Use any OpenAI-compatible provider:

```bash
BH_AGENT_API_KEY=... \
browser-harness delegate \
  --base-url https://api.z.ai/api/paas/v4/ \
  --model glm-5.1 \
  "Find the current page title"
```

Safety-conscious mode:

```bash
browser-harness delegate --policy confirm "Open GitHub and prepare to star this repo"
browser-harness delegate --policy dry-run "Plan how to submit this form"
```

## Architecture

```text
Codex / Claude Code
        |
        |  browser-harness delegate
        v
OpenAI-compatible model, e.g. GLM-5.1
        |
        |  JSON tool calls only
        v
Browser Delegate Agent tool runner
        |
        |  Unix socket JSON lines
        v
daemon.py -> CDP websocket -> your real browser
```

The external model does not get shell access or repo file access. It receives compact text observations of the page and can request browser tools. A restricted fast-path Python tool can batch browser helper calls, but it has no imports, no shell, no file access, no raw CDP, no uploads, and no cookies/storage access.

## What this can do that normal agents cannot

- Use your existing logged-in browser without pasting credentials.
- Let you watch the active tab as the delegate works.
- Offload long browser workflows to cheaper or specialized models.
- Keep durable site knowledge in `domain-skills/` so future agents do not rediscover the same quirks.
- Drop down to direct CDP helpers when normal web automation gets flaky.

## Why not just Browser Use, Playwright, or MCP?

- **Browser Use cloud** is great for managed remote browsers. Browser Delegate Agent is for your real local browser profile, with optional Browser Use cloud support when you want remote sessions.
- **Playwright** is excellent for tests. Browser Delegate Agent is optimized for agents operating messy real sites where screenshots, coordinates, CDP, and mid-task helper edits are often faster.
- **MCP** is a good integration surface. This repo stays installable as one tiny CLI first; an MCP wrapper can sit on top later.

## Useful commands

```bash
browser-harness --bootstrap
browser-harness --doctor
browser-harness delegate --doctor
browser-harness delegate "Open example.com and tell me what loaded"
browser-harness --reload
```

## Contributing

The best contributions are small, field-tested improvements:

- New or improved `domain-skills/<site>/` notes.
- Browser compatibility fixes.
- Safer delegate tools.
- Better bootstrap behavior for Codex, Claude Code, and other agents.

If an agent learns something non-obvious while completing a site workflow, capture the durable map, not the diary: selectors, URL patterns, API endpoints, waits, and traps.

## Credits

This project is based on [`browser-use/browser-harness`](https://github.com/browser-use/browser-harness), created by the Browser Use team and released under the MIT License. The original copyright notice is preserved in [LICENSE](LICENSE), and additional attribution is in [NOTICE.md](NOTICE.md).

The delegate-agent layer, self-bootstrap flow, Claude/Codex registration, OpenAI-compatible provider loop, and safety policy additions are maintained in this standalone repository.
