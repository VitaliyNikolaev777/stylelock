# Fixing it in post

Read after a batch lands, before rerolling anything, and whenever an artefact survives a
reworded brief.

All scripts are in this skill's `scripts/` folder. They are standalone Python that needs only
Pillow (`pip install pillow`, or `uv run --with pillow python <script>`). None of them calls an
image API, so none bypasses the wrapper. Every one has `--help`, and most have `--report` to
measure without writing.

**The general rule:** when an artefact appears, spend **one** call checking whether wording
fixes it, measure the result, and say what you measured. If the number doesn't move, stop
rewording and post-process. When the picture is right and only a measurement is wrong, fix
the measurement.

---

## 1. Measure before rerolling

`scripts/measure_image.py a.png b.png accepted.png` prints these columns:
- **grain**: mean |img − blur(1.2)|
- **flat** and **modelled**: pixel fractions
- **sat** and **val**: mean HSV, over opaque pixels only on sprites
- **hue_conc**: 1.00 means monochrome
- **warm** and **cool**: band shares
- **edge**: alpha touching the frame

- Soft complaints ("cartoonish", "messy", "pasted-on", "is it bluer?") almost always have a
  number behind them. In practice, measuring **disproved** the planned fix both times it was
  tried:
  - a plate called "cartoonish" was the busiest of its set (51% strongly modelled), so the
    "add fidelity" fix would have made it worse;
  - a plate called "messy" had normal grain (4.21 against 3.99–4.49 on accepted plates), so
    the real fault was geometry.
- **Compare against an accepted image, not against the guide's prose.** A metric compared to
  the wrong baseline is worse than none, because it is convincing.
- **"Pasted on" lives in saturation and value.** In practice, characters matched their plates
  within 0.02 on every axis. Shop goods ran 0.11–0.16 higher in saturation, and one item was
  0.31 brighter than the whole plate, because each standalone sprite is lit as a hero prop.
  Before "fixing" it, ask whether the pop is wanted: clickable items arguably should separate.
- **Palette shift**: the warm (hue 20–70) vs cool (180–260) shares settle "is it actually
  bluer" in one number.
- **Large neutral areas punish mean saturation.** A cream apron or grey hair drags a
  correctly coloured figure down, so judge the face first and the number second.
- **Detectors that do not work, so don't rebuild them:**
  - mirror asymmetry as a perspective score (it confuses an asymmetric shape with a turned view);
  - colour-blob detection on images where two materials share a hue (sand vs paving);
  - colour-keyed furniture detection on a uniformly warm plate (use luminance steps instead);
  - "widest row" ellipse ratios (it finds the feet, not the top).
- **The rule:** when a detector disagrees with your eye about **geometry**, trust the eye and
  mock the asset into context. When it disagrees about **tone or texture**, trust the number.
- Say so when a check was by eye. Don't dress an eyeball judgement up as a measurement.

## 2. Baked contact shadows: always strip

`scripts/strip_contact_shadow.py outputs/*.png --in-place`, then `--report`.

- Renderers bake a soft grey pool or ground slab under roughly **6 in 10** transparent-
  background objects, whatever the guide says. It is **not predictable from the brief**: in
  practice amounts ranged from 7 to 34,000 px with no pattern by pose, volume or material.
  Don't look for a predictor. Strip every batch.
- Wording does not fix it. An explicit "no contact shadow, empty alpha where the object is
  not" moved one object from 15,612 stray pixels to 16,001.
- Guides that ask for gloss or occlusion slab harder (1.5k→35k px in practice).
- The subject-reference route (the edit endpoint) slabs less often, about 1 in 5, but still
  not zero.
- It matters beyond looks: a compositor that anchors bottom-centre on the alpha bbox gets
  pushed up off its mark and shrunk by the pool.
- The script separates shadow from antialiasing **by geometry**, not by alpha threshold:
  faint pixels touching the solid body are edge, detached ones are shadow. Verify `--report`
  reads 0 detached px.
