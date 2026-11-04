# Writing and changing a style guide

Read when creating a guide after `stylelock init`, adding a variant, type or cast member, or
when a render and the guide disagree.

A guide is a versioned JSON file in `style/` (`style-guide-v<N>.json`). `stylelock` renders
it into the same style block every time, so two runs a month apart differ only by subject
and provider, never by phrasing.

---

## 1. Anatomy

| Key | What it is |
| --- | --- |
| `id`, `version` (semver), `status` | `draft` → `active` → `deprecated`. Generating against a draft needs `--allow-draft`. |
| `palette` | `colors` (≥2, each with `name`, `hex`, optional `role`), `description`, `rules` |
| `rendering` | `medium` plus free keys (line weight, shading, texture, detail level, colour handling…) |
| `lighting`, `camera`, `composition`, `mood` | optional sections, rendered in `prompt.style_block_order` |
| `characters` | rules for *all* figures (proportions, faces, how animals are drawn) |
| `cast` | named recurring characters, one rendered only when `--character` selects it |
| `avoid` | the cheapest quality lever you have. Must be non-empty. |
| `hard_rules` | absolute constraints, rendered last on every prompt, never overridable |
| `prompt` | `template` (must contain `{subject}` and `{style_block}`), `prefix`, `suffix`, `negative`, `style_block_order` |
| `references` | `default_roles`, `anchor_limit` (default 5) |
| `variants`, `types` | overlays (below) |
| `provider_defaults` | per-provider options (model, size, quality, background) |

`stylelock style lint` checks the required keys, palette shape, template, overlay keys, cast
shape and `hard_rules`. **It does not look inside `rendering`, `camera`, `lighting` or
`composition`.** A key deleted there fails silently (see §6).

## 2. Variant = which world. Type = what kind of asset. Cast = who.

Three orthogonal dimensions. Do not fork the guide for any of them.

- **Variant**: a place or palette the product keeps returning to (a city, a forest, night).
  It usually replaces `palette`, `lighting` and `mood`.
- **Type**: a format the product keeps needing (scene plate, object sprite, icon, badge,
  card art, map, frame overlay, character sheet). It usually replaces `composition` and
  `camera`, adds an `append`, sets `provider_defaults` (size, transparency) and `negative`.
- **Cast**: a locked description of one named character, added only when the brief names them.

Overlay rules:
- **Sections are replaced wholesale, never merged.** A merged palette is not a palette.
  `provider_defaults` is the one key that merges per provider, so a type can set `size`
  without restating `model`.
- **Order is variant, then type, then character. Type wins on conflict**, because the kind of
  asset constrains format more than the world does.
- **A type that names colours cancels the variant system.** A colour word in a type's
  `append` or `composition` overrides every variant palette beneath it. In practice a frame
  type's "cold blues own the structure" silently countermanded a new non-blue world one
  paragraph later. Write types to defer to "the palette in force".
- `reference_tags` on an overlay scopes which references attach. A type's tags beat a
  variant's. Pin a type to a tag nothing carries (e.g. `"reference_tags": ["none"]`) when no
  existing anchor suits it; otherwise a no-variant call silently attaches whatever untagged
  anchors exist. `reference_roles` lets a type read e.g. `composition` refs instead of anchors.
