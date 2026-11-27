#!/usr/bin/env python3
"""Install the runtime tools pinned in assets-manifest.json.

Both platforms take the renderer and the conversion tools; the avatar card's
model weights are platform independent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).with_name("assets-manifest.json")
DEST = ROOT / "src" / "plugins" / "Malody_toolkit" / "tools"
DEFAULT_DEST = "src/plugins/Malody_toolkit/tools"


def default_platform() -> str:
    return "windows" if platform.system().lower().startswith("win") else "linux"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def is_current(path: Path, entry: dict) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == entry["size"]
        and digest(path) == entry["sha256"]
    )


def download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "baka666bot-assets/1"})
    temporary = target.with_name(target.name + ".part")
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    temporary.replace(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("windows", "linux"), default=default_platform())
    parser.add_argument("--dest", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    names = manifest["platforms"][args.platform] + manifest.get("always", [])
    sources = manifest["sources"]

    failed = False
    for name in names:
        entry = manifest["files"][name]
        target = args.dest / name if args.dest else ROOT / entry.get("dest", DEFAULT_DEST) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not args.force and is_current(target, entry):
            print(f"[assets] {name}: ok")
            continue
        print(f"[assets] {name}: downloading")
        try:
            download(f"{sources[entry['source']].rstrip('/')}/{name}", target)
        except Exception as exc:
            print(f"[assets] {name}: download failed: {exc}", file=sys.stderr)
            failed = True
            continue
        if not is_current(target, entry):
            print(f"[assets] {name}: checksum mismatch", file=sys.stderr)
            target.unlink(missing_ok=True)
            failed = True
            continue
        print(f"[assets] {name}: installed")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
