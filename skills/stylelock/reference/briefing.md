# Briefing a generation

Read before writing any `subject` or `--extra`, and again whenever a render fights you twice.

Every rule here was paid for in rerolls on gpt-image-class renderers. The numbers are from
real batches; treat them as orders of magnitude, not constants.

---

## 1. Three slots, three jobs

| Slot | Holds | Never holds |
| --- | --- | --- |
| `subject` | **what** to depict — the thing, the place, who is there | how it looks. Style words in the subject fight the style block and cause drift. |
| `--extra` | direction for **this one picture** — view, crop, layout, what stands where, edge rules | anything that is true of the style in general |
| the guide | properties of the **style** — palette, rendering, gloss, detail density, how light behaves | anything that is true of one picture only |

Getting it backwards produces either a guide that suits one image, or a correction retyped
on every call. If you catch yourself pasting the same sentence into `--extra` for the third
time, it is a guide change: `stylelock style bump`, edit the new file (see `guides.md`).

## 2. Keep `--extra` short, and lead with rendering

`--extra` renders **after** the style block. A long one drowns the style.

- In practice, an extra that grew from ~200 to ~750 words over one session (every added word
  policing object placement) made the output visibly "more cartoonish" — the extra had grown
  as long as the whole style block. Cutting it to ~290 words and moving the material-fidelity
  paragraph first fixed the drift *and* got every planned object into the frame for the first
  time.
- **Target 250–300 words.** Order: rendering fidelity → content bans (no people, blank
  surfaces) → geometry rules → frame-edge rules.
- A fidelity paragraph that works names materials concretely: a gradient from lit to shaded
  side on every surface, no flat unshaded fills; grainy timber with plank seams; brushed metal
  with a rolled edge; matte cloth with a hem and a fold; occlusion where forms meet; a small
  specular on anything rounded; and the value steps (dark framing layer, bright readable
  middle, pale hazy distance).
- The way to avoid a long extra is a shorter subject — see §6, plan layers.

Always `stylelock generate ... --dry-run` first. It prints the assembled prompt and which
references will attach, and costs nothing.

## 3. Concrete beats vague

The renderer ignores qualitative asks and obeys physical ones.

**Name a referent substance, not a hue or a ban.**
- "Deep toffee brown, the colour of set treacle toffee, never yellow or buttery" works.
  "In the tan family, not yellow" never did.
- In practice, a canopy that came back 55% inside a forbidden warm band dropped to 3.4% once
  told "the colour of a fired clay flowerpot".
- "The pale, neutral, slightly blue-grey of a new galvanised steel bucket" stopped steel
  drifting to sage-green paint.

**Name a substitute shape, not a prohibition.** "A plain flat upright rectangle, like a book
standing on a shelf with its cover facing you" beat three rounds of "not three-quarter view".

**Ask for a positive structure, never an absence.** The renderer cannot draw "empty".
- Four rounds of "leave four clearings" produced 3, 2, 2 and none.
- "A town built around four paved garden squares, one per quarter, paths running to a central
  fountain" worked first call.
- The same applies to "leave space for the UI": describe the calm structure that *is* there.

**Give abstract qualities physical, checkable markers.** "Flying, not floating" only landed
as: horizon in the top third, everything below seen from above, clouds *below* the craft.

**Naming an object is not describing it.** "A cabin looking out through a window" gave a flat
wall with a window in it, twice. Naming the geometry gave the real thing on the next call:
the shape of the opening, what frames it, how the surfaces step and wrap. Do the same for
lights: **say where they sit**, or they land somewhere plausible and wrong.

**Frame edges.** "A clear margin from the border" fails. What works is checkable:
- *"no hand, finger, foot, elbow or strand of hair touches or crosses any edge, and an
  outstretched arm points inwards towards the middle"*;
- for a plate object, *"set well in from its left border, with ground showing between it and
  the border"*;
- for a clipped sprite, *"DRAW IT SMALL IN THE FRAME"* plus an explicit one-tenth margin per side.

Verify with `measure_image.py` (the `edge` column must be 0 on transparent assets).

**Built geometry — the ruler rule.** At 2–3× zoom, generated doorways bow, lintels sag and
openings turn trapezoid. Put this **first** in the extra when anything built matters:

> Everything built by people is straight and true, drawn as if set out with a ruler: posts,
> planks, rails, frames and lintels have dead-straight parallel edges of even thickness
> meeting at clean square corners. Uprights stand exactly vertical and cross-members exactly
> horizontal. Nothing manufactured bows, sags, leans or tapers. Only living things curve.