- A new type gets its own copy of anything the default would fight. If an existing type's
  `avoid` bans what you need (an `object` type banning "frames" and "touching the canvas
  edge" while you want a full-bleed frame overlay), add a type rather than bending that one.
- One-off pictures are **neither**. See `one-offs.md`.

## 3. `hard_rules`

- `hard_rules` renders on every prompt, after everything else, under "Absolute rules, these
  override everything above". No variant or type may define it; lint enforces both.
- Put a constraint there only if it is genuinely non-negotiable. The default is **no text of
  any kind**, because image models garble lettering.
- Everything that is merely usually-true belongs in `avoid` or a type's `negative`.

## 4. Guides are immutable once active

Every sidecar records the guide file and version that produced it. Editing an `active` guide
in place makes every one of those irreproducible.

```bash
stylelock style bump            # copies latest to style-guide-v<N+1>.json, status=draft
# edit the new file
stylelock style lint
# set the new file active, the old one deprecated, add a style/CHANGELOG.md entry
```

- **Freeze before a rewrite.** Before a palette rewrite or a model change, make sure the old
  version is kept somewhere a sidecar can point at.
- When a model is retired, deprecated guides keep the old model name. Regenerate against
  them with `--option model=<new>` rather than editing them.

## 5. The guide describes the art, not the intention

**Judge a render against approved art, never against the guide's prose.** A guide is written
once and the art moves on. In practice a guide described a world its art did not obey four
separate times:
- a palette rule said one colour dominates every surface, and measured approved plates held
  under 5% of it;
- an object type said "matte, no glossy sheen", and every approved object was glossy;
- a character type demanded realistic proportions, and the cast it existed for is stylised;
- a frame type hard-coded a palette that overrode the variant beneath it.

So:
1. Open an approved image beside the render before judging it (`measure_image.py` on both).
   Real faults become obvious in the comparison. Phantom ones disappear.
2. When the art has genuinely moved, **fix the guide** (bump), instead of another per-call
   override. Otherwise the next brief inherits the same fight.
3. Derive palettes by measuring real art (`measure_palette.py`), not by picking hexes by eye.
4. A new variant whose values were *written* rather than *derived* has no baseline. Say so,
   and calibrate after the first approved batch.

## 6. Editing a guide programmatically: merge, never rebuild

Rebuilding a section from a literal list of key names silently drops any key you forgot.

```python
# WRONG - drops every key not in `order`
d["rendering"] = {k: r[k] for k in order if k in r}

# RIGHT - keep the rest
d["rendering"] = {**{k: r[k] for k in order if k in r},
                  **{k: v for k, v in r.items() if k not in order}}
```

In practice, a rebuild dropped the key that carried the whole colour hierarchy. Lint passed,
and two passes of output were wrong before anyone suspected the guide instead of the renderer.

After any scripted edit, **print the key set of every section before and after, and diff
them.** Then run `stylelock style render --type X --variant Y` and read the result.

A silent deletion inside a section the linter doesn't inspect looks exactly like a renderer
fault, and it costs rerolls.

## 7. The reference library

- `references/manifest.json` is the source of truth, not the folders. An image on disk that
  isn't registered is invisible, and `refs validate` reports it.
- Roles: `anchor` (stylistically pure, sent by default), `palette`, `texture`, `composition`,
  `subject` (a specific thing or character to reproduce).
- **Anchors must be stylistically pure. No `exclude` entries are allowed on an anchor.** If an
  image is 90% right, crop it and file it as `texture` or `composition` with an `exclude` note
  ("ignore its background colour").
- Every reference needs a `demonstrates` note. Otherwise six months later nobody remembers
  why it's there.
- **Cap it.** At most `anchor_limit` (default 5) per selector. A big, noisy reference set
  weakens style transfer.
- `references/_source/` (any `_`-prefixed dir) is raw material that is never sent. Rasterize
  vectors with `scripts/rasterize.py`, then `stylelock refs add`.
- An image carrying baked-in text or numerals can't be an anchor. File it as `composition`
  and point the type's `reference_roles` at it.

## 8. Small-asset types (icons, badges)

- A 24px glyph can't carry gradients or speculars. Icons usually need their **own** flat
  type, or their own guide, and will deliberately look unlike the modelled scene art. Tell
  the user that's intended.
- Rules that hold up: one colour per glyph (unless it's a reward or status token), three or
  four shapes at most, gaps of at least 10% of the icon width.
- Knock a mark *out* of the body as negative space rather than drawing it on top. That
  keeps the glyph to one colour.
- **Consistency is not differentiation.** A set in one material and palette reads as one blob
  at menu size. Vary silhouette, or give each item a distinct accent.
- **Always review at real display size.** Ship a size ladder (e.g. 72 / 40 / 24px) and a
  contact sheet at the real size. 120px catches what 1024px hides.
- A status colour that isn't in the palette (an error red) should be added to the guide's
  palette, not slipped into one brief.
