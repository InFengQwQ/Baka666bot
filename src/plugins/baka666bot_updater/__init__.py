"""Check and apply published Baka666Bot updates before adapters connect."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

from nonebot import get_driver, logger
from nonebot.plugin import PluginMetadata


__plugin_meta__ = PluginMetadata(
    name="Baka666Bot 自动更新",
    description="启动时检查 Baka666Bot 主仓库并同步已发布版本。",
    usage="Bot 启动时自动检查并应用主仓库更新。",
)

REPOSITORY = "MCPsDE/Baka666bot"
BRANCH = "main"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
UPDATE_MODE_ENV = "BAKA666BOT_UPDATE_MODE"
GITHUB_COMMIT_API = f"https://api.github.com/repos/{REPOSITORY}/commits/{BRANCH}"


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
