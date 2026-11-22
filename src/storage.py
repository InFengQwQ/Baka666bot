import os
import re
from pathlib import Path


def data_root() -> Path:
    configured = os.environ.get("BAKA_DATA_DIR")
    if configured:
        root = Path(configured).expanduser()
    else:
        root = Path(__file__).resolve().parents[1] / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def plugin_data(plugin_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", plugin_id):
        raise ValueError("invalid plugin id")
    path = data_root() / plugin_id
    path.mkdir(parents=True, exist_ok=True)
    return path
