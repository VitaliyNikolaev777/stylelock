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
and run `stylelock init <dir>` there. Ask them to put their API key in `<dir>/.env`
themselves rather than pasting it into chat.

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
echo "OPENAI_API_KEY=sk-..." > .env
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
| `stylelock generate "<subject>"` | `--type --variant --character --extra --provider -n --dry-run --option k=v` |
| `stylelock style list / lint / render / show / bump / variants / types / cast` | inspect and version the guide |
| `stylelock refs list / add / validate` | manage the reference library |
| `stylelock review pending / accept / reject / report / reasons` | the feedback loop |

## Development

```bash
uv venv && uv pip install -e ".[dev,tools]"
.venv/bin/python -m pytest -q
```

Adding a provider means one file in `src/stylelock/providers/` subclassing `Provider`, plus a
line in `providers/__init__.py`. Set `supports_reference_images` / `supports_negative_prompt`
honestly. Provider defaults belong in the guide's `provider_defaults`, not in the adapter.