It costs something — the picture tends to come back flatter and emptier. Keep the previous
render to compare.

**Objects on an angled surface: state both converging lines and their directions.**
- One display took 12 generations across 6 rounds: "three-quarter" gave isometric, "flat
  elevation" gave a cut-out.
- What worked was two labelled clauses, each with a consequence: *"TURNED, so the tops come
  DOWN towards the right; the tallest point is at the far LEFT"* and *"BUT ALMOST NO DOWNWARD
  TILT, so each mouth is a narrow ellipse five times as wide as it is tall"*.
- Measure the surface in the plate before briefing it. On a receding box the top edges fall
  and the bottom edges rise.

**Routes must connect.** For any walkable scene, trace a walking line from the bottom edge to
every destination. If it crosses grass, a fence, a kerb or a wall, the route is broken
however convincing the furniture looks.
- The renderer will draw turnstiles against a solid wall, stanchions with no fence, and a
  road behind a verge.
- Specify the **opening first**, then the object in it: *"the fence stops here and the gap is
  open, you can see sunlit ground through it, and the turnstile lanes stand IN that opening"*.
- An entrance is a hole in a boundary, not a mechanism placed near one.
- Don't over-correct to "nothing may stand on the path". The rule is that the way through is
  visible and passable.

## 4. Renderer fallback biases: change the setup, don't reword

When a brief is hard, the renderer does not try harder. It substitutes a default:

| Asked for | Comes back as |
| --- | --- |
| an arrow pointing **right** | an arrow pointing **left** (5+ failures in practice) |
| a hard pose (head turned back, legs splayed to drink) | a plain **standing** figure |
| a **set** of three | a **single** item (check whether your type says "ONE subject"; the type wins over the brief) |
| "console hardware" for any vehicle or workstation | **car** furniture: louvred vents, HVAC clusters |
| a cool white surface | **warmed** cream/beige ("nothing is cream, beige, ivory, sand or tan — if it looks warm, it is wrong" fixes it) |
| a count of anything | the wrong count — never ask it to count |
| a full-bleed frame **and** an empty centre | oscillation between a floating frame and a translucent wash (fix in post, `solidify_frame.py`) |

Rewording escalates cost and drifts the composition. Two things work:

1. **Change the physical setup.** A signpost that pointed the wrong way five times came out
   right first time once it was moved from against a fence into open grass.
2. **Fix it afterwards** (`post-processing.md`: mirror, mask, crop).

**If a shape fights twice, change the subject, not the wording.**
- In practice, six objects each burned 3+ attempts locked in a raised three-quarter view
  (suitcase, cash tin, carrier bag, tape dispenser, heaped tray, brazier rim).
- Every substitution came back right on the **first** call: teddy bear, pigeon, kite,
  flat-packed box, tiered stand.
- The offending word is often in the subject. "The cockpit of a **stubby** tug" failed three
  times; "a **wide** tug" worked.
- Inherently flat or side-view subjects come back clean every time: garments, birds,
  locomotives, kites. Choose the silhouette rather than fight the renderer.

Accepted exceptions, so don't burn calls on them: a cylinder keeps a thin top rim, and a
bowl always shows an elliptical one. Reroll only a full top face *plus* a receding side.

**Content vs artefact.**
- An emphatic, enumerated ban of **content** often works. *"absolutely no numbers, no digits,
  no dates, no letters and no day names anywhere on it, just blank squares"* gave a clean
  calendar first call.
- A ban on something the renderer does **structurally** never works: baked shadows, a dark
  footwell under a console, a base board under a row of objects. Accept it and fix it in
  post, or control it (accept the board, set its angle).

## 5. Text

Image models garble lettering, so `hard_rules` forbids it on every prompt. Even so:

- **Drawing a landmark in full tempts the renderer to label it.** In practice, four of eight
  baked map candidates came back with shop-sign lettering, `hard_rules` notwithstanding.
  Sweep every building at 2× before shipping.
- When a topic is *named* by text (a newspaper, a notice, a calendar), carry it by
  **silhouette and material**. A blank sheet hanging from one red drawing pin reads as
  "urgent notice": the pin does the urgency, the sheet the noun. A newspaper without print
  read as a scroll until recoloured to newsprint grey with blank column blocks.
- If lettering is genuinely needed, add it afterwards in the design tool, over a blank plate
  generated for the purpose.

## 6. Plan layers before prompting

Given a screen mockup, **do not prompt from the picture.** Split it first:

