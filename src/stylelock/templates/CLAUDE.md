# Image generation project (stylelock)

This folder is a **stylelock** project: a versioned style guide (`style/`), a curated
reference library (`references/`), and everything generated against them.

- **Every image goes through `stylelock generate`.** Never call an image API directly, not
  even in a throwaway script - that skips the style spec, the anchors and the provenance
  sidecar.
- The subject names *what* to depict, never how it looks. Per-image direction goes in `--extra`.
- An `active` guide is immutable: change the style with `stylelock style bump`.
- Reject with a reason from `stylelock review reasons`, never free text.
- Check the setup with `stylelock doctor`; preview a prompt with `stylelock generate ... --dry-run`.

If the stylelock skill is installed, it has the full workflow (briefing, review,
post-processing). If `stylelock` is not on PATH, see https://github.com/VitaliyNikolaev777/stylelock.
