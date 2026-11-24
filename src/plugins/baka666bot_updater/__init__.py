"""Check and apply published Baka666Bot updates before adapters connect."""

from __future__ import annotations

import asyncio
import base64
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import Request, urlopen
import urllib.error
import urllib.request

from PIL import Image

from nonebot import get_driver, logger, on_request
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Bot, GroupRequestEvent
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule


__plugin_meta__ = PluginMetadata(
    name="Baka666Bot 自动更新",
    description="启动时更新 Baka666Bot、同步 QQ 账号资料并检查总群状态。",
    usage="Bot 启动时自动检查更新并同步主账号头像和昵称。",
)

REPOSITORY = "MCPsDE/Baka666bot"
BRANCH = "main"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
UPDATE_MODE_ENV = "BAKA666BOT_UPDATE_MODE"
GITHUB_COMMIT_API = f"https://api.github.com/repos/{REPOSITORY}/commits/{BRANCH}"
MAIN_ACCOUNT_QQ = 1469429
MAIN_GROUP_ID = 451586654
QQ_AVATAR_URL = "https://q1.qlogo.cn/g?b=qq&nk={qq}&s=640"
MAX_AVATAR_BYTES = 5 * 1024 * 1024


def _local_env_value(name: str) -> str:
    """Read one local .env value without importing or exposing other secrets."""
    env_value = os.environ.get(name)
    if env_value is not None:
        return env_value.strip().strip('"').strip("'")

    env_file = PROJECT_ROOT / ".env"
    if not env_file.is_file():
        return ""
    prefix = f"{name}="
    for raw_line in env_file.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw_line.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip().strip('"').strip("'")
    return ""


def _is_development_mode() -> bool:
    return _local_env_value(UPDATE_MODE_ENV).lower() in {
        "dev",
        "development",
    }


def _run_git(*arguments: str, timeout: int = 300) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return result.stdout.strip()


def _latest_remote_commit() -> str:
    request = urllib.request.Request(
        GITHUB_COMMIT_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Baka666Bot-Updater",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    commit = str(payload.get("sha", ""))
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit.lower()):
        raise ValueError("GitHub returned an invalid commit id")
    return commit


def _working_tree_has_changes() -> bool:
    return bool(_run_git("status", "--porcelain", "--untracked-files=all"))


def _restore_previous_commit(previous_commit: str) -> None:
    _run_git("reset", "--hard", previous_commit)
    _run_git("submodule", "update", "--init", "--recursive", "--force", timeout=900)


def _apply_update(target_commit: str, previous_commit: str) -> None:
    try:
        # Remove non-ignored files first so an untracked path cannot block a
        # tracked file introduced by the published version.
        _run_git("clean", "-fd", timeout=300)
        _run_git("reset", "--hard", target_commit)
        _run_git("submodule", "sync", "--recursive", timeout=300)
        _run_git("submodule", "update", "--init", "--recursive", "--force", timeout=900)
        _run_git("lfs", "pull", "origin", BRANCH, timeout=1800)
    except Exception:
        logger.exception("Baka666Bot update failed during file synchronization; restoring the previous version")
        _restore_previous_commit(previous_commit)
        raise


def _check_and_update() -> str | None:
    if _is_development_mode():
        logger.info(
            "Baka666Bot auto-update is disabled by {}=dev",
            UPDATE_MODE_ENV,
        )
        return None

    origin = _run_git("remote", "get-url", "origin")
    if REPOSITORY.lower() not in origin.lower():
        logger.warning("Baka666Bot auto-update skipped because origin is not {}", REPOSITORY)
        return None

    local_commit = _run_git("rev-parse", "HEAD")
    remote_commit = _latest_remote_commit()
    has_local_changes = _working_tree_has_changes()
    if local_commit == remote_commit and not has_local_changes:
        logger.info("Baka666Bot is already up to date ({})", local_commit[:7])
        return None

    logger.info(
        "Baka666Bot update found. Local {}, GitHub {}",
        local_commit[:7],
        remote_commit[:7],
    )
    _run_git("fetch", "--prune", "origin", BRANCH, timeout=900)
    fetched_commit = _run_git("rev-parse", "FETCH_HEAD")
    if fetched_commit != remote_commit:
        raise RuntimeError("Fetched commit does not match the GitHub main branch")

    _apply_update(remote_commit, local_commit)
    return remote_commit


