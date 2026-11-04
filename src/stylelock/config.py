"""Where the project lives, and environment loading.

A stylelock *project* is any folder holding `style/` and `references/manifest.json` -
the tool is installed once, and each project carries its own guides, references, outputs
and reject log, the way each git repo carries its own history.

Which project a command acts on:
  1. `STYLELOCK_HOME`, if set;
  2. otherwise the nearest folder at or above the current directory that looks like one.

`stylelock init` creates one.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
HOME_ENV = "STYLELOCK_HOME"
USER_ENV_FILE = Path.home() / ".config" / "stylelock" / ".env"


class ProjectNotFound(Exception):
    pass


def is_project(path: Path) -> bool:
    return (path / "style").is_dir() and (path / "references" / "manifest.json").is_file()


def find_root(start: Path | None = None) -> Path | None:
    """The project root for `start` (default: cwd), or None. `STYLELOCK_HOME` wins."""
    home = os.getenv(HOME_ENV)
    if home:
        root = Path(home).expanduser().resolve()
        return root if is_project(root) else None
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if is_project(candidate):
            return candidate
    return None


@dataclass(frozen=True)
class Project:
    root: Path

    @property
    def style_dir(self) -> Path:
        return self.root / "style"

    @property
    def references_dir(self) -> Path:
        return self.root / "references"

    @property
    def manifest_path(self) -> Path:
        return self.references_dir / "manifest.json"

    @property
    def outputs_dir(self) -> Path:
        return self.root / "outputs"

    @property
    def rejects_dir(self) -> Path:
        return self.root / "rejects"

    @property
    def reject_log(self) -> Path:
        return self.rejects_dir / "log.jsonl"

    def ensure_dirs(self) -> None:
        for d in (self.outputs_dir, self.rejects_dir):
            d.mkdir(parents=True, exist_ok=True)


def project(start: Path | None = None) -> Project:
    root = find_root(start)
    if root is None:
        home = os.getenv(HOME_ENV)
        where = f"{HOME_ENV}={home}" if home else f"{Path.cwd()} or any folder above it"
        raise ProjectNotFound(
            f"no stylelock project at {where} (a project has style/ and "
            "references/manifest.json). Run `stylelock init` to create one, or set "
            f"{HOME_ENV} to an existing project."
        )
    return Project(root)


# -- generation settings -------------------------------------------------
#
# "Which painter" is a setting of whoever runs stylelock (a person, or an orchestrator's
# connector), not of the agent writing briefs. So it lives in the environment:
#   STYLELOCK_PROVIDER  openai | gemini | replicate | openai-compatible | dryrun
#   STYLELOCK_MODEL     model id for that provider
# Precedence everywhere: explicit argument > environment (incl. .env files) > style guide.

PROVIDER_ENV = "STYLELOCK_PROVIDER"
MODEL_ENV = "STYLELOCK_MODEL"
SETTABLE = {  # `stylelock config set <name> <value>` -> env var
    "provider": PROVIDER_ENV,
    "model": MODEL_ENV,
    "base-url": "STYLELOCK_COMPAT_BASE_URL",
    "max-images": "STYLELOCK_MAX_IMAGES",
}


def resolve_generation(provider: str | None = None, options: dict | None = None) -> tuple[str, dict, dict]:
    """(provider, options, sources). `STYLELOCK_MODEL` only applies to the provider it was
    configured for - an explicit `--provider gemini` must not inherit an OpenAI model id."""
    env_provider = os.getenv(PROVIDER_ENV) or None
    name = provider or env_provider or "dryrun"
    opts = dict(options or {})
    sources = {"provider": "argument" if provider else ("env" if env_provider else "default")}
    env_model = os.getenv(MODEL_ENV)
    if "model" in opts:
        sources["model"] = "argument"
    elif env_model and (provider is None or provider == env_provider):
        opts["model"] = env_model
        sources["model"] = "env"
    else:
        sources["model"] = "guide"
    return name, opts, sources


def write_env_value(path: Path, key: str, value: str) -> None:
    """Set KEY=value in a .env file, replacing an existing line. The file is kept 0600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    out, done = [], False
    for line in lines:
        if line.split("=", 1)[0].strip() == key:
            if not done:
                out.append(f"{key}={value}")
                done = True
            continue
        out.append(line)
    if not done:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n")
    path.chmod(0o600)


def env_sources(names: list[str]) -> dict[str, str]:
    """Where each variable's value comes from: 'environment', a file path, or 'unset'.
    Call before load_dotenv() to tell the real environment apart from .env files."""
    root = find_root()
    files = ([root / ".env"] if root else []) + [USER_ENV_FILE]
    out = {}
    for name in names:
        src = "environment" if name in os.environ else "unset"
        if src == "unset":
            for f in files:
                if f.exists() and any(
                    line.split("=", 1)[0].strip() == name and line.split("=", 1)[1].strip()
                    for line in f.read_text().splitlines() if "=" in line
                ):
                    src = str(f)
                    break
        out[name] = src
    return out


def load_dotenv() -> None:
    """Load the project's `.env`, then `~/.config/stylelock/.env`. Values already in the
    environment win, and the project file wins over the user-wide one."""
    root = find_root()
    for path in ([root / ".env"] if root else []) + [USER_ENV_FILE]:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
