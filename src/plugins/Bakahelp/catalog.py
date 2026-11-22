"""Inspect registered matchers, never execute their rules or handlers.

Only explicit documentation and rule fields are serialized. Bot config,
checker reprs, closure values and permission arguments must never be exported.
"""
from __future__ import annotations

from datetime import datetime, timezone
import base64
from hashlib import sha256
from itertools import product
import json
import os
from pathlib import Path
import tempfile
from typing import Any

ROOT = Path(__file__).parent
LABELS = {"command": "命令", "shell": "Shell 命令", "fullmatch": "完整匹配",
          "startswith": "前缀匹配", "endswith": "后缀匹配", "keyword": "关键词",
          "regex": "正则匹配", "alconna": "Alconna", "shortcut": "快捷规则",
          "message": "消息事件", "notice": "通知事件", "request": "请求事件",
          "meta_event": "元事件", "custom": "自定义规则"}


def name_of(call: Any) -> str:
    return getattr(call, "__name__", type(call).__name__)


def rules_of(rule: Any) -> list[Any]:
    return [checker.call for checker in getattr(rule, "checkers", ())]


def describe_rule(call: Any, starts: list[str], seps: list[str]) -> list[dict]:
    kind = type(call).__name__
    if kind in {"CommandRule", "ShellCommandRule"}:
        values = sorted({prefix + sep.join(parts) for parts in call.cmds
                         for prefix, sep in product(starts, seps)})
        result = {"kind": "shell" if kind == "ShellCommandRule" else "command", "values": values}
        if kind == "ShellCommandRule" and call.parser:
            result["syntax"] = call.parser.format_usage().strip()
        if kind == "CommandRule" and call.force_whitespace is not None:
            result["whitespace"] = call.force_whitespace
        return [result]
    fields = {"StartswithRule": ("startswith", "msg"), "EndswithRule": ("endswith", "msg"),
              "FullmatchRule": ("fullmatch", "msg"), "KeywordsRule": ("keyword", "keywords")}
    if kind in fields:
        label, field = fields[kind]
        return [{"kind": label, "values": sorted(getattr(call, field)),
                 "ignorecase": getattr(call, "ignorecase", False)}]
    if kind == "RegexRule":
        regex = call.regex
        return [{"kind": "regex", "values": [getattr(regex, "pattern", regex)],
                 "flags": int(call.flags)}]
    if kind == "AlconnaRule":
        command = call.command()
        if command is None:
            return []
        prefixes = [p for p in command.prefixes if isinstance(p, str)] or [""]
        result = [{"kind": "alconna", "values": [p + str(command.command) for p in prefixes],
                   "syntax": command.get_help()}]
        shortcuts = command.get_shortcuts()
        if shortcuts:
            result.append({"kind": "shortcut", "values": sorted(shortcuts)})
        return result
    return []