1. **UI**: rails, cards, inventory, price bubbles (never generated)
2. **Markers**: hotspots, pins, numbers, routes (never generated)
3. **Sprites**: people, animals, merchandise, clues (generated separately, transparent)
4. **The plate**: terrain, architecture, *empty* fixtures (the only thing this call generates)

Roughly a third of what reads as "the background" in a mockup is layers 1–3. In practice, one
scene took **nine** generations when the subject described people and merchandise, because
the renderer paid for each newly named object by dropping another. The next, planned this
way, took **two**.

- Before writing a subject, check which sprites already exist. Usually most of them do.
- Say explicitly that blank panels, bare shelves and empty trays are the **goal**, or the
  renderer invents filler.
- Write the plan to a file next to the build log (layer split, existing assets, the plate's
  objects with normalised x/y) and get a nod before spending calls.

## 7. Lock a recurring character with a subject reference

A `cast` entry in the guide is not enough to hold a character on-model. Describing the design
in words does not hold it either.

```bash
stylelock refs add path/to/approved-sprite.png --role subject --id hero-v1 \
  --demonstrates "canonical design of the hero: face, outfit, colours"
stylelock generate "hero, the same figure drawn three times in a row" \
  --type character --character hero --ref-ids hero-v1 --roles subject --extra "..."
```

- **`--roles subject` is mandatory.** `--ref-ids` alone leaves roles at the default `anchor`.
  That filters the subject ref straight back out, and the call runs with no reference while
  looking correct. Check it with `--dry-run`.
- Register refs from **approved art in the current style**. A subject ref from an older
  guide drags the result toward that guide.
- In practice: words alone drifted eye size, skin tone and shoe colour; spelling every detail
  out fixed some and regressed others; attaching the sprite was on-model first try. The same
  method held an animal across four sheets with no drift.
- **Sheet geometry depends on the figure.** Three figures across a 3:2 frame fits a child.
  A tall animal needs **two** per sheet plus an explicit vertical margin.
- When ordering matters, the **first** attached image dominates. To get a stylised variant of
  a character, put the proportions reference first and the costume master second, and say
  which image is for what ("image 2 is costume only").
- When the guide's prose disagrees with the cast it describes (e.g. "realistic proportions"
  for a stylised cast), don't quote the guide. Spell out the cast's actual construction in
  `--extra`, and fix the guide with a bump.

## 8. Composing for how the asset is used

- **Ask which crop the asset gets before composing for it.** "A panel covers the middle" and
  "it gets cropped to a thin strip" pull in opposite directions.
- **Art that will be cropped must be an allover pattern, not a composition.** A banner with a
  calm middle is destroyed by a strip crop, which cuts *from* the middle. Spread the motif over
  the full height, with no focal point. Verify by cutting bands at three heights.
- **Budget usable ground before adding oversized elements.** A map that must carry big
  landmarks cannot also spend a third of its canvas on surrounding water and a dense ring.
- **A full-bleed asset is meant to be cut by the border**: scale up and centre-crop, never
  stretch. This inverts the usual frame-edge rule.
- **Busyness lives in two keys.** When a type needs a calmer picture than the house style
  (maps, card art), override `rendering.detail_level` and the colour-hierarchy rule. Give it a
  checkable test: *"if you half-close your eyes, ONLY the landmarks should still stand out"*.

## 9. Vague quality asks: name the dials

"More futuristic", "more like a panel", "more premium" are not briefs, and that is not the
user's problem to fix.

- Decompose the quality into the dials that actually control it (rake angle, how much of the
  frame it takes, number and depth of recesses, how far it wraps), say what each costs, and
  offer two or three points on the scale.
- **Offer a second option rather than a replacement.** Keep A, brief B against named
  differences. It is cheaper than iterating one image toward a target nobody has described.
- **Every removal costs a cue.** Stripping out a screen, a glowing panel and the controls for
  good product reasons can together remove everything that said "cockpit". Expect to put the
  signal back somewhere harmless, usually at the edges, where the interface never draws.

## 10. Providers

- `gpt-image-1.5`: real alpha (`background: transparent`). Sizes 1024², 1536×1024, 1024×1536
  only, so there is **no 16:9**. Deliver 3:2 and crop, and say so.
- Newer OpenAI image models may reject `background: transparent`. For a transparent copy,
  use the chroma-key route (`post-processing.md`). Never redraw approved art on another model
  "exactly"; it drifts.
- Retired models can still appear in `models.list()`, so trust a real call, not the listing.
- Per-call overrides: `--option size=1536x1024`, `--option model=...`. Defaults belong in the
  guide's `provider_defaults`, per type.
