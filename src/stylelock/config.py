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