def collect_catalog() -> dict:
    from nonebot import get_driver, get_loaded_plugins
    from nonebot.matcher import matchers

    config = get_driver().config
    starts, seps = sorted(config.command_start), sorted(config.command_sep)
    loaded = sorted(get_loaded_plugins(), key=lambda p: p.name)
    plugins = []
    for plugin in loaded:
        meta = plugin.metadata
        plugins.append({"id": plugin.name, "name": meta.name if meta else plugin.name,
                        "description": meta.description if meta else "",
                        "usage": meta.usage if meta else ""})
    entries, errors = [], []
    for priority in sorted(matchers):
        for matcher in list(matchers[priority]):
            if matcher.temp:
                continue  # Conversation continuations are not public entry points.
            plugin = matcher.plugin_name or "unowned"
            module = matcher.module_name or plugin
            handler_names = sorted({name_of(h.call) for h in matcher.handlers})
            triggers, conditions = [], []
            for call in rules_of(matcher.rule):
                try:
                    found = describe_rule(call, starts, seps)
                    if found:
                        triggers.extend(found)
                    else:
                        conditions.append(name_of(call))
                    if type(call).__name__ == "AlconnaRule":
                        for extra in (call.before_rules, call.after_rules):
                            conditions.extend(name_of(c) for c in rules_of(extra))
                except Exception as exc:
                    conditions.append(name_of(call))
                    errors.append({"plugin": plugin, "rule": name_of(call), "error": type(exc).__name__})
            if not triggers:
                triggers = [{"kind": matcher.type if matcher.type in LABELS else "custom", "values": []}]
            triggers.sort(key=lambda t: (t["kind"], json.dumps(t["values"], ensure_ascii=False)))
            permissions = sorted(name_of(c) for c in rules_of(matcher.permission))
            # Identity excludes line numbers and discovery order so manual docs survive edits.
            identity = json.dumps([plugin, module, handler_names,
                                   [{"kind": t["kind"], "values": t["values"]} for t in triggers]],
                                  ensure_ascii=False, sort_keys=True)
            entry_id = plugin + ":" + sha256(identity.encode()).hexdigest()[:12]
            entries.append({"id": entry_id, "plugin": plugin, "module": module,
                            "handlers": handler_names, "triggers": triggers,
                            "conditions": sorted(set(conditions)), "permissions": permissions,
                            "event": matcher.type or "any", "priority": priority,
                            "restricted": any("SUPERUSER" in p.upper() or "ADMIN" in p.upper() or
                                              "OWNER" in p.upper() for p in permissions)})
    entries = list({entry["id"]: entry for entry in entries}.values())
    entries.sort(key=lambda e: (e["plugin"].casefold(), e["id"]))
    return {"schema": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
            "command_start": starts, "command_sep": seps, "plugins": plugins,
            "entries": entries, "errors": errors, "labels": LABELS}


def apply_manual(catalog: dict, manual: dict) -> dict:
    """Precedence: plugin defaults < matching trigger docs < exact entry id."""
    plugin_docs = manual.get("plugins", {})
    for plugin in catalog["plugins"]:
        plugin.update({k: v for k, v in plugin_docs.get(plugin["id"], {}).items()
                       if k in {"name", "description", "usage", "category"}})
    visible = []
    for entry in catalog["entries"]:
        doc = dict(plugin_docs.get(entry["plugin"], {}).get("defaults", {}))
        values = {v for trigger in entry["triggers"] for v in trigger["values"]}
        for override in manual.get("triggers", []):
            if override.get("plugin", entry["plugin"]) == entry["plugin"] and values.intersection(override.get("match", [])):
                doc.update({k: v for k, v in override.items() if k not in {"plugin", "match"}})
        doc.update(manual.get("entries", {}).get(entry["id"], {}))
        if doc.get("hidden"):
            continue
        entry["doc"] = doc
        visible.append(entry)
    catalog["entries"] = visible
    return catalog


def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".bakahelp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def export_site(destination: Path, catalog: dict | None = None) -> dict:
    raw = catalog if catalog is not None else collect_catalog()
    manual = json.loads((ROOT / "manual.json").read_text(encoding="utf-8"))
    catalog = apply_manual(raw, manual)
    data = json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
    # Single HTML works under file:// and /bakahelp with or without trailing slash.
    embedded = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = (ROOT / "web/index.html").read_text(encoding="utf-8")
    page = page.replace("BAKAHELP_BRAND_IMAGE", "data:image/png;base64," + base64.b64encode((ROOT / "assets/baka.png").read_bytes()).decode("ascii"))
    page = page.replace("/* BAKAHELP_STYLE */", (ROOT / "web/style.css").read_text(encoding="utf-8"))
    for name in ("display-cn", "display-latin"):
        page = page.replace("BAKAHELP_FONT_" + name, base64.b64encode((ROOT / "assets" / (name + ".ttf")).read_bytes()).decode("ascii"))
    page = page.replace("/* BAKAHELP_SCRIPT */", (ROOT / "web/app.js").read_text(encoding="utf-8"))
    page = page.replace("BAKAHELP_DATA_PLACEHOLDER", embedded)
    atomic_write(destination / "catalog.json", json.dumps(catalog, ensure_ascii=False, indent=2))
    atomic_write(destination / "index.html", page)
    return {"entry_count": len(catalog["entries"]), "plugin_count": len(catalog["plugins"]),
            "errors": catalog["errors"]}