@get_driver().on_startup
async def update_baka666bot() -> None:
    try:
        updated_commit = await asyncio.to_thread(_check_and_update)
    except Exception:
        logger.exception("Baka666Bot update check failed; continuing with the current files")
        return

    if not updated_commit:
        return

    logger.warning("Baka666Bot updated to {}. Restarting the terminal process.", updated_commit[:7])
    os.chdir(PROJECT_ROOT)
    os.execv(sys.executable, [sys.executable, *sys.argv])


def _read_qq_avatar(qq: int) -> bytes:
    request = Request(
        QQ_AVATAR_URL.format(qq=qq),
        headers={
            "User-Agent": "Baka666Bot-Profile-Sync/1.0",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(request, timeout=15) as response:
        data = response.read(MAX_AVATAR_BYTES + 1)
    if len(data) > MAX_AVATAR_BYTES:
        raise ValueError("QQ avatar exceeds the 5 MiB limit")

    with Image.open(BytesIO(data)) as image:
        if image.width * image.height > 16_777_216:
            raise ValueError("QQ avatar dimensions exceed the supported limit")
        normalized = image.convert("RGB")
        output = BytesIO()
        normalized.save(output, format="JPEG", quality=92, optimize=True)
    return output.getvalue()


async def _synchronize_qq_profile(bot: Bot) -> None:
    try:
        login = await bot.call_api("get_login_info")
        source = await bot.call_api(
            "get_stranger_info",
            user_id=MAIN_ACCOUNT_QQ,
            no_cache=True,
        )
        source_nickname = str(source.get("nickname") or "").strip()
        current_nickname = str(login.get("nickname") or "").strip()
        current_qq = int(login.get("user_id") or 0)
        if current_qq <= 0:
            raise ValueError("connected QQ account could not be identified")

        if not source_nickname and current_qq == MAIN_ACCOUNT_QQ:
            source_nickname = current_nickname
        if not source_nickname:
            raise ValueError("main QQ account nickname is unavailable")

        if source_nickname != current_nickname:
            await bot.call_api("set_qq_profile", nickname=source_nickname)
            logger.info("QQ profile nickname synchronized from {}", MAIN_ACCOUNT_QQ)

        if current_qq == MAIN_ACCOUNT_QQ:
            return

        source_avatar, current_avatar = await asyncio.gather(
            asyncio.to_thread(_read_qq_avatar, MAIN_ACCOUNT_QQ),
            asyncio.to_thread(_read_qq_avatar, current_qq),
        )
        if hashlib.sha256(source_avatar).digest() == hashlib.sha256(current_avatar).digest():
            return

        encoded_avatar = base64.b64encode(source_avatar).decode("ascii")
        await bot.call_api("set_qq_avatar", file=f"base64://{encoded_avatar}")
        logger.info("QQ profile avatar synchronized from {}", MAIN_ACCOUNT_QQ)
    except Exception:
        logger.exception("QQ profile synchronization failed")


def _is_main_group_invite(event: Event) -> bool:
    return (
        isinstance(event, GroupRequestEvent)
        and event.sub_type == "invite"
        and event.group_id == MAIN_GROUP_ID
    )


main_group_invite = on_request(
    rule=Rule(_is_main_group_invite),
    priority=0,
    block=True,
)


@main_group_invite.handle()
async def _accept_main_group_invite(bot: Bot, event: GroupRequestEvent) -> None:
    await event.approve(bot)
    logger.info("Accepted an invitation to main group {}", MAIN_GROUP_ID)


@get_driver().on_bot_connect
async def synchronize_account_and_check_group(bot: Bot) -> None:
    if bot.adapter.get_name() != "OneBot V11":
        return

    await _synchronize_qq_profile(bot)
    try:
        groups = await bot.call_api("get_group_list")
        joined = any(int(group.get("group_id", 0)) == MAIN_GROUP_ID for group in groups)
        if joined:
            logger.info("Baka666Bot is already in main group {}", MAIN_GROUP_ID)
        else:
            logger.warning(
                "Baka666Bot is not in main group {}. OneBot cannot join a group without an invitation. "
                "An invitation to this group will be accepted automatically.",
                MAIN_GROUP_ID,
            )
    except Exception:
        logger.exception("Could not check membership in main group {}", MAIN_GROUP_ID)
