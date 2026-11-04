import json
from pathlib import Path

import pytest

from stylelock.cli import main
from stylelock.manifest import Library, Reference
from stylelock.prompt import assemble
from stylelock.providers import get_provider
from stylelock.providers.dryrun import _solid_png
from stylelock.style import StyleError, StyleGuide


# -- project discovery and init ------------------------------------------

def test_init_creates_a_project_that_lints(project):
    from stylelock.config import is_project

    assert is_project(project)
    assert (project / "CLAUDE.md").exists() and (project / ".env.example").exists()
    guide = StyleGuide.load()
    assert guide.validate() == []
    assert guide.status == "draft"
    assert guide.data["updated"]


def test_init_never_overwrites(tmp_path, capsys):
    root = tmp_path / "p"
    root.mkdir()
    (root / "CLAUDE.md").write_text("mine")
    assert main(["init", str(root)]) == 0
    assert (root / "CLAUDE.md").read_text() == "mine"
    assert main(["init", str(root)]) == 0
    assert "already a stylelock project" in capsys.readouterr().out


def test_project_found_by_walking_up(project, monkeypatch):
    from stylelock.config import find_root

    monkeypatch.delenv("STYLELOCK_HOME")
    deep = project / "outputs" / "a" / "b"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    assert find_root() == project


