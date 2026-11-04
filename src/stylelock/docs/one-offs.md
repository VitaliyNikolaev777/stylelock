# One-off images that are not the project's style

Read when someone asks for a single picture that deliberately looks different: a mock-up, a
pitch image, a slide illustration, "something in this other style".

The project's style is deliberately hard to escape. An image that's *meant* to look different
needs to say so explicitly, or it drifts back.

---

## 1. Is it really a one-off?

| Ask | Where it goes |
| --- | --- |
| A single picture, a mock-up, a pitch image | A throwaway guide, `style/experiments/oneoff-<slug>.json`. The project guide is untouched. |
| A new world the product will keep visiting | A new **variant** in the project guide |
| A new format the product will keep needing | A new **type** in the project guide |

If unsure, ask. Getting it wrong is costly both ways. A one-off that quietly becomes a habit
leaves the guide not describing the art, and a recurring world filed as a throwaway gets
re-invented every time.

**A one-off never edits the project guide**: no new variant, no new type, no tweak to an
existing one.

## 2. What to ask the user

Two sentences each is plenty:

```
One-off, not house style.

Subject:      <what to depict>
Look like:    <medium / technique / reference image>
Must NOT be:  <which habits of the project style to drop>
Format:       <size, aspect, transparent or opaque, size in use>
Text:         <none | needed, and where>
Fidelity:     <rough mock | final asset>
```

- **"Must NOT be" is the part people skip, and it matters most.** An off-style brief that only
  says what it wants comes back as house style plus a hint of the ask. Read the project
  guide's `rendering` and `avoid` aloud to the user and ask which of those habits to drop.
- A reference image is worth more than adjectives. You can't trace it, but you can read the
  technique off it.
- Size in use matters: a thing that must read at 64px is a different drawing from a slide.

## 3. The workflow

1. Write the minimum guide that passes lint at `style/experiments/oneoff-<slug>.json`:
   `id`, semver `version`, `status: draft`, a `palette` with ≥2 named hex colours,
   `rendering`, a non-empty `avoid`, `prompt.template` with `{subject}` and `{style_block}`,
   and `hard_rules` (with the no-text rule).
2. Lint and dry-run it, and show the user the assembled prompt before spending a call:
   ```bash
   stylelock style lint --style-version style/experiments/oneoff-<slug>.json
   stylelock generate "<subject>" --style-version style/experiments/oneoff-<slug>.json \
     --allow-draft --tags none --dry-run
   ```
3. Generate the same way, without `--dry-run`, with `--provider openai` (or your provider).
4. `--tags none` (any tag no reference carries) **is not optional.** Every anchor in the
   library is project-style art and drags the picture back toward it. Check the dry-run's
   reference list is empty, unless you registered references for this one-off.
5. Version the throwaway guide as it is corrected (0.1.0 → 0.2.0 → …). It's cheap and keeps
   each sidecar reproducible.
6. Deliver into a dated folder with a `build.log` and a short `README.md`, like any batch.
   Don't add one-offs to a placement catalogue.

## 4. Define the style by what it IS, never by what it isn't

The most expensive one-off trap: listing everything the project style does (no outlines,
gradients everywhere, occlusion, speculars) and banning it. The result is technically
off-style and completely dead: flat, matte, bare.

The reference was never flat. Read it for what it **has**:

| | Ask |
| --- | --- |
| **Surface** | gloss or matte? specular sheen anywhere? highlights on rounded forms? |
| **Shading** | flat fills or gradients? occlusion where forms meet? contact shadows? |
| **Light** | what is emissive? does it bloom? **where exactly** are the light sources placed? |
| **Colour** | saturated or muted? contrast? warm or cool? what is the darkest value? |
| **Detail** | rich with seams and trim, or deliberately sparse? |
| **Geometry** | the actual shapes. Say them out loud; they are what gets missed most. |

Being different from the project style is a side-effect, never the specification.

## 5. Style in the guide, content in `--extra`

The same split as house work (`briefing.md` §1):
- gloss, palette and light behaviour go in the one-off guide, versioned;
- the view, the layout and what's on the desk go in `--extra`, per image.

## 6. Two constraints that hold even for throwaways

- **Everything goes through `stylelock generate`.** There's no raw-API path for throwaways
  either. It costs nothing: same command, different `--style-version`.
- **No text in generated images.** `hard_rules` carries the no-text rule in a one-off guide
  too. If the image needs lettering, add it afterwards over a blank plate generated for the
  purpose. If someone genuinely wants generated lettering, that's a deliberate decision to
  change the rule, not something to slip past the linter.

## 7. Iterating

- **Offer option B rather than replacing A** when the target is fuzzy. Brief B against named
  differences (frame colour, where the lights sit, the shape of an opening). Users often keep
  both.
- Renderer habits that showed up on off-style work too:
  - it warms whites;
  - a named object isn't a described one;
  - lights land in the wrong place unless positioned;
  - gloss raises baked-shadow amounts, so strip and `--report`.

  See `briefing.md` §3–4.
