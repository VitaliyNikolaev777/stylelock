---
name: stylelock
description: Generate images, illustrations, sprites, icons, scene backgrounds or game/app assets that must stay in ONE consistent visual style, using the stylelock CLI (versioned style guide + reference anchors + provenance sidecar per image). Use whenever the user asks to make, regenerate, fix or review images for a project that has (or should have) a house style, to set up a style guide from existing art, to register reference images, or mentions stylelock. Also use for one-off off-style pictures inside such a project.
---

# stylelock

You are the art director; the image model is the painter; `stylelock` is the only line
between you. You plan, brief, look at results and decide. The CLI injects the versioned
style spec and the anchor images into every call and writes a provenance sidecar next to
every output. The image API key belongs to the CLI - you never need it and never call an
image API yourself.

## The one rule

**Every image goes through `stylelock generate`.** No direct `client.images.generate(...)`,
no curl to an image endpoint, not even in a throwaway script. That would skip the style spec,
the anchors and the provenance record - the entire point of the setup.

## First use: make sure the tool and a project exist

1. `stylelock --version`. If the command is missing, install it (needs [uv](https://docs.astral.sh/uv/)):
   ```bash
   uv tool install "stylelock[openai,tools] @ git+https://github.com/VitaliyNikolaev777/stylelock"
   ```
   No uv? Tell the user the one-line installer from docs.astral.sh/uv and ask before running
   it; `pipx install "stylelock[openai,tools] @ git+https://github.com/VitaliyNikolaev777/stylelock"`
   works too. Swap `openai` for `gemini` or `replicate` if that is their provider.
2. `stylelock doctor`. It finds the project from the current folder upward, or from
   `STYLELOCK_HOME`. If there is none, ask the user where their art project should live and
   run `stylelock init <dir>`.
3. Provider and key. Which image model paints is the user's setting:
   `stylelock config set provider openai` (optionally `config set model <id>`). For the key,
   ask the user to run `stylelock config set-key openai` in their own terminal. It prompts
   for the key and stores it with mode 600. Don't ask them to paste a key into chat.
   `stylelock providers` shows what each provider can do (references, transparency) and
   whether its key is set. `--provider dryrun` needs no key and is fine for checking the plumbing.

## A new project has no style yet - build it from their art

`init` writes a **draft** placeholder guide. Generating against it produces generic art.
Before real generation:

1. Ask for 3-10 images the user considers exactly on-style (shipped art, a mood board).
   Look at them yourself.
2. Measure, don't guess: `scripts/measure_palette.py` for the palette, and describe rendering,
   lighting, composition and mood from what is actually in the files.
3. Rewrite `style/style-guide-v1.json` (see `reference/guides.md`). Keep `hard_rules` for
   genuinely absolute constraints - usually "no text of any kind".
4. Register the 2-5 purest as anchors:
   `stylelock refs add <file> --role anchor --demonstrates "<what this image teaches>"`.
   Anything only partly right goes in as `texture`/`composition`/`palette` with `--exclude`.
5. `stylelock style lint`, `stylelock refs validate`, a few `--dry-run`s, a few real tests.
   Then set `"status": "active"`. From now on the guide is immutable - changes go through
   `stylelock style bump`.

## The loop for every request

1. **Plan the layers before prompting.** A screen or scene is usually UI + markers + sprites +
   a background plate, and only some of that should be generated at all. Decide what is a
   separate transparent `object`, what is the plate, and what is the app's job. See
   `reference/briefing.md`.
2. **Brief.** `subject` = *what* to depict, never how it looks (style words in the subject
   fight the style block). Per-image direction (crop, camera, layout) goes in `--extra`. Keep
   it short (about 300 words at most) and lead with rendering. Pick `--type` (what kind of
   asset) and `--variant` (which world) from `stylelock style types` / `style variants`. Use
   `--character` for a recurring cast member, plus a subject reference of the shipped sprite.
3. **Dry-run first** when the brief is new: `stylelock generate "<subject>" --type ... --dry-run`
   prints the exact prompt and references without spending a call.
4. **Generate:** `stylelock generate "<subject>" --provider openai --type object -n 2`.
   The output paths are printed. Every image gets a `.json` sidecar.
5. **Look at every output yourself** (open the PNG) against the brief and the guide. Measure
   when in doubt (`scripts/measure_image.py`) - eyeballing has been wrong before.
6. **Decide:**
   - on-style and on-brief → `stylelock review accept <img>`
   - wrong → `stylelock review reject <img> --reasons <tag> --note "..."` with tags from
     `stylelock review reasons` (fixed vocabulary - counted reasons feed back into the guide)
   - 90% right → fix locally (mirror, mask, strip shadow, key out) rather than reroll; see
     `reference/post-processing.md`
7. **Fix the setup, not the wording.** If the same failure repeats, change the setup (type,
   references, layer split, post-process step). Ten rewordings of `--extra` rarely help.
   `stylelock review report` tells you which guide sections to tighten.
8. Tell the user how many generations you spent.

## Off-style one-offs

A single picture in a different style never edits the house guide. Write a throwaway guide at
`style/experiments/oneoff-<slug>.json` and run
`stylelock generate ... --style-version style/experiments/oneoff-<slug>.json --allow-draft`.
A *recurring* world becomes a variant and a *recurring* format becomes a type. See
`reference/one-offs.md`.

## Reference - read when the task touches it

| File | Read when |
|---|---|
| `reference/briefing.md` | writing any non-trivial brief: layer planning, `--extra`, renderer biases, character locking |
| `reference/guides.md` | creating or changing a style guide, variants, types, cast, anchors |
| `reference/post-processing.md` | transparency problems, baked shadows, local fixes vs redraw, measuring |
| `reference/review.md` | reviewing a batch, reject reasons, handing assets over |
| `reference/one-offs.md` | the user wants something outside the house style |

## Scripts (PIL only, no API calls)

In `scripts/` next to this file. Run with `uv run --with pillow python <script> --help`, or
with any Python that has Pillow. Each script's docstring says when to use it.

- `strip_contact_shadow.py` - remove the soft shadow pool models bake under transparent objects
- `chroma_key.py` - make an opaque render transparent after an edit onto flat #00FF00
- `fill_interior_holes.py` - fill transparent holes punched inside an object
- `mirror_region.py` - fix a wrong-facing part by mirroring a region instead of rerolling
- `knock_back_background.py` - desaturate/lighten a plate so sprites read on it
- `solidify_frame.py` - repair the alpha of a full-bleed frame with a window
- `split_character_sheet.py` - cut a one-call pose sheet into separate sprites
- `compose_scene.py` - assemble plate + sprites for a preview
- `measure_palette.py`, `measure_image.py` - numbers instead of impressions
- `rasterize.py` - SVG/PDF source art to PNG before `refs add`

## Commands at a glance

```
stylelock init [dir]                         new project
stylelock doctor                             what's set up, what's missing
stylelock providers                          capabilities and key status per provider
stylelock config show|set|set-key            provider/model defaults, API keys
stylelock style list|lint|render|show|bump|variants|types|cast
stylelock refs list|add|validate
stylelock generate "<subject>" [--type T] [--variant V] [--character C]
                   [--extra "..."] [--provider openai] [-n N] [--dry-run]
                   [--roles anchor,subject] [--ref-ids id1,id2] [--option key=value]
stylelock review pending|accept|reject|report|reasons
```

Add `--json` to any of these for output you can parse reliably.
