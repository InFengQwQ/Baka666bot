import os
import shutil
from pathlib import Path


class MissingBusinessAccount(ValueError):
    pass


class MissingToolError(RuntimeError):
    """系统依赖缺失。"""


def require_executable(name: str, hint: str) -> str:
    path = shutil.which(name)
    if not path:
        raise MissingToolError(f"未找到 {name}，{hint}")
    return path


def current_qq_user():
    from nonebot.matcher import current_event

    try:
        return current_event.get().get_user_id()
    except (LookupError, ValueError):
        return None


def credential(env: str, config_name: str | None = None) -> str:
    if env in os.environ:
        return os.environ[env].strip()
    try:
        import nonebot

        value = getattr(nonebot.get_driver().config, config_name or env.lower(), "")
        return str(value).strip() if value is not None else ""
    except ValueError:
        return ""


def plugin_resource_dir(module_name: str) -> Path:
    from importlib.util import find_spec

    try:
        spec = find_spec(module_name)
    except (ModuleNotFoundError, ValueError):
        spec = None
    if spec and spec.origin:
        path = Path(spec.origin)
        return path.parent / module_name.split(".")[-1] if path.suffix.lower() == ".pyd" else path.parent
    configured = os.environ.get("BAKA_TOOLS_DIR")
    root = Path(configured) if configured else Path(__file__).resolve().parents[1] / "data" / "tools"
    return root / "fonts"


def import_plugin_module(plugin_id: str, submodule: str = ""):
    from importlib import import_module
    from nonebot import require

    plugin = require(plugin_id)
    return import_module(plugin.__name__ + ("." + submodule if submodule else ""))


def tool_path(name: str) -> Path:
    if Path(name).name != name:
        raise ValueError("invalid tool name")
    configured = os.environ.get("BAKA_TOOLS_DIR")
    root = (
        Path(configured)
        if configured
        else Path(__file__).resolve().parent / "plugins" / "Malody_toolkit" / "tools"
    )
    return root / name


async def malody_store_account(qq: str | None = None):
    from nonebot import require

    plugin = require("MalodyVClientPlugin")
    database = plugin.MalodyAPI.database.db
    if not database.conn:
        return None
    qq = qq if qq is not None else current_qq_user()
    if qq is None:
        return None
    uid = await database.get_uid_by_qq(str(qq))
    if not uid:
        return None
    user = await database.get_user(uid)
    if user and user.get("store_token"):
        return str(uid), user["store_token"]
    return None


async def required_malody_account():
    account = await malody_download_account()
    if not account:
        raise MissingBusinessAccount(MALODY_DOWNLOAD_HINT)
    return account


MALODY_DOWNLOAD_HINT = "请先登录并绑定 Malody 账号，或在 config/malody.env 配置下载账号。"


async def malody_download_account(qq: str | None = None):
    uid = credential("MALODY_DOWNLOAD_UID")
    token = credential("MALODY_DOWNLOAD_TOKEN")
    if uid and uid.isascii() and uid.isdigit() and token:
        return uid, token
    return await malody_store_account(qq)


async def malody_web_cookies():
    raw = credential("MALODY_WEB_COOKIES")
    if raw:
        return parse_malody_cookies(raw)
    from nonebot import require

    plugin = require("MalodyVClientPlugin")
    database = plugin.MalodyAPI.database.db
    qq = current_qq_user()
    uid = await database.get_uid_by_qq(str(qq)) if qq is not None and database.conn else None
    user = await database.get_user(uid) if uid else None
    raw = user.get("web_cookies") if user else None
    return parse_malody_cookies(raw) if raw else {}


def parse_malody_cookies(raw: str) -> dict[str, str]:
    import json

    try:
        value = json.loads(raw)
        if isinstance(value, dict):
            return {str(key): str(item) for key, item in value.items()}
    except (TypeError, ValueError):
        pass
    return dict(pair.strip().split("=", 1) for pair in str(raw).split(";") if "=" in pair)
