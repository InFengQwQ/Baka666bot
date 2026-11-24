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
import re
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).parent
LABELS = {"command": "命令", "shell": "Shell 命令", "fullmatch": "完整匹配",
          "startswith": "前缀匹配", "endswith": "后缀匹配", "keyword": "关键词",
          "regex": "文字格式", "alconna": "Alconna", "shortcut": "自然语言说法",
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


def _meme_arguments(params: Any) -> str:
    arguments: list[str] = []
    min_images = int(getattr(params, "min_images", 0) or 0)
    max_images = int(getattr(params, "max_images", 0) or 0)
    min_texts = int(getattr(params, "min_texts", 0) or 0)
    max_texts = int(getattr(params, "max_texts", 0) or 0)

    if min_images:
        arguments.append("<图片或@用户>")
    elif max_images:
        arguments.append("[图片或@用户]")
    if min_texts:
        arguments.append("<文字>")
    elif max_texts:
        arguments.append("[文字]")

    for option in getattr(params, "options", ()):
        parser_flags = getattr(option, "parser_flags", None)
        aliases = list(getattr(parser_flags, "long_aliases", ()) or ())
        aliases += list(getattr(parser_flags, "short_aliases", ()) or ())
        flag = "--" + aliases[0] if aliases else "--" + str(option.name)
        description = str(getattr(option, "description", "") or option.name)
        if type(option).__name__ == "BooleanOption":
            arguments.append(f"[{flag}]")
        else:
            arguments.append(f"[{flag} <{description}>]")

    return " ".join(arguments) if arguments else "无"


def _meme_documentation(starts: list[str]) -> dict[str, dict[str, str]]:
    """Translate the meme plugin's registered keywords and regex shortcuts."""
    try:
        from meme_generator import get_memes
        from nonebot_plugin_memes.config import memes_config
    except ImportError:
        return {}

    configured_prefixes = memes_config.memes_command_prefixes
    prefixes = starts if configured_prefixes is None else configured_prefixes
    documentation: dict[str, dict[str, str]] = {}
    for meme in get_memes():
        keywords = [str(keyword) for keyword in meme.info.keywords if keyword]
        keyword = keywords[0] if keywords else str(meme.key)
        arguments = _meme_arguments(meme.info.params)
        description = f"制作“{keyword}”表情包，并按参数提供文字、图片或@用户素材。"

        for trigger in keywords:
            for prefix in prefixes:
                documentation[f"{prefix}{trigger}"] = {
                    "trigger_label": f"{prefix}{trigger}",
                    "arguments": arguments,
                    "description": description,
                }

        for shortcut in meme.info.shortcuts:
            label = str(shortcut.humanized or keyword)
            label = label.replace("xx", "某内容")
            shortcut_description = f"按“{label}”这一文字格式制作“{keyword}”表情包。"
            for prefix in prefixes:
                documentation[f"{prefix}re:{shortcut.pattern}"] = {
                    "trigger_label": f"{prefix}{label}",
                    "arguments": arguments,
                    "description": shortcut_description,
                }
    return documentation


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

    # MalodyVClientPlugin exposes its `ma` subcommands through one dispatcher,
    # so they are real user-facing entry points without individual Matchers.
    registered = {e["plugin"] for e in entries}
    ma_module = sys.modules.get("src.plugins.MalodyVClientPlugin.matcher.ma") if "MalodyVClientPlugin" in registered else None
    subcommands = getattr(ma_module, "_SUBCOMMANDS", {})
    ma_prefixes = ("ma", "MA", "Ma", "malody")
    for subcommand, matcher in sorted(subcommands.items()):
        values = sorted({
            f"{start}{prefix} {subcommand}"
            for start, prefix in product(starts, ma_prefixes)
        })
        ma_handler = getattr(matcher, "handle", None)
        handler_names = [name_of(ma_handler)] if callable(ma_handler) else [subcommand]
        identity = json.dumps(
            ["MalodyVClientPlugin", "ma", subcommand, handler_names],
            ensure_ascii=False,
            sort_keys=True,
        )
        entry_id = "MalodyVClientPlugin:ma-" + sha256(identity.encode()).hexdigest()[:12]
        entries.append({
            "id": entry_id,
            "plugin": "MalodyVClientPlugin",
            "module": "src.plugins.MalodyVClientPlugin.matcher.ma",
            "handlers": handler_names,
            "triggers": [{"kind": "command", "values": values}],
            "conditions": [],
            "permissions": [],
            "event": "message",
            "priority": 5,
            "restricted": False,
            "dispatcher": "ma",
        })

    # OMTK's command reference is a dispatcher. Its registered command types
    # are enumerated by the same help data that /omtk displays at runtime.
    omtk_module = sys.modules.get("src.plugins.nonebot_plugin_osumania_toolkit.data.help") if "nonebot_plugin_osumania_toolkit" in registered else None
    omtk_help_data = getattr(omtk_module, "omtk_help_data", None)
    omtk_aliases = getattr(omtk_help_data, "command_aliases", {})
    omtk_types = {row[0]: row[1] for row in getattr(omtk_help_data, "help_text", [])}
    for command_type, topic in sorted(omtk_types.items()):
        aliases = [alias for alias, target in omtk_aliases.items() if target == command_type]
        names = [command_type, *aliases]
        values = sorted({
            f"{start}omtk {name}"
            for start in starts
            for name in names
        })
        identity = json.dumps(
            ["nonebot_plugin_osumania_toolkit", "omtk", command_type],
            ensure_ascii=False,
        )
        entry_id = "nonebot_plugin_osumania_toolkit:omtk-" + sha256(identity.encode()).hexdigest()[:12]
        entries.append({
            "id": entry_id,
            "plugin": "nonebot_plugin_osumania_toolkit",
            "module": "src.plugins.nonebot_plugin_osumania_toolkit.matcher.omtk",
            "handlers": ["handle_omtk"],
            "triggers": [{"kind": "command", "values": values}],
            "conditions": [],
            "permissions": [],
            "event": "message",
            "priority": 5,
            "restricted": False,
            "dispatcher": "omtk",
            "help_topic": topic,
        })
    entries = list({entry["id"]: entry for entry in entries}.values())
    entries.sort(key=lambda e: (e["plugin"].casefold(), e["id"]))
    return {"schema": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
            "command_start": starts, "command_sep": seps, "plugins": plugins,
            "entries": entries, "errors": errors, "labels": LABELS}


def apply_manual(catalog: dict, manual: dict) -> dict:
    """Precedence: plugin defaults < matching trigger docs < exact entry id."""
    plugin_docs = manual.get("plugins", {})
    meme_docs = _meme_documentation(catalog["command_start"])
    command_docs = manual.get("commands", {})
    handler_docs = manual.get("handlers", {})
    for plugin in catalog["plugins"]:
        plugin.update({k: v for k, v in plugin_docs.get(plugin["id"], {}).items()
                       if k in {"name", "description", "usage", "category"}})
    visible = []
    for entry in catalog["entries"]:
        doc = dict(plugin_docs.get(entry["plugin"], {}).get("defaults", {}))
        values = {v for trigger in entry["triggers"] for v in trigger["values"]}
        if entry["plugin"] == "nonebot_plugin_memes":
            matching = [meme_docs[value] for value in sorted(values) if value in meme_docs]
            if matching:
                doc.update(matching[0])
                doc["meme_template"] = True
        if entry.get("dispatcher") == "omtk":
            if entry["help_topic"] == "星数重算":
                doc.update(
                    title="查看旧星数重算入口说明",
                    arguments="无",
                    description="该入口已转由 /mapview 提供键型分析和难度估计。",
                )
            else:
                doc.update(title=entry["help_topic"], arguments="[页码]",
                           description=f"查看「{entry['help_topic']}」的工具箱帮助，可指定页码。")
        plugin_handler_docs = handler_docs.get(entry["plugin"], {})
        matching_handlers = [plugin_handler_docs[handler] for handler in entry.get("handlers", [])
                             if handler in plugin_handler_docs]
        if matching_handlers:
            doc.update(matching_handlers[0])
        for command, command_doc in command_docs.items():
            if command in values:
                doc.update(command_doc)
        for override in manual.get("triggers", []):
            if override.get("plugin", entry["plugin"]) == entry["plugin"] and values.intersection(override.get("match", [])):
                doc.update({k: v for k, v in override.items() if k not in {"plugin", "match"}})
        doc.update(manual.get("entries", {}).get(entry["id"], {}))
        if doc.get("hidden"):
            continue
        entry["doc"] = doc
        doc.setdefault("arguments", _entry_arguments(entry))
        for trigger in entry["triggers"]:
            values = trigger.get("values", [])
            contains_pattern = trigger.get("kind") == "regex" or any(
                re.search(r"(?:^|/)re:", value) for value in values
            )
            if contains_pattern:
                trigger["values"] = []
                trigger.pop("syntax", None)
        visible.append(entry)
    catalog["entries"] = visible
    return catalog


def _trigger_label(entry: dict) -> str:
    doc = entry.get("doc", {})
    if doc.get("trigger_label"):
        return str(doc["trigger_label"])

    triggers = entry.get("triggers", [])
    values = [value for trigger in triggers if trigger["kind"] not in {"regex", "shortcut"}
              for value in trigger.get("values", []) if not re.match(r"^/?re:", value)]
    if values:
        return "、".join(sorted(values, key=lambda s: (len(s), s != s.lower(), s)))

    kind = triggers[0].get("kind", "custom") if triggers else "custom"
    return {
        "message": "符合消息条件时触发",
        "regex": "消息符合指定文字格式时触发",
        "notice": "收到相应通知时触发",
        "request": "收到相应请求时触发",
        "meta_event": "连接状态事件触发",
        "custom": "满足插件自定义条件时触发",
    }.get(kind, "由事件或上下文触发")


def _alconna_arguments(syntax: str) -> str:
    lines = syntax.splitlines()
    if not lines:
        return "参数格式待补充"

    arguments: list[str] = []
    first_line = re.sub(r"^\[[^]]*\]", "", lines[0])
    command = first_line.split(maxsplit=1)
    if len(command) > 1:
        positional = re.findall(r"<([^>]+)>", command[1])
        for item in positional:
            name = item.split(":", 1)[0].strip()
            if name in {"meme_params", "text", "texts", "args"}:
                label = "文字、图片或@用户"
            elif name in {"id", "cid", "sid", "uid"}:
                label = name.upper()
            else:
                label = name or "参数"
            arguments.append(f"<{label}>")

    pending_description = ""
    for line in lines[1:]:
        stripped = line.strip()
        if stripped.startswith("*"):
            pending_description = stripped[1:].strip()
            continue
        option = re.match(r"(?:[-\w│|]+)\s*(?:<([^>]+)>)?\s*$", stripped)
        if not option or not stripped.startswith("-"):
            continue
        aliases = stripped.split()[0].split("│")
        flag = next((alias for alias in aliases if alias.startswith("--")), aliases[0])
        value = option.group(1)
        if value:
            label = pending_description or value.split(":", 1)[0].strip()
            arguments.append(f"[{flag} <{label}>]")
        else:
            arguments.append(f"[{flag}]")
        pending_description = ""

    return " ".join(arguments) if arguments else "无"


def _entry_arguments(entry: dict) -> str:
    doc = entry.get("doc", {})
    if doc.get("arguments"):
        return str(doc["arguments"])
    if doc.get("usage"):
        usage = str(doc["usage"]).strip()
        remainder = usage.split(maxsplit=1)
        return remainder[1] if len(remainder) > 1 else "无"

    for trigger in entry.get("triggers", []):
        if trigger.get("syntax"):
            return _alconna_arguments(str(trigger["syntax"]))
        if trigger.get("kind") == "shell" and trigger.get("syntax"):
            return str(trigger["syntax"])
    if any(trigger.get("kind") in {"message", "notice", "request", "meta_event"}
           for trigger in entry.get("triggers", [])):
        return "无（由消息或事件触发）"
    if any(trigger.get("kind") in {"fullmatch", "startswith", "endswith", "keyword"}
           for trigger in entry.get("triggers", [])):
        return "无"
    return "按功能提示提供所需内容"


def _markdown_cell(value: str, *, code: bool = False) -> str:
    cleaned = str(value).replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")
    if code:
        return "`" + cleaned.replace("`", "'") + "`"
    return cleaned


def render_commands_markdown(catalog: dict) -> str:
    """Render a compact three-column command reference grouped by category."""
    plugins = {plugin["id"]: plugin for plugin in catalog.get("plugins", [])}
    entries = catalog.get("entries", [])
    memes = [entry for entry in entries if entry["doc"].get("meme_template")]
    category_order = ("Malody", "osu!", "创作与娱乐", "管理", "通用")
    tick = chr(96)

    def category(entry: dict) -> str:
        return str(plugins.get(entry["plugin"], {}).get("category") or "通用")

    def sort_key(entry: dict) -> str:
        return _trigger_label(entry).casefold()

    rows = [
        "# Baka666Bot 指令目录",
        "",
        f"根据当前运行配置收录 {len(entries)} 个触发条目。{tick}<参数>{tick} 表示必填，{tick}[参数]{tick} 表示可选。",
        f"表情包指令已折叠，展开后可以查到每个触发词、参数和对应效果。",
        "",
    ]

    for category_name in category_order:
        category_entries = [
            entry for entry in entries
            if category(entry) == category_name and not entry["doc"].get("meme_template")
        ]
        category_memes = [entry for entry in memes if category(entry) == category_name]
        if not category_entries and not category_memes:
            continue

        rows.extend((
            f"## {category_name}",
            "",
            "| 触发名或触发语义 | 参数 | 功能说明 |",
            "| --- | --- | --- |",
        ))
        for entry in sorted(category_entries, key=sort_key):
            doc = entry.get("doc", {})
            plugin = plugins.get(entry["plugin"], {})
            description = doc.get("description") or plugin.get("description") or "按功能提示提供内容。"
            rows.append(
                "| " + " | ".join((
                    _markdown_cell(_trigger_label(entry), code=True),
                    _markdown_cell(_entry_arguments(entry), code=True),
                    _markdown_cell(description),
                )) + " |"
            )

        if category_memes:
            rows.append(
                "| 表情包关键词与文字格式（展开下方列表） | 见展开列表 | "
                f"表情包模板，共 {len(category_memes)} 个触发项。 |"
            )
            rows.extend((
                "",
                f"<details><summary>展开 {len(category_memes)} 个表情包触发项</summary>",
                "",
                "| 触发名或触发语义 | 参数 | 功能说明 |",
                "| --- | --- | --- |",
            ))
            for entry in sorted(category_memes, key=sort_key):
                doc = entry.get("doc", {})
                rows.append(
                    "| " + " | ".join((
                        _markdown_cell(_trigger_label(entry), code=True),
                        _markdown_cell(_entry_arguments(entry), code=True),
                        _markdown_cell(doc.get("description") or "制作对应模板的表情包。"),
                    )) + " |"
                )
            rows.extend(("", "</details>"))
        rows.append("")

    return "\n".join(rows)


def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.read_text(encoding="utf-8") == content:
            return
    except FileNotFoundError:
        pass
    fd, temporary = tempfile.mkstemp(prefix=".bakahelp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def export_site(
    destination: Path,
    catalog: dict | None = None,
    markdown_path: Path | None = None,
    *,
    standalone: bool = True,
    documented: bool = False,
) -> dict:
    raw = catalog if catalog is not None else collect_catalog()
    if not documented:
        manual = json.loads((ROOT / "manual.json").read_text(encoding="utf-8"))
        raw = apply_manual(raw, manual)
    catalog = raw
    data = json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
    # Single HTML works under file:// and /bakahelp with or without trailing slash.
    embedded = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = (ROOT / "web/index.html").read_text(encoding="utf-8")
    if (ROOT / "assets" / "baka.webp").is_file():
        brand_image = "data:image/webp;base64," + base64.b64encode((ROOT / "assets/baka.webp").read_bytes()).decode("ascii")
    else:
        brand_image = "data:image/png;base64," + base64.b64encode((ROOT / "assets/baka.png").read_bytes()).decode("ascii")
    if not standalone:
        brand_image = "./assets/baka.webp" if (ROOT / "assets" / "baka.webp").is_file() else "./assets/baka.png"
        favicon_url = "./assets/favicon.png"
    else:
        favicon_url = "data:image/png;base64," + base64.b64encode(
            (ROOT / "assets" / "favicon.png").read_bytes()
        ).decode("ascii")
    page = page.replace("BAKAHELP_BRAND_IMAGE", brand_image)
    page = page.replace("BAKAHELP_FAVICON", favicon_url)
    page = page.replace("/* BAKAHELP_STYLE */", (ROOT / "web/style.css").read_text(encoding="utf-8"))
    if standalone:
        for name in ("display-cn", "display-latin"):
            page = page.replace("BAKAHELP_FONT_" + name, base64.b64encode((ROOT / "assets" / (name + ".ttf")).read_bytes()).decode("ascii"))
    page = page.replace("/* BAKAHELP_SCRIPT */", (ROOT / "web/app.js").read_text(encoding="utf-8"))
    page = page.replace("BAKAHELP_DATA_PLACEHOLDER", embedded)
    atomic_write(destination / "catalog.json", json.dumps(catalog, ensure_ascii=False, indent=2))
    atomic_write(destination / "index.html", page)
    if markdown_path is not None:
        atomic_write(markdown_path, render_commands_markdown(catalog))
    return {"entry_count": len(catalog["entries"]), "plugin_count": len(catalog["plugins"]),
            "errors": catalog["errors"]}
