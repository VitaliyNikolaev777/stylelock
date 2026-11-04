import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stylelock.cli import main  # noqa: E402
from stylelock.providers.dryrun import _solid_png  # noqa: E402

# Everything the starter guide lacks, so overlays and cast can be exercised.
RICH = {
    "characters": {
        "humans": "simple rounded proportions, dot eyes",
        "animals": "friendly and simplified",
    },
    "variants": {
        "forest": {
            "description": "Woodland world.",
            "reference_tags": ["forest"],
            "palette": {"colors": [
                {"name": "moss", "hex": "#2E8B57"}, {"name": "bark", "hex": "#7A5230"},
                {"name": "fern", "hex": "#9BD770"},
            ]},
            "append": "Tall tree trunks frame the left and right edges.",
        },
        "night": {
            "description": "The same world after dark.",
            "reference_tags": ["night"],
            "palette": {"colors": [
                {"name": "midnight", "hex": "#1B1F3B"}, {"name": "lamp", "hex": "#FFD27A"},
            ]},
        },
    },
    "types_extra": {
        "emblem": {
            "description": "A round achievement emblem.",
            "palette": {"colors": [
                {"name": "plate navy", "hex": "#2E3A5C"}, {"name": "gold", "hex": "#F2C14E"},
            ]},
            "negative": ["text", "letters"],
        },
        "diagram": {
            "description": "A layout diagram read from a composition reference.",
            "reference_roles": ["composition"],
            "negative": ["text"],
        },
    },
    "cast": {
        "nora": {"description": "the guide", "appearance": "two short braids, yellow raincoat"},
        "theo": {"description": "her friend", "appearance": "green hooded top, round glasses"},
        "bolt": {"description": "the helper", "appearance": "small round delivery robot on one wheel"},
    },
}


_ENV = ("OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "REPLICATE_API_TOKEN",
        "STYLELOCK_PROVIDER", "STYLELOCK_MODEL", "STYLELOCK_COMPAT_BASE_URL",
        "STYLELOCK_COMPAT_API_KEY", "STYLELOCK_MAX_IMAGES", "STYLELOCK_HOME")


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """No test may see the developer's real keys, settings or ~/.config/stylelock/.env."""
    import stylelock.cli as cli
    import stylelock.config as config

    for var in _ENV:
        monkeypatch.delenv(var, raising=False)
    user_env = tmp_path / "user-config" / ".env"
    monkeypatch.setattr(config, "USER_ENV_FILE", user_env)
    monkeypatch.setattr(cli, "USER_ENV_FILE", user_env)
    monkeypatch.chdir(tmp_path)
    return user_env


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A fresh project made by `stylelock init`, with STYLELOCK_HOME pointing at it."""
    root = tmp_path / "proj"
    assert main(["init", str(root)]) == 0
    monkeypatch.setenv("STYLELOCK_HOME", str(root))
    return root


@pytest.fixture
def rich_project(project):
    """The starter guide plus variants, extra types and a cast."""
    path = project / "style" / "style-guide-v1.json"
    data = json.loads(path.read_text())
    data["characters"] = RICH["characters"]
    data["variants"] = RICH["variants"]
    data["types"].update(RICH["types_extra"])
    data["types"]["icon"]["reference_tags"] = ["icon"]
    for t in data["types"].values():
        t.setdefault("negative", data["prompt"]["negative"])
    data["cast"] = RICH["cast"]
    path.write_text(json.dumps(data, indent=2))
    return project


@pytest.fixture
def guide(rich_project):
    from stylelock.style import StyleGuide

    return StyleGuide.load()


@pytest.fixture
def library(rich_project):
    from stylelock.manifest import Library

    refdir = rich_project / "references"
    for name in ("anchors/a1.png", "anchors/a2.png", "texture/t1.png"):
        (refdir / name).write_bytes(_solid_png(8, 8))
    manifest = refdir / "manifest.json"
    manifest.write_text(json.dumps({
        "version": 1,
        "images": [
            {"id": "a1", "file": "anchors/a1.png", "role": "anchor",
             "tags": ["hero"], "demonstrates": "line weight and palette"},
            {"id": "a2", "file": "anchors/a2.png", "role": "anchor",
             "tags": ["spot"], "demonstrates": "negative space"},
            {"id": "t1", "file": "texture/t1.png", "role": "texture",
             "tags": ["grain"], "demonstrates": "paper grain", "exclude": ["background colour"]},
        ],
    }))
    return Library.load(manifest)