- A shadow that is **opaque and fused** to the subject can't be stripped. Regenerate it.

Use `reject --reasons baked-ground` when a slab forces a redraw, so the count reaches the
report.

## 3. Transparency from a model that has none: chroma key

`scripts/chroma_key.py in.png out.png --checker [--backdrop '#RRGGBB']`

Some models can't output alpha (`background: transparent` is rejected).

- **Don't redraw approved art "exactly" on another model to get alpha.** In practice it came
  back sketchier, lost small features, shuffled effects between panels and changed
  proportions.
- **Approved opaque image → transparent copy:** add a type with `background: opaque` that
  briefs the backdrop as *"one flat pure green #00FF00, no green spill, no shadow on the
  backdrop"*. Attach the approved image as a `subject` ref so the call goes through the edit
  endpoint, brief "change ONLY the backdrop", then key it.
- **New art:** generate straight onto green and key it. One call gives both a transparent and
  an opaque copy (`--backdrop`).
- Keying is a greenness ramp, g − max(r,b): opaque at ≤40, clear at ≥120, then a despill.
- Two failure modes of the edit, and both need a re-brief:
  - small effects (embers, sparks) get silently dropped, so name every effect that must survive;
  - translucent auras and smoke key to olive fringes, so ask for effects as **solid opaque
    inked shapes**.
- Only valid when nothing in the subject's own palette is green. Always review over the
  checkerboard against the original, panel by panel.

## 4. Local edits vs redraw

Often the ask is to change one element and keep the rest of the picture. Local edits cost no
API call.

**The decisive question: does the background behind the thing you're changing exist anywhere
else in the image?**
- Yes (grass, sky, a uniform board): the edit will be invisible.
- No (a patterned fence that is only visible behind the sign): every fill ghosts, so redraw.

**Flip a directional element:**
`scripts/mirror_region.py plate.png --box X0,Y0,X1,Y1 --centre X [--preview out.png]`
- Mirror about the **post's centreline** to swap which side of the post a sign hangs on. That
  fixes mounting.
- Mirror about the element's own box only when it straddles its support evenly. Otherwise
  the arrow turns round but hangs from the wrong end.
- A plain rectangular mirror drags background with it. That's fine over uniform ground, but
  it seams across a gradient or a material boundary.

**Mask when a plain mirror would drag background.**
- Composite the flipped crop through the object's own silhouette, dilated (`MaxFilter(7)`)
  and feathered (`GaussianBlur(1.4)`). A hard threshold leaves a ghost ring.
- Choose the mask channel by what separates the object from its surround: lightness alone,
  or warmth plus lightness when both are similar materials.

**Fill a vacated area.**
- Sample from the **same rows** so a vertical gradient carries.
- Tile alternate copies **mirrored** so seams are continuous.
- Blur about 0.8px inside the patch only.
- Measure the stddev of the source strip first, because a "plain" strip picked by eye can
  contain an edge that tiling stamps everywhere.

**Always:** archive the previous version to `history/` first, report the changed-pixel count
and bbox, and check at **1:1** as well as zoomed. Repairs that look bad zoomed are often
invisible at working size, and vice versa.

**Crop when an artefact can't be prompted away.**
- A dark band (a footwell under a console, a ground strip) can survive explicit bans; in
  practice one was at 72% dark pixels after being told not to draw it.
- Profile it row by row, find where it starts, and cut above it.
- Those crops often land near 16:9, the ratio some models won't generate directly. That's a
  better outcome than another reroll.

## 5. Frame overlays: fix the alpha geometrically

`scripts/solidify_frame.py outputs/frame.png --in-place` (or `--report`)

- Renderers won't reliably fill to all four borders **and** leave the centre empty. In
  practice they oscillated between a small floating frame and a full frame fading to a ghost
  wash (3.3–8.4% faint pixels vs 0.2–0.3% when it behaves), on the same prompt.
