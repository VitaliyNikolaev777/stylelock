# stylelock

Style-locked image generation. Image models drift: the same prompt a month apart gives a
different look, and every person phrases style differently. stylelock fixes the style in a
**versioned guide** and sends it, together with a few **reference anchor** images, on every
call. Each output gets a **provenance sidecar** recording exactly what produced it.

It comes in two parts:

- **`stylelock` CLI** - the deterministic part. It assembles the prompt from the guide, attaches
  the anchors, calls the image provider (OpenAI, Gemini or Replicate), and writes the image
  and its sidecar.
- **Claude Code skill** - the judgment part. It teaches Claude to plan layers, write briefs,
  look at results, reject with countable reasons, and fix things locally instead of rerolling.

```
you ──► Claude (plans, briefs, reviews) ──► stylelock CLI ──► image model
                     ▲                            │
                     └──── reads PNG + sidecar ◄──┘
```

## Install with Claude Code

Paste this repo's link into Claude Code and ask it to install it. Claude follows the section below.

### For Claude Code: how to install

Run these, then tell the user to start a new session so the skill loads:

```bash
# 1. the skill (as a plugin)
claude plugin marketplace add VitaliyNikolaev777/stylelock
claude plugin install stylelock@stylelock

# 2. the CLI (needs uv: https://docs.astral.sh/uv/ - ask before installing uv itself)
uv tool install "stylelock[openai,tools] @ git+https://github.com/VitaliyNikolaev777/stylelock"
stylelock --version
```

Use `gemini` or `replicate` instead of `openai` if that is the user's provider. Without uv,
use `pipx install` with the same spec. Then ask the user where their art project should live,
and run `stylelock init <dir>` there. For the key, have the user run
`stylelock config set-key openai` in their own terminal (it prompts for it), rather than
pasting it into chat. Then set the provider with `stylelock config set provider openai`.

## Install by hand

```bash
uv tool install "stylelock[openai,tools] @ git+https://github.com/VitaliyNikolaev777/stylelock"
```

In Claude Code: `/plugin marketplace add VitaliyNikolaev777/stylelock`, then
`/plugin install stylelock@stylelock`.

To use the skill without the plugin system, copy `skills/stylelock/` to `~/.claude/skills/stylelock/`.

## Quick start

```bash
stylelock init my-art && cd my-art
stylelock config set provider openai          # which image model paints
stylelock config set-key openai               # prompts for the key; stored 0600, never in argv
stylelock doctor
stylelock generate "a red bicycle" --type object --dry-run      # see the exact prompt, free
stylelock generate "a red bicycle" --type object --allow-draft  # real call, against the draft
```

`init` writes a **draft placeholder guide**. Replace it with a description of your own art
(or ask Claude to build one from your images), register 2-5 anchors, and set
`"status": "active"`:

```bash
stylelock refs add hero.png --role anchor --demonstrates "flat fills, no outlines, the palette"
stylelock style lint && stylelock refs validate
```

## Use it from an orchestrator or any MCP host

stylelock is model-agnostic on both sides. The **smart model** (planner, briefer, reviewer) can
be anything that calls tools: Claude, GPT, Gemini, a local model. The **generation model** is a
setting of whoever runs stylelock. The two never share a key.

```bash
uv tool install "stylelock[openai,mcp] @ git+https://github.com/VitaliyNikolaev777/stylelock"
```

Register it as an MCP server (stdio). For example, a connector definition:

```json
{
  "command": "stylelock",
  "args": ["mcp", "--project", "/path/to/my-art", "--max-images", "40"],
  "env": {
    "STYLELOCK_PROVIDER": "openai",
    "STYLELOCK_MODEL": "gpt-image-1.5",
    "OPENAI_API_KEY": "<from the host's secret store>"
  }
}
```

