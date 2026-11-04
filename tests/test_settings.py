"""Generation settings, key storage, --json output, providers, docs."""

import io
import json
import os
import stat
from pathlib import Path

import pytest

from stylelock.cli import main
from stylelock.config import resolve_generation

ROOT = Path(__file__).resolve().parents[1]


# -- provider / model resolution -----------------------------------------

def test_defaults_to_dryrun_and_the_guide():
    name, opts, src = resolve_generation()
    assert name == "dryrun" and "model" not in opts
    assert src == {"provider": "default", "model": "guide"}


def test_env_sets_provider_and_model(monkeypatch):
    monkeypatch.setenv("STYLELOCK_PROVIDER", "openai")
    monkeypatch.setenv("STYLELOCK_MODEL", "gpt-image-2")
    name, opts, src = resolve_generation()
    assert (name, opts["model"]) == ("openai", "gpt-image-2")
    assert src == {"provider": "env", "model": "env"}


def test_env_model_does_not_leak_to_another_provider(monkeypatch):
    monkeypatch.setenv("STYLELOCK_PROVIDER", "openai")
    monkeypatch.setenv("STYLELOCK_MODEL", "gpt-image-2")
    name, opts, _ = resolve_generation("gemini")
    assert name == "gemini" and "model" not in opts


def test_explicit_model_wins(monkeypatch):
    monkeypatch.setenv("STYLELOCK_MODEL", "from-env")
    _, opts, src = resolve_generation(None, {"model": "from-arg"})
    assert opts["model"] == "from-arg" and src["model"] == "argument"


def test_run_uses_the_configured_provider(project, monkeypatch):
    from stylelock import generate as gen
    from stylelock.providers import ProviderError

    monkeypatch.setenv("STYLELOCK_PROVIDER", "openai")
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        gen.run("a lighthouse", allow_draft=True)


def test_settings_in_the_project_env_file_apply(project):
    from stylelock import service

    (project / ".env").write_text("STYLELOCK_PROVIDER=gemini\nSTYLELOCK_MODEL=gemini-x\n")
    g = service.generation_config()
    assert (g["provider"], g["model"]) == ("gemini", "gemini-x")
    assert g["capabilities"]["supports_transparency"] is False


# -- config command ------------------------------------------------------

def test_config_set_writes_the_user_file(isolated_env, capsys):
    assert main(["config", "set", "provider", "openai"]) == 0
    assert main(["config", "set", "model", "gpt-image-1.5"]) == 0
    assert main(["config", "set", "provider", "replicate"]) == 0   # replaces, not appends
    text = isolated_env.read_text()
    assert text.count("STYLELOCK_PROVIDER=") == 1 and "STYLELOCK_PROVIDER=replicate" in text
    assert "STYLELOCK_MODEL=gpt-image-1.5" in text


def test_config_set_rejects_unknown_provider(capsys):
    assert main(["config", "set", "provider", "midjourney"]) == 2


def test_set_key_reads_stdin_not_argv_and_is_private(isolated_env, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("sk-test-1234567890\n"))
    assert main(["config", "set-key", "openai"]) == 0
    assert "OPENAI_API_KEY=sk-test-1234567890" in isolated_env.read_text()
    assert stat.S_IMODE(isolated_env.stat().st_mode) == 0o600
    assert "sk-test-1234567890" not in capsys.readouterr().out


def test_set_key_into_the_project(project, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("r8-token\n"))
    assert main(["config", "set-key", "replicate", "--project"]) == 0
    assert "REPLICATE_API_TOKEN=r8-token" in (project / ".env").read_text()


def test_config_show_masks_keys_and_names_sources(project, monkeypatch, capsys):
    (project / ".env").write_text("OPENAI_API_KEY=sk-abcdefghijklmnop\n")
    monkeypatch.setenv("STYLELOCK_PROVIDER", "openai")
    assert main(["config", "show", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    key = d["values"]["OPENAI_API_KEY"]
    assert key["source"].endswith(".env") and "abcdefghijkl" not in key["value"]
    assert d["values"]["STYLELOCK_PROVIDER"]["source"] == "environment"
    assert d["generation"]["provider"] == "openai"


# -- --json output -------------------------------------------------------

def _json(capsys, argv):
    main(argv)
    return json.loads(capsys.readouterr().out)


def test_doctor_json(project, capsys):
    d = _json(capsys, ["doctor", "--json"])
    assert d["project"] == str(project)
    assert d["generation"]["provider"] == "dryrun"
    assert any("draft" in s for s in d["next_steps"])


def test_generate_and_review_json(project, capsys):
    out = _json(capsys, ["generate", "a kite", "--allow-draft", "-n", "2", "--json"])
    assert len(out) == 2 and out[0]["status"] == "unreviewed" and out[0]["width"] == 64
    pend = _json(capsys, ["review", "pending", "--json"])
    assert {p["image"] for p in pend} == {o["image"] for o in out}
    rej = _json(capsys, ["review", "reject", out[0]["image"], "--reasons", "artifact", "--json"])
    assert rej["reasons"] == ["artifact"] and Path(rej["moved_to"]).exists()


def test_dry_run_json(project, capsys):
    d = _json(capsys, ["generate", "a kite", "--type", "icon", "--dry-run", "--json"])
    assert d["prompt"].startswith("a kite") and "type=icon" in d["style"]


def test_providers_json_lists_capabilities(capsys):
    rows = {p["name"]: p for p in _json(capsys, ["providers", "--json"])}
    assert {"openai", "openai-compatible", "gemini", "replicate", "dryrun"} <= set(rows)
    assert rows["openai"]["supports_transparency"] and not rows["gemini"]["supports_transparency"]
    assert rows["openai"]["key_set"] is False and rows["dryrun"]["key_env"] is None


# -- openai-compatible ---------------------------------------------------

def test_compatible_provider_needs_base_url_and_model(guide, library):
    from stylelock.prompt import assemble
    from stylelock.providers import ProviderError, get_provider

    bundle = assemble("x", guide, library)
    with pytest.raises(ProviderError, match="base_url"):
        get_provider("openai-compatible", model="m").generate(bundle)
    with pytest.raises(ProviderError, match="model"):
        get_provider("openai-compatible", base_url="http://localhost:1/v1").generate(bundle)


def test_compatible_provider_sends_references_only_when_told():
    from stylelock.providers import get_provider

    assert get_provider("openai-compatible").supports_reference_images is False
    assert get_provider("openai-compatible", edit=True).supports_reference_images is True


# -- docs ----------------------------------------------------------------

def test_skill_reference_docs_match_the_package():
    """The skill folder carries copies of the packaged docs; they must not drift."""
    pkg = ROOT / "src" / "stylelock" / "docs"
    skill = ROOT / "skills" / "stylelock" / "reference"
    names = {p.name for p in skill.glob("*.md")}
    assert names and names <= {p.name for p in pkg.glob("*.md")}
    for name in names:
        assert (skill / name).read_text() == (pkg / name).read_text(), (
            f"{name} drifted - copy src/stylelock/docs/{name} over skills/stylelock/reference/"
        )


def test_instructions_prints_the_agent_doc(capsys):
    assert main(["instructions"]) == 0
    assert "art director" in capsys.readouterr().out
    assert main(["instructions", "briefing"]) == 0


def test_no_key_value_ever_reaches_status(project, monkeypatch):
    from stylelock import service

    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value-123")
    monkeypatch.setenv("STYLELOCK_PROVIDER", "openai")
    assert "sk-secret-value-123" not in json.dumps(service.status())
    assert os.environ["OPENAI_API_KEY"] == "sk-secret-value-123"