- The picture is right; only the alpha is wrong. The script finds every opening as the
  low-alpha regions the border can't reach, so side windows survive. It makes everything else
  opaque, feathers the rim and flattens the RGB under the hole so no compositor drags a halo.
- Verify: centre-opaque 0%, edge coverage 100% on all four sides, faint ≤0.5%.
- Expect heavier structure than briefed (a smaller opening). Harmless once the frame is cropped.

## 6. Holes punched through transparent assets

`scripts/fill_interior_holes.py map.png --color '#RRGGBB'`

- Asked for a transparent background, a model will also knock out large flat interior fills,
  so a map comes back as a lattice.
- The script floods from the canvas edge, and anything transparent the flood can't reach is
  filled.
- Run it **after** halo cleanup (`split_character_sheet.py`), since a halo can bridge a hole
  to the exterior.

## 7. Plates competing with sprites

`scripts/knock_back_background.py plate.png --strength 0.25`

- Plates and sprites drawn from one guide share a saturation and value range, so sprites
  compete instead of sitting on top. Wording doesn't fix it: in practice mean saturation went
  90.4%→90.6% across a rewrite.
- The script desaturates and slightly lifts the **background only**:
  - 0.15 is subtle;
  - 0.25 is usual;
  - 0.40 starts to look washed out.

## 8. Sheets, sprites and composition

- **Character sheets:** generate all poses in ONE call so they match, then
  `scripts/split_character_sheet.py sheet.png --name hero --out <dir>`. It strips the
  low-alpha halo (≤24), cuts by empty columns, trims and pads, and prints
  `N sprite(s) from <raw>`, which is the line for the build log.
- **Composition:** `scripts/compose_scene.py compositions/scene.json` places sprites on a plate.
  - It reads a catalogue `height` (a fraction of frame height at the near ground edge) and a
    `ground` ramp (`far`, `near`, `far_scale`), anchors bottom-centre and paints in y order.
    `--table` prints pixel coordinates without rendering.
  - It crops to the alpha bbox first, because **catalogue height describes the object, not the
    file**. An uncropped 1024 canvas with padding underneath otherwise floats and renders small.
  - **Solve `scale` from a target pixel height; never guess it.** `s = far_scale + (y − far) /
    (1 − far) · (1 − far_scale)`, then `scale = target_px / (height · s · H)`. When
    `far == far_scale` this collapses to `s = y`, so a shelf high in the frame shrinks to a
    speck even though it isn't far away. In practice that turned every object in six scenes
    into 13–16px specks until solved this way.
  - Targets that worked:
    - goods on a shelf about 78px;
    - larger props 96–150px;
    - a standing child about 330–360px.
  - Indoors, use a flatter ramp than outdoors. Each shelf board of a tall unit needs its own
    scale.
  - **Derive catalogue heights from real-world size.** Set `height = base_h · real_m /
    base_m` from one calibrated object and store `real_m` alongside. A flat default for
    everything makes a compass and a hat place at the same size.
  - **Known gaps:** nothing restores a soft grounding shadow after stripping, so composited
    sprites float slightly. There's also no z-order control: a sprite can't stand *behind* a
    counter baked into the plate. Both are cheap local additions if needed.
- **Recolour without an API call:** shift each pixel by its own offset from the source mean,
  `new = target + (old − source_mean)` per channel, clamped, with alpha untouched. A flat
  overwrite discards the renderer's fine grain and makes the variant subtly smoother than its
  sibling.
- **Hidden or "find it" objects:**
  - judge at 1:1, never zoomed;
  - report the visible size of the *telling detail*, not the sprite height;
  - "hard to spot" and "legible once found" are opposite pressures: a bite mark has to be big
    enough to read as a bite, a tuft of fur means the same at any size;
  - fix proportion inside the sprite before scale;
  - camouflage is placement.
