"""Static front assets, prepared once at startup.

Front code may contain scenario blocks:

    //@@<scenario-name>
    ...code...
    //@@end

A block is kept when its scenario is active and removed otherwise. Marker lines
are always removed, so the served code carries no scenario names.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from kvyt_common import REGISTRY, ScenarioSet

STATIC_DIR = Path(__file__).parent / "static"

_BLOCK_START = re.compile(r"^\s*//@@([a-z0-9-]+)\s*$")
_BLOCK_END = re.compile(r"^\s*//@@end\s*$")


@dataclass(frozen=True)
class Asset:
    content: bytes
    media_type: str
    etag: str


def apply_scenario_blocks(source: str, scenarios: ScenarioSet, owner: str) -> str:
    kept: list[str] = []
    current: str | None = None
    for number, line in enumerate(source.splitlines(keepends=True), start=1):
        if (start := _BLOCK_START.match(line)) and start.group(1) != "end":
            name = start.group(1)
            spec = REGISTRY.get(name)
            if current is not None or spec is None or spec.owner != owner:
                raise ValueError(f"line {number}: invalid scenario block '{name}'")
            current = name
        elif _BLOCK_END.match(line):
            if current is None:
                raise ValueError(f"line {number}: block end without start")
            current = None
        elif current is None or scenarios.active(current):
            kept.append(line)
    if current is not None:
        raise ValueError(f"scenario block '{current}' is not closed")
    return "".join(kept)


def load_assets(scenarios: ScenarioSet, owner: str) -> dict[str, Asset]:
    files = {
        "/": ("index.html", "text/html; charset=utf-8"),
        "/static/app.js": ("app.js", "application/javascript; charset=utf-8"),
        "/static/styles.css": ("styles.css", "text/css; charset=utf-8"),
    }
    assets = {}
    for url, (name, media_type) in files.items():
        text = (STATIC_DIR / name).read_text(encoding="utf-8")
        content = apply_scenario_blocks(text, scenarios, owner).encode()
        etag = '"' + hashlib.sha256(content).hexdigest()[:16] + '"'
        assets[url] = Asset(content=content, media_type=media_type, etag=etag)
    return assets