def test_no_project_is_a_clean_error(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("STYLELOCK_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main(["doctor"]) == 2
    assert "stylelock init" in capsys.readouterr().err


def test_env_file_is_loaded_from_the_project(project, monkeypatch):
    import os

    from stylelock.config import load_dotenv

    (project / ".env").write_text("OPENAI_API_KEY=from-project\n")
    load_dotenv()
    assert os.environ["OPENAI_API_KEY"] == "from-project"


def test_refs_add_registers_into_the_project(project, tmp_path):
    src = tmp_path / "hero.png"
    src.write_bytes(_solid_png(8, 8))
    assert main(["refs", "add", str(src), "--role", "anchor", "--demonstrates", "the look"]) == 0
    assert (project / "references" / "anchors" / "hero.png").exists()
    lib = Library.load()
    assert [r.id for r in lib.references] == ["hero"]
    assert lib.references[0].path.exists()


# -- style guide ---------------------------------------------------------

def test_shipped_guide_is_valid(guide):
    assert guide.validate() == []


def test_style_block_is_deterministic_and_covers_the_spec(guide):
    a, b = guide.style_block(), guide.style_block()
    assert a == b
    for color in guide.data["palette"]["colors"]:
        assert color["hex"] in a
    assert "Do not include:" in a


def test_validate_catches_bad_hex_and_template(guide):
    broken = json.loads(json.dumps(guide.data))
    broken["palette"]["colors"][0]["hex"] = "E4572E"
    broken["prompt"]["template"] = "{subject}"
    problems = StyleGuide(path=guide.path, data=broken).validate()
    assert any("bad hex" in p for p in problems)
    assert any("{style_block}" in p for p in problems)


def test_load_picks_the_highest_version(tmp_path):
    for n, ver in ((1, "1.0.0"), (2, "2.0.0"), (10, "10.0.0")):
        (tmp_path / f"style-guide-v{n}.json").write_text(json.dumps({"version": ver}))
    assert StyleGuide.load(None, style_dir=tmp_path).version == "10.0.0"


# -- prompt assembly -----------------------------------------------------

def test_every_prompt_carries_the_style_block(guide, library):
    bundle = assemble("a lighthouse on a cliff", guide, library)
    assert bundle.prompt.startswith("a lighthouse on a cliff")
    assert guide.style_block() in bundle.prompt
    assert bundle.style_version == guide.version


def test_anchors_are_default_and_capped(guide, library):
    bundle = assemble("x", guide, library)
    assert [r.id for r in bundle.references] == ["a1", "a2"]


def test_role_refs_are_scoped_and_impurities_flagged(guide, library):
    bundle = assemble("x", guide, library, roles=["texture"])
    assert [r.id for r in bundle.references] == ["t1"]
    assert "match its texture only" in bundle.prompt
    assert "ignore its background colour" in bundle.prompt


def test_tags_are_and_matched(guide, library):
    assert [r.id for r in assemble("x", guide, library, tags=["hero"]).references] == ["a1"]


def test_fingerprint_tracks_prompt_and_refs(guide, library):
    base = assemble("x", guide, library)
    assert base.fingerprint == assemble("x", guide, library).fingerprint
    assert base.fingerprint != assemble("y", guide, library).fingerprint
    assert base.fingerprint != assemble("x", guide, library, ref_ids=["a1"]).fingerprint


def test_empty_subject_rejected(guide, library):
    with pytest.raises(ValueError):
        assemble("   ", guide, library)


# -- providers -----------------------------------------------------------

def test_negatives_folded_in_when_provider_lacks_the_field(guide, library):
    from stylelock.providers.openai_images import OpenAIImagesProvider

    bundle = assemble("x", guide, library)
    assert "Absolutely avoid:" in OpenAIImagesProvider().text_prompt(bundle)
    assert get_provider("dryrun").text_prompt(bundle) == bundle.prompt


def test_dryrun_writes_valid_png(guide, library):
    imgs = get_provider("dryrun").generate(assemble("x", guide, library), n=2)
    assert len(imgs) == 2
    assert imgs[0].data.startswith(b"\x89PNG\r\n\x1a\n")


# -- library validation --------------------------------------------------

def test_impure_anchor_is_rejected(library):
    library.data["images"][0]["exclude"] = ["stray gradient"]
    assert any("stylistically pure" in p for p in library.validate())


def test_anchor_cap_enforced(library):
    for i in range(9):
        library.add(Reference(id=f"extra{i}", file="anchors/a1.png",
                              role="anchor", demonstrates="filler"))
    assert any("exceeds the limit" in p for p in library.validate(anchor_limit=5))


def test_unregistered_file_is_reported(library):
    (library.root / "anchors" / "stray.png").write_bytes(_solid_png(4, 4))
    assert any("unregistered image" in p for p in library.validate())


def test_source_folder_is_not_reported(library):
    (library.root / "_source" / "raw.png").write_bytes(_solid_png(4, 4))
    assert not any("raw.png" in p for p in library.validate())


# -- generate wrapper ----------------------------------------------------

def test_draft_guide_blocks_generation(project):
    from stylelock import generate as gen

    with pytest.raises(gen.DraftGuideError):
        gen.run("a lighthouse", provider="dryrun")


def test_generate_writes_image_and_provenance_into_the_project(project):
    from stylelock import generate as gen

    paths = gen.run("a lighthouse", provider="dryrun", allow_draft=True)
    assert len(paths) == 1
    assert paths[0].parent == project / "outputs"
    side = json.loads(paths[0].with_suffix(".json").read_text())
    assert side["status"] == "unreviewed"
    assert side["style_version"] == StyleGuide.load().version
    assert side["subject"] == "a lighthouse"
    assert side["prompt"]


def test_cli_generate_dry_run(project, capsys):
    assert main(["generate", "a lighthouse", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("a lighthouse") and "fingerprint:" in out


# -- review loop ---------------------------------------------------------

def test_reject_requires_a_known_reason(project):
    import stylelock.review as rev
    from stylelock import generate as gen

    img = gen.run("a lighthouse", provider="dryrun", allow_draft=True)[0]
    with pytest.raises(rev.ReviewError):
        rev.reject(img, reasons=["it-looks-bad"])
    with pytest.raises(rev.ReviewError):
        rev.reject(img, reasons=[])

    dest = rev.reject(img, reasons=["off-palette"], note="accent everywhere")
    assert dest.exists() and not img.exists()
    entry = json.loads((project / "rejects" / "log.jsonl").read_text().strip())
    assert entry["reasons"] == ["off-palette"]


def test_report_suggests_spec_changes(project):
    import stylelock.review as rev

    (project / "rejects" / "log.jsonl").write_text("\n".join(json.dumps({
        "reasons": ["off-palette"], "references": ["a1"], "style_version": "1.0.0",
    }) for _ in range(4)))
    r = rev.report(min_hits=3)
    assert r["total_rejects"] == 4
    assert r["by_reason"]["off-palette"] == 4
    assert any("off-palette" in s for s in r["suggested_actions"])
    assert any("a1" in s for s in r["suggested_actions"])


def test_pending_lists_unreviewed(project):
    import stylelock.review as rev
    from stylelock import generate as gen

    img = gen.run("a lighthouse", provider="dryrun", allow_draft=True)[0]
    assert rev.pending() == [img]
    rev.accept(img)
    assert rev.pending() == []


# -- variants ------------------------------------------------------------

def test_variant_replaces_the_palette(guide):
    forest, night = guide.with_variant("forest"), guide.with_variant("night")
    assert forest.variant == "forest"
    assert "#2E8B57" in forest.style_block()
    assert "#2E8B57" not in night.style_block()       # not merged in
    assert "#1B1F3B" in night.style_block()


def test_variant_append_lands_in_the_prompt(guide, library):
    bundle = assemble("a clearing", guide.with_variant("forest"), library)
    assert "Tall tree trunks" in bundle.prompt
    assert bundle.variant == "forest"


def test_unknown_variant_is_an_error(guide):
    with pytest.raises(StyleError):
        guide.with_variant("desert")


def test_variant_scopes_the_reference_set(guide, library):
    library.data["images"][0]["tags"] = ["forest"]
    library.data["images"][1]["tags"] = ["night"]
    picked = assemble("x", guide.with_variant("forest"), library).references
    assert [r.id for r in picked] == ["a1"]


def test_variant_is_recorded_in_provenance(rich_project):
    from stylelock import generate as gen

    paths = gen.run("a clearing", provider="dryrun", variant="night", allow_draft=True)
    side = json.loads(paths[0].with_suffix(".json").read_text())
    assert side["variant"] == "night"
    assert "night" in paths[0].name


def test_shipped_variants_all_validate(guide):
    assert guide.variants
    for name in guide.variants:
        v = guide.with_variant(name)
        assert v.validate() == []
        assert v.style_block()


# -- asset types ---------------------------------------------------------

def test_type_overrides_format_and_provider_size(guide):
    icon = guide.with_type("icon")
    assert icon.asset_type == "icon"
    opts = icon.provider_defaults("openai")
    assert opts["size"] == "1024x1024"
    assert opts["background"] == "transparent"
    assert opts["model"] == "gpt-image-1.5"        # merged, not clobbered by the overlay


def test_type_wins_over_variant_on_conflict(guide):
    both = guide.with_variant("forest").with_type("emblem")
    assert both.variant == "forest" and both.asset_type == "emblem"
    assert "#2E3A5C" in both.style_block()
    assert "#2E8B57" not in both.style_block()


def test_variant_survives_a_type_that_does_not_touch_it(guide):
    both = guide.with_variant("night").with_type("object")
    assert "#1B1F3B" in both.style_block()
    assert "transparent background" in both.data["prompt"]["suffix"]


def test_type_reference_tags_beat_variant_tags(guide, library):
    library.data["images"][0]["tags"] = ["forest"]
    library.data["images"][1]["tags"] = ["icon"]
    picked = assemble("x", guide.with_variant("forest").with_type("icon"), library).references
    assert [r.id for r in picked] == ["a2"]


def test_type_is_recorded_in_provenance(rich_project):
    from stylelock import generate as gen

    paths = gen.run("a fox", provider="dryrun", variant="forest", asset_type="object",
                    allow_draft=True)
    side = json.loads(paths[0].with_suffix(".json").read_text())
    assert side["asset_type"] == "object" and side["variant"] == "forest"
    assert "object-forest" in paths[0].name


def test_unknown_type_is_an_error(guide):
    with pytest.raises(StyleError):
        guide.with_type("poster")


def test_shipped_types_all_validate(guide):
    assert set(guide.types) == {"scene", "object", "icon", "emblem", "diagram"}
    for name in guide.types:
        t = guide.with_type(name)
        assert t.validate() == []
        assert t.style_block()


def test_openai_passes_transparency_through(guide):
    from stylelock.providers.openai_images import OpenAIImagesProvider

    p = OpenAIImagesProvider(**guide.with_type("icon").provider_defaults("openai"))
    params = {k: v for k, v in p.options.items() if k in p.PASSTHROUGH}
    assert params["background"] == "transparent"
    assert params["output_format"] == "png"


def test_type_can_read_composition_not_anchors(guide):
    assert guide.with_type("diagram").reference_roles == ["composition"]
    assert guide.with_type("scene").reference_roles == ["anchor"]


# -- hard rules and characters -------------------------------------------

def test_hard_rules_render_on_every_prompt(guide):
    for variant in [None, *guide.variants]:
        for asset_type in [None, *guide.types]:
            block = guide.with_variant(variant).with_type(asset_type).style_block()
            assert "Absolute rules" in block
            assert "no words, letters, numerals" in block


def test_no_overlay_may_weaken_a_hard_rule(guide):
    broken = json.loads(json.dumps(guide.data))
    broken["types"]["icon"]["hard_rules"] = ["text is fine actually"]
    problems = StyleGuide(path=guide.path, data=broken).validate()
    assert any("hard_rules cannot be overridden" in p for p in problems)


def test_missing_text_rule_is_a_warning_not_an_error(guide):
    broken = json.loads(json.dumps(guide.data))
    broken["hard_rules"] = ["one subject per asset"]
    g = StyleGuide(path=guide.path, data=broken)
    assert g.validate() == []
    assert any("no hard rule about text" in w for w in g.warnings())


def test_every_type_carries_text_in_its_negatives(guide):
    for name in guide.types:
        assert "text" in guide.with_type(name).negative_terms, name


def test_characters_section_renders(guide):
    block = guide.style_block()
    assert "Characters:" in block
    assert "Animals:" in block


# -- cast ----------------------------------------------------------------

def test_selecting_a_character_renders_only_that_one(guide):
    block = guide.with_character("nora").style_block()
    assert "two short braids" in block
    assert "hooded top" not in block
    assert "delivery robot" not in block


def test_no_character_selected_renders_no_cast(guide):
    block = guide.style_block()
    for name in guide.cast:
        assert name.title() + ":" not in block


def test_unknown_character_is_rejected(guide):
    with pytest.raises(StyleError):
        guide.with_character("nobody")


def test_character_survives_variant_and_type(guide):
    g = guide.with_character("bolt").with_variant("night").with_type("object")
    assert g.character == "bolt"
    assert "delivery robot" in g.style_block()


def test_character_reaches_the_sidecar(guide, library):
    bundle = assemble("Bolt beside a crate", guide.with_character("bolt"), library)
    assert bundle.to_meta()["character"] == "bolt"


def test_cast_entry_without_appearance_fails_lint(guide):
    broken = json.loads(json.dumps(guide.data))
    broken["cast"]["nora"].pop("appearance")
    assert any("no appearance" in p for p in StyleGuide(path=guide.path, data=broken).validate())


def test_cast_missing_from_style_block_order_fails_lint(guide):
    broken = json.loads(json.dumps(guide.data))
    broken["prompt"]["style_block_order"] = [s for s in broken["prompt"]["style_block_order"] if s != "cast"]
    assert any("style_block_order" in p for p in StyleGuide(path=guide.path, data=broken).validate())


def test_every_cast_member_renders_and_validates(guide):
    for name in guide.cast:
        g = guide.with_character(name)
        assert g.validate() == []
        assert name.title() + ":" in g.style_block()
