from __future__ import annotations

import asyncio
import hashlib
import random
import re
from typing import Any

from nonebot import logger, on_command, on_message
from nonebot.adapters import Bot, Event, Message
from nonebot.params import CommandArg
from nonebot.rule import Rule

from . import foreign_adapter
from .framework import PlatformBot, is_group_event

try:
    from src.plugin_runtime import import_plugin_module
    _native_peer = import_plugin_module('Malody_guess_song', '')
    HINT_CONFIG = _native_peer.HINT_CONFIG
    Game = _native_peer.Game
    _save_last_params = _native_peer._save_last_params
    fetch_songs = _native_peer.fetch_songs
    last_guess_params = _native_peer.last_guess_params
except ImportError:
    HINT_CONFIG = {}
    Game = None
    fetch_songs = None
    last_guess_params = {}


PORTABLE_GAMES: dict[str, Any] = {}


def _scope(event: Event) -> str:
    chat = getattr(event, "chat", None)
    if chat is not None:
        return f"telegram:{chat.id}"
    return f"discord:{getattr(event, 'channel_id', event.get_session_id())}"


def _config_key(scope: str) -> int:
    return int.from_bytes(
        hashlib.blake2b(scope.encode("utf-8"), digest_size=8).digest(),
        "big",
    ) & 0x7FFFFFFFFFFFFFFF


def _is_foreign_group(bot: Bot, event: Event) -> bool:
    return (
        bot.adapter.get_name() in {"Discord", "Telegram"}
        and is_group_event(event)
    )


ma_guess = on_command(
    "ma猜歌",
    aliases={"音频猜歌", "malody猜歌", "mag"},
    priority=5,
    block=True,
    rule=Rule(_is_foreign_group),
)


@ma_guess.handle()
async def handle_ma_guess(
    bot: Bot, event: Event, args: Message = CommandArg()
):
    if Game is None or fetch_songs is None:
        await ma_guess.finish("猜歌模块不可用。")

    scope = _scope(event)
    current = PORTABLE_GAMES.get(scope)
    if current and current.active:
        await ma_guess.finish("当前会话已有进行中的猜歌，请等待结束。")

    usage = (
        "用法：/ma猜歌 [lvmin=1] [lvmax=40] [count=100] [mode=0] "
        "[type=2] [word=关键词] [bpmmin=...] [bpmmax=...] [lenmin=...] [lenmax=...]\n"
        "无参数时复用本会话上次搜索条件。"
    )
    config = {
        "lvmin": 1,
        "lvmax": 40,
        "count": 200,
        "mode": None,
        "type": "2",
        "word": None,
        "bpmmin": None,
        "bpmmax": None,
        "lenmin": None,
        "lenmax": None,
    }
    arg_text = args.extract_plain_text().strip()
    history_key = _config_key(scope)
    if not arg_text and history_key in last_guess_params:
        config.update(last_guess_params[history_key])
    elif arg_text:
        for part in arg_text.split():
            if "=" not in part:
                match = re.fullmatch(r"(\d{1,2})-(\d{1,2})", part)
                if match:
                    config["lvmin"] = int(match.group(1))
                    config["lvmax"] = int(match.group(2))
                    continue
                await ma_guess.finish(usage)
            key, value = part.split("=", 1)
            key = key.lower().strip()
            if key not in config:
                await ma_guess.finish(usage)
            if key in {
                "lvmin",
                "lvmax",
                "count",
                "mode",
                "bpmmin",
                "bpmmax",
                "lenmin",
                "lenmax",
            }:
                try:
                    config[key] = int(value)
                except ValueError:
                    await ma_guess.finish(usage)
            else:
                config[key] = value

    if not (
        1 <= config["lvmin"] <= config["lvmax"]
        and 10 <= config["count"] <= 1000
        and (config["mode"] is None or config["mode"] in (0, 1, 2, 3))
    ):
        await ma_guess.finish(usage)

    try:
        songs = await asyncio.to_thread(
            fetch_songs,
            lvmin=config["lvmin"],
            lvmax=config["lvmax"],
            target_count=config["count"],
            mode=config["mode"],
            type_str=config["type"],
            word=config["word"],
            bpmmin=config["bpmmin"],
            bpmmax=config["bpmmax"],
            lenmin=config["lenmin"],
            lenmax=config["lenmax"],
        )
    except Exception as exc:
        logger.opt(exception=exc).error("Cross-platform song search failed")
        await ma_guess.finish("获取歌曲失败，请稍后重试。")
    if not songs:
        await ma_guess.finish("没有符合条件的歌曲，请调整条件。")

    last_guess_params[history_key] = config.copy()
    _save_last_params()
    game = Game(songs[random.randrange(len(songs))], PlatformBot(bot, event), scope)
    PORTABLE_GAMES[scope] = game
    game.start_timer()
    await asyncio.gather(game.download_cover(), game.download_audio())
    await game.send_hint()


hint = on_command(
    "提示",
    aliases={"音频提示", "猜歌提示", "ts", "tishi"},
    priority=5,
    block=True,
    rule=Rule(_is_foreign_group),
)


@hint.handle()
async def handle_hint(bot: Bot, event: Event):
    game = PORTABLE_GAMES.get(_scope(event))
    if game and game.active:
        await game.send_hint()


answer = on_command(
    "答案",
    aliases={"结束", "结束猜歌", "取消猜歌", "answer", "ans"},
    priority=5,
    block=True,
    rule=Rule(_is_foreign_group),
)


@answer.handle()
async def handle_answer(bot: Bot, event: Event):
    scope = _scope(event)
    game = PORTABLE_GAMES.get(scope)
    if not game or not game.active:
        await answer.finish("当前没有进行中的猜歌。")
    await game.end_game(won=False)
    PORTABLE_GAMES.pop(scope, None)


async def _answer_match(bot: Bot, event: Event) -> bool:
    game = PORTABLE_GAMES.get(_scope(event))
    return (
        bot.adapter.get_name() in {"Discord", "Telegram"}
        and is_group_event(event)
        and bool(game and game.active)
        and game.check_answer(event.get_plaintext())
    )


answer_matcher = on_message(
    rule=Rule(_answer_match),
    priority=10,
    block=False,
)


@answer_matcher.handle()
async def handle_guess(bot: Bot, event: Event):
    scope = _scope(event)
    game = PORTABLE_GAMES.get(scope)
    if not game or not game.active:
        return
    await game.end_game(won=True, winner_uid=event.get_user_id())
    PORTABLE_GAMES.pop(scope, None)
