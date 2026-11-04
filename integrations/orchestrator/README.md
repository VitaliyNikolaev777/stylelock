# stylelock for an orchestrator

Everything needed to plug stylelock into an orchestrator, or any MCP host, as a connector.
The orchestrator has two settings:

- **Smart model**: plans, briefs, reviews. Any tool-calling model; it should be able to see images.
- **Generation model**: paints. A stylelock provider plus a model id, with its API key.

```
orchestrator chat ──► smart model ──MCP tools──► stylelock mcp ──► image API
                                                     ▲
                    connector env: provider, model, key (set once, by you)
```

The smart model only ever sees tools. The key lives in the connector's env, and no tool can
read it, change the provider or model, or touch files outside the project.

## Files here

| File | What it is |
|---|---|
| `connector.json` | The standard connector: OpenAI, 40 images per session. Edit the path and inject the key. |
| `connector.read-only.json` | Same project, `--max-images 0`: browse the guide, preview prompts, review. Nothing is generated. |
| `connector.openai-compatible.json` | Generation through a proxy or a local model server (OpenAI Images API). |
| `system-prompt.md` | The workflow for the smart model. The server already sends it as its MCP `instructions`. Use this file only if your host ignores those. |
| `tools.json` | The 13 tools with their input schemas, generated from the running server. |
| `smoke_test.py` | Launches a connector exactly as a host would and checks it end to end. |

## Setup

**1. Install the tool** (once per machine):

```bash
uv tool install "stylelock[openai,mcp] @ git+https://github.com/VitaliyNikolaev777/stylelock"
stylelock --version
```

Pick the extras you need: `openai`, `gemini`, `replicate` (`openai` also covers
`openai-compatible`), plus `mcp`. If your host launches commands without your shell's PATH,
use the absolute path that `which stylelock` prints as `command`.

**2. Have a project.** This is a folder with `style/` and `references/manifest.json`. Make
a new one with `stylelock init /path/to/art` (it starts with a *draft* guide), or point at
an existing one.

**3. Fill in the connector.** Copy `connector.json` into your orchestrator and set:

| Field | Set to |
|---|---|
| `--project` | the absolute project path. One connector serves one project. |
| `--max-images` | the per-session cap. When it's reached, the model gets a readable error that tells it to ask you. `0` = read-only. |
| `STYLELOCK_PROVIDER` | `openai` · `gemini` · `replicate` · `openai-compatible` · `dryrun` (placeholder images, no key) |
| `STYLELOCK_MODEL` | the model id, e.g. `gpt-image-1.5`. Leave it out to use the style guide's choice. |
| key | `OPENAI_API_KEY` · `GEMINI_API_KEY` · `REPLICATE_API_TOKEN` · `STYLELOCK_COMPAT_API_KEY`. Inject it from the orchestrator's secret store. |
| `STYLELOCK_COMPAT_BASE_URL` | only for `openai-compatible` |

Rather than putting the key in the connector, you can store it once on the machine with
`stylelock config set-key openai`. It goes to `~/.config/stylelock/.env` with mode 600, and
the server reads it from there. A key in the connector env takes precedence.

To see what each provider can do before choosing (references, transparency, whether a key
is set), run `stylelock providers --json`. You can use it to fill a settings dropdown.

**4. Smoke test** before approving the connector:

```bash
uv run --with "mcp>=2.3,<3" python smoke_test.py connector.json              # free
uv run --with "mcp>=2.3,<3" python smoke_test.py connector.json --generate   # 1 image
```

It prints the tools, the project, the guide, the configured painter and its capabilities,
and the budget. Placeholder key values are skipped, so a key exported in your shell is used.

## Guarantees the server enforces

- The provider, model and key are fixed at launch. The `generate` tool accepts only image
  options (`size`, `quality`, `background`, `output_format`, `aspect_ratio`, `seed`, ...);
  passing `model` or `base_url` is an error. No tool result contains a key.
- Every path argument must resolve inside `--project`. `../` and absolute paths elsewhere
  are refused.
- At most 4 images per `generate` call, and at most `--max-images` per session.
- One line per tool call goes to **stderr** (`[stylelock] generate 'a kite' type=object n=1`),
  for your log. Each image's `.json` sidecar is the permanent record: prompt, style version,
  references, provider and model.
- Errors the model can act on (draft guide, unknown type, bad reject reason, budget
  reached) come back as readable tool errors, not crashes.

## What the smart model gets

- **Instructions** at connect time: the workflow in `system-prompt.md`.
- **Tools:**
  - `status`: call first; it shows the painter's capabilities and budget.
  - `style_info`
  - `preview_prompt`: free.
  - `generate`: returns previews.
  - `view_image`
  - `list_pending`, `accept`, `reject`: rejects use the fixed reasons from `review_reasons`.
  - `review_report`
  - `list_references`, `add_reference`
  - `read_doc`, for deeper guidance: `briefing`, `guides`, `post-processing`, `review`, `one-offs`.

Two things to know:

- **Vision.** Reviewing outputs means looking at them. With a text-only smart model, planning
  and briefing still work, but leave the review to a person.
- **Draft guides.** `generate` refuses a guide marked `draft` unless the model passes
  `allow_draft: true`. That's on purpose: a draft is a placeholder. Mark the guide `active`
  once it describes your real art.

## Without MCP

Any agent with a shell can drive the CLI instead. Use the output of `stylelock instructions`
as its system prompt and have it add `--json` to every command. Then the key is only as
private as the agent's shell environment. With MCP it never reaches the agent.

## Keeping this folder current

`system-prompt.md` and `tools.json` are copies of what the package serves, and the test
suite fails if either drifts. After changing a tool or the agent doc, regenerate them from
the repo root:

```bash
.venv/bin/python integrations/orchestrator/regenerate.py
```
