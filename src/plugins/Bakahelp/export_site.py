"""Copy the self-contained Bakahelp build into a MalodySite source checkout."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PLUGIN_DIR = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, default=PLUGIN_DIR / "dist")
    args = parser.parse_args()

    site_root = args.site_root.resolve()
    build_dir = args.build_dir.resolve()
    destination = site_root / "public" / "bakahelp"
    if not (site_root / ".git").exists():
        raise SystemExit(f"Not a Git checkout: {site_root}")
    if not (destination / "assets" / "favicon.svg").is_file():
        raise SystemExit(f"Bakahelp route assets are missing: {destination}")

    sources = [build_dir / "catalog.json"]
    missing = [path for path in sources if not path.is_file()]
    if missing:
        raise SystemExit("Build output is incomplete: " + ", ".join(map(str, missing)))

    if str(PLUGIN_DIR) not in sys.path:
        sys.path.insert(0, str(PLUGIN_DIR))
    from catalog import export_site

    catalog = json.loads(sources[0].read_text(encoding="utf-8"))
    export_site(destination, catalog, standalone=False, documented=True)

    logo = PLUGIN_DIR / "assets" / "baka.webp"
    if not logo.is_file():
        logo = PLUGIN_DIR / "assets" / "baka.png"
    for source in (logo, PLUGIN_DIR / "assets" / "favicon.png"):
        if not source.is_file():
            continue
        target = destination / "assets" / source.name
        target.write_bytes(source.read_bytes())
    print(f"Exported the standalone page and catalogue to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