| Orchestrator setting | Goes to |
|---|---|
| smart model | whichever model the host connects to this server. It gets the workflow as the server's `instructions`. |
| generation model | `STYLELOCK_PROVIDER` + `STYLELOCK_MODEL` in the server's env |
| generation key | `OPENAI_API_KEY` / `GEMINI_API_KEY` / `REPLICATE_API_TOKEN` / `STYLELOCK_COMPAT_API_KEY` in the server's env |
| self-hosted / proxy model | `STYLELOCK_PROVIDER=openai-compatible` + `STYLELOCK_COMPAT_BASE_URL` |

What the server guarantees:

- provider, model and key are fixed at launch. No tool can change them, and no tool result
  contains a key.
- one server serves one project, and every path argument must resolve inside it.
- `--max-images` caps generation per session. The model gets a readable error and is told
  to ask the user.
- one line per tool call on stderr, for the host's log. The sidecars remain the durable record.
- previews of generated images come back with the result, transparent ones over a
  checkerboard, so a vision model can review them without a second call.

Tools: `status`, `style_info`, `preview_prompt`, `generate`, `view_image`, `list_pending`,
`accept`, `reject`, `review_reasons`, `review_report`, `list_references`, `add_reference`,
`read_doc`.

**No MCP?** Any agent with a shell can drive the CLI. Put `stylelock instructions` in its
system prompt and have it use `--json` on every command. `stylelock providers --json` lists
every image provider with its capabilities and key status, for a settings screen.

## A project

A project is any folder with `style/` and `references/manifest.json`. The CLI finds it by
walking up from the current directory, or from `STYLELOCK_HOME`. The tool is installed once;
each project has its own style, library, outputs and reject log.

```
my-art/
  style/style-guide-v1.json     the versioned spec (immutable once active - use `style bump`)
  style/experiments/            throwaway guides for one-off off-style images
  style/CHANGELOG.md
  references/manifest.json      the library - an image on disk but not here is invisible
  references/{anchors,palette,texture,composition,subject}/
  references/_source/           raw material, never sent to a model
  outputs/                      images + .json provenance sidecars
  rejects/log.jsonl             reasons from a fixed vocabulary, mined by `review report`
  .env                          provider keys (also read: ~/.config/stylelock/.env)
```

## The guide in one paragraph

A base spec (palette, rendering, lighting, camera, composition, mood, avoid) plus two
orthogonal overlays: **variants** (*which world* - forest, night) and **types** (*what kind of
asset* - scene, object, icon). An overlay replaces whole sections rather than merging; the
order is variant, then type. **cast** locks named recurring characters, and only the selected
one renders. **hard_rules** render last on every prompt and no overlay may touch them. See
`skills/stylelock/reference/guides.md`.

## Commands

| | |
|---|---|
| `stylelock init [dir]` | create a project |
| `stylelock doctor` | check guide, library and provider keys |
| `stylelock providers` | image providers, capabilities, whether a key is set |
| `stylelock config show / set / set-key` | provider and model defaults, API keys |
| `stylelock instructions [doc]` | the workflow for an orchestrating model |
| `stylelock mcp --project DIR` | run as an MCP server over stdio |
| `stylelock generate "<subject>"` | `--type --variant --character --extra --provider --model -n --dry-run --option k=v` |
| `stylelock style list / lint / render / show / bump / variants / types / cast` | inspect and version the guide |
| `stylelock refs list / add / validate` | manage the reference library |
| `stylelock review pending / accept / reject / report / reasons` | the feedback loop |

## Development

```bash
uv venv && uv pip install -e ".[dev,tools]"
.venv/bin/python -m pytest -q
```

The reference docs live in `src/stylelock/docs/` (packaged, served over MCP). The skill keeps
copies in `skills/stylelock/reference/`, and a test fails if they drift.

Adding a provider means one file in `src/stylelock/providers/` subclassing `Provider`, plus a
line in `providers/__init__.py`. Set `supports_reference_images` / `supports_negative_prompt`
honestly. Provider defaults belong in the guide's `provider_defaults`, not in the adapter.
