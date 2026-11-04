# Changelog

## 0.2.0 - 2026-11-04

- **MCP server** (`stylelock mcp`, `pip install 'stylelock[mcp]'`). One server per
  project. Provider, model and key are fixed by the host at launch. Path arguments must
  stay inside the project. Optional per-session image budget. `generate` returns previews
  with its result, transparent images over a checkerboard.
- **Generation is a setting.** `STYLELOCK_PROVIDER` / `STYLELOCK_MODEL` (env or `.env`)
  choose the provider and model. Precedence: flag, then env, then guide. `generate --model`.
- **`stylelock config show / set / set-key`.** Keys are read from a prompt or stdin, never
  from argv, and stored 0600 in `~/.config/stylelock/.env` or the project `.env`.
- **`stylelock providers`** lists each provider's capabilities (references, transparency,
  negative prompt) and key status.
- **`openai-compatible` provider** for any server with OpenAI's Images API: proxies, local
  model servers, self-hosted gateways.
- **`--json`** on generate, style, refs, review, doctor, providers and config.
- **`stylelock instructions`** prints an agent-neutral workflow for any orchestrating model.
- Reference docs moved into the package (`src/stylelock/docs/`). The skill keeps checked copies.

## 0.1.0 - 2026-11-04

- First release: CLI with project discovery and `init`, Claude Code skill and plugin.
