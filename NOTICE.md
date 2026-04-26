# Credits and Lineage

Browser Delegate Agent is built on top of the MIT-licensed
[`browser-use/browser-harness`](https://github.com/browser-use/browser-harness)
project by the Browser Use team.

Original Browser Harness copyright:

```text
Copyright (c) 2026 Browser Use
```

The original MIT license text is preserved in `LICENSE`.

This standalone repository adds the self-bootstrapping delegate agent:

- `browser-harness --bootstrap`
- `browser-harness delegate`
- OpenAI-compatible model delegation, defaulting to Z.AI `glm-5.1`
- Codex and Claude Code registration
- Browser-only tool execution policy
- Delegate transcripts and safety controls

Thank you to Browser Use for the compact real-browser CDP harness that made
this project possible.
