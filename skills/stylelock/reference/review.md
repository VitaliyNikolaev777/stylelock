# Review, records and handover

Read when judging a batch, delivering assets, or running generation with several agents.

---

## 1. The review loop

Every image `stylelock generate` writes has a provenance sidecar (`<stem>.json`) with
`status: unreviewed`.

```bash
stylelock review pending                       # what still needs a verdict
stylelock review accept outputs/<img>.png --note "why it passed"
stylelock review reject outputs/<img>.png --reasons off-palette,baked-ground --note "..."
stylelock review report                        # what to change in the guide
stylelock review reasons                       # the vocabulary
```

**Judge before deciding:**
1. Open the image (you can read PNGs) beside an **accepted** image from the same variant and
   type. Don't judge it against the guide's prose (`guides.md` §5).
2. Check it at **real display size** and at **1:1**. Zoom to 2–3× for geometry and text.
3. Check it against `hard_rules`: sweep every sign, screen, book and shopfront for lettering.
4. For transparent assets, run `strip_contact_shadow.py --report` and the `edge` column of
   `measure_image.py`.

**Reasons come from a fixed vocabulary**, because free text can't be counted, and an
uncounted reason never makes it back into the guide:

| Reason | Means |
| --- | --- |
| `off-palette` | colours outside the palette, or an accent over-used |
| `wrong-rendering` | shading, line weight or texture is wrong |
| `too-detailed` | busier than the detail level allows |
| `too-simple` | under-rendered, reads as unfinished |
| `wrong-lighting` | glow, gradients or dramatic lighting crept in |
| `bad-composition` | framing, negative space or focal hierarchy is off |
| `off-mood` | the tone is wrong even though the surface is right |
| `artifact` | anatomy, geometry or text garbling |
| `prompt-miss` | on-style but not what was asked for |
| `content` | provider refusal, safety block or unusable subject matter |
| `baked-ground` | a transparent asset came back on a ground slab or contact shadow |

If a genuinely new failure mode keeps recurring, don't invent a free-text tag (`reject`
refuses unknown ones). Use the nearest tag plus a precise `--note`, tell the user, and
suggest proposing the new reason upstream (an issue on the stylelock repo). An uncounted
reason never makes it back into the guide.

`review report`:
- counts reasons per guide version and per reference;
- once a reason crosses the threshold, suggests tightening that section of the guide (then
  bump);
- flags any reference attached to most rejects, so you can inspect it for off-style content
  or demote it out of `anchor`.

Reject reasons only help if they're honest. Record the reject even when you fixed the image
in post, and keep the rejected file as evidence.

## 2. Where the record lives

- **The sidecar is the prompt archive.** It holds:
  - the subject verbatim;
  - the full assembled prompt;
  - negatives and references with roles;
  - the guide file and version, variant, type and character;
  - provider and model;
  - a fingerprint (identical prompts share it).
- **`--extra` is not stored separately, but it's recoverable.** It's appended after the
  style block, which always ends with the `hard_rules` paragraph:
  ```python
  MARK = "Absolute rules, these override everything above:"
  extra = sidecar["prompt"].split(MARK, 1)[1].split("\n\n", 1)[1]
  ```
- **Scratch files are not a record.** Draft subject and extra files in a temp dir disappear;
  the sidecar holds the text of every call actually made.
- **Plans are written before generating** for anything bigger than one asset (the layer split
  and object plan, `briefing.md` §6), and kept next to the delivery.
- **Correct conclusions in place, with a date.** When an earlier note turns out wrong, amend
  it ("2026-xx-xx correction: …") rather than deleting it. The rejected rounds are the useful
  part.

## 3. Delivering a batch

`outputs/` is the audit trail: timestamp-plus-slug filenames, each beside its sidecar. Nobody
can hand those to a designer, so deliveries go into a structured folder:

```
<delivery>/
  README.md        what was asked, what was delivered, what went wrong and what fixed it,
                   known gaps stated plainly
  build.log        one line per asset: semantic name, px size, SOURCE raw filename,
                   every fix applied (shadow stripped, re-cut, recoloured), every reject + reasons
  plate.png / objects/<semantic-name>.png / characters/<name>-pose-N.png / ...
  history/         superseded versions kept for comparison
```

- **Never move or rename a raw output. Copy it.** The sidecar stays with the raw file, and
  `build.log` is the link between a delivered name and its provenance.
- Log the pixel size, so a sprite at the wrong scale is visible in the log.
- Keep superseded variants registered (e.g. three difficulty levels of one hidden object)
  rather than overwriting them, so switching is a one-line edit with no regeneration.

## 4. Catalogue hygiene (if you place sprites)

- A fix that lives only in a dated corrections folder doesn't reach the catalogue. Before any
  composition, check each catalogue entry's `file` against the newest version of that asset.
- After any refiling, check the paths actually exist:
  ```python
  [k for k, v in cat["assets"].items() if not os.path.exists(os.path.join(root, v["file"]))]
  ```
  Then cross-check the asset folders against the catalogue keys. An unregistered sprite is
  invisible, exactly as an unregistered reference is to `refs validate`.
- If a project has more than one catalogue, check which one a composition declares before
  adding entries.

## 5. Running generation with parallel agents

Parallel agents speed up large batches. Four failures recur, and three of them are silent:

1. **Name collisions.** Give every agent the **full** list of existing asset names, and expect
   duplicates anyway. Agents can't see each other's in-flight work, so check before
   registering.
2. **Shared `outputs/`.** `ls -t outputs/*.png | head -1` returns a sibling's file. Agents
   must use the path `stylelock generate` **prints**. Give each its own scratch directory too.
3. **Registration and catalogue writes stay serial, with you.** Concurrent writes to one JSON
   file clobber silently. Agents generate, strip and report; you register.
4. **"Completed" means nothing until you check the disk.** A hung agent isn't worth resuming
   twice. Take the remaining work over directly, usually with a shell loop.

Every agent brief should state:
- the CLI form and the `--dry-run` gate;
- `hard_rules` and any palette reservations;
- that shadow stripping must be verified to 0;
- "do not edit catalogues, compositions or guides";
- the exact output folder.

Agents that get all of this produce honest reports, including the items that still failed.
