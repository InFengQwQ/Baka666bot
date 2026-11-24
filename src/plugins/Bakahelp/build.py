"""Build the searchable Bakahelp page and the standalone command directory."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PLUGIN_DIR = Path(__file__).resolve().parent
DEFAULT_BOT_ROOT = PLUGIN_DIR.parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bot-root", type=Path, default=DEFAULT_BOT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=PLUGIN_DIR / "dist")
    parser.add_argument("--markdown-path", type=Path, default=None)
    args = parser.parse_args()

    bot_root = args.bot_root.resolve()
    sys.path.insert(0, str(bot_root))
    import bot  # noqa: F401  Loads exactly the configured plugins and rules.

    from src.plugins.Bakahelp.catalog import export_site
    markdown_path = (args.markdown_path or bot_root / "COMMANDS.md").resolve()
    site_report = export_site(args.output_dir.resolve(), markdown_path=markdown_path)
    print(
        f"Exported {site_report['entry_count']} trigger entries from "
        f"{site_report['plugin_count']} loaded plugins."
    )
    print(f"HTML: {args.output_dir.resolve() / 'index.html'}")
    print(f"Markdown: {markdown_path}")
    if site_report["errors"]:
        print(f"Rule metadata warnings: {len(site_report['errors'])}")
        for item in site_report["errors"]:
            print(f"  {item['plugin']}: {item['rule']} ({item['error']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
