import asyncio
import base64
import json
import random
import re
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional, List, Tuple

import httpx
from nonebot import on_command, on_message, logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.params import CommandArg
from nonebot.rule import Rule
from PIL import Image

from nonebot.adapters.onebot.v11 import PokeNotifyEvent
from nonebot import on_notice

from .match import check_song_match
from .getmeta import fetch_songs
from src.storage import plugin_data
from src.plugin_runtime import malody_download_account as malody_store_account
from urllib.parse import urlencode

# ==================== 配置 ====================
AUDIO_API = "http://api.paimonnokoya.me/api/store/download"

# ---------- 所有提示相关可配置项 ----------
HINT_CONFIG = {
    "cover_percentages": [1, 3, 8, 30, 100],
    "audio_durations": [5000, 7000, 10000, 15000],
    "hint_probabilities": {
        "cover": 50,
        "audio": 50,
        "meta": 50,
    },
}

# ==================== 全局游戏状态 ====================
games: Dict[int, "Game"] = {}

# 保存每个群上次成功搜索参数的持久化文件路径
LAST_PARAMS_FILE = plugin_data("Malody_guess_song") / "last_guess_params.json"
last_guess_params: Dict[int, dict] = {}


def _load_last_params():
    """从文件加载历史参数"""
    try:
        if LAST_PARAMS_FILE.exists():
            with open(LAST_PARAMS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 键是字符串，需转为 int
                return {int(k): v for k, v in data.items()}
    except Exception as e:
        logger.warning(f"加载上次参数失败：{e}")
    return {}


def _save_last_params():
    """将当前历史参数保存到文件"""
    try:
        with open(LAST_PARAMS_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {str(k): v for k, v in last_guess_params.items()},
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as e:
        logger.warning(f"保存上次参数失败：{e}")


# 启动时加载
last_guess_params = _load_last_params()


class Game:
    def __init__(self, song: dict, bot: Bot, group_id: int, store_account=None):
        self.store_account = store_account
        self.bot = bot
        self.group_id = group_id
        self.song = song
        self.active = True
        self.cover_index = 0
        self.audio_index = 0
        self.meta_used = False
        self.cover_image: Optional[Image.Image] = None
        self.audio_bytes: Optional[bytes] = None
        self.mc_title: Optional[str] = None
        self.version: Optional[str] = None
        self.audio_disabled = False
        self.cover_disabled = False
        self.timer: Optional[asyncio.Task] = None  # 新增超时计时器

    def start_timer(self):
        """启动 5 分钟超时自动结束"""

        async def _auto_end():
            await asyncio.sleep(300)  # 300 秒 = 5 分钟
            if self.active:
                await self.end_game(won=False)

        self.cancel_timer()  # 先取消可能残留的旧计时器
        self.timer = asyncio.ensure_future(_auto_end())

    def cancel_timer(self):
        """取消超时计时器"""
        if self.timer and not self.timer.done():
            self.timer.cancel()
        self.timer = None

    def available_hints(self) -> List[str]:
        hints = []
        cfg = HINT_CONFIG
        if not self.cover_disabled and self.cover_index < len(cfg["cover_percentages"]):
            hints.append("cover")
        if not self.audio_disabled and self.audio_index < len(cfg["audio_durations"]):
            hints.append("audio")
        if not self.meta_used:
            hints.append("meta")
        return hints

    async def download_cover(self):
        if self.cover_image is not None:
            return
        sid = self.song["sid"]
        url = f"http://cni.machart.top/cover/{sid}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    self.cover_image = Image.open(BytesIO(resp.content))
                    logger.info(f"封面下载成功：{url}")
                else:
                    logger.warning(f"封面下载失败，状态码：{resp.status_code}")
                    self.cover_disabled = True
        except Exception as e:
            logger.error(f"封面下载异常：{e}")
            self.cover_disabled = True

    async def download_audio(self):
        if self.audio_bytes is not None:
            return
        sid = str(self.song["sid"])
        logger.info(f"[音频] 开始为 SID {sid} 准备音频")
        try:
            cids = await fetch_cids_from_sid(sid)
            logger.info(f"[音频] SID {sid} 获取到 {len(cids)} 个 CID：{cids}")
            if not cids:
                logger.warning(f"[音频] SID {sid} 无 CID，禁用音频")
                self.audio_disabled = True
                return
            cid = cids[0]
            logger.info(f"[音频] 使用 CID {cid} 下载")
            result = await download_audio_from_cid(cid, self.store_account)
            if result:
                self.audio_bytes, self.mc_title, self.version = result
                logger.info(
                    f"[音频] 成功下载音频，大小 {len(self.audio_bytes)} bytes, mc_title={self.mc_title}, version={self.version}"
                )
            else:
                logger.warning(f"[音频] CID {cid} 下载返回空数据")
                self.audio_disabled = True
        except Exception as e:
            logger.error(f"[音频] 准备失败：{e}")
            self.audio_disabled = True

    def get_cover_crop(self, percentage: float) -> Optional[BytesIO]:
        if self.cover_image is None:
            return None
        try:
            img = self.cover_image
            w, h = img.size
            scale = (percentage / 100.0) ** 0.5
            crop_w = max(1, int(w * scale))
            crop_h = max(1, int(h * scale))
            max_x = w - crop_w
            max_y = h - crop_h
            if max_x < 0 or max_y < 0:
                return None
            x = random.randint(0, max_x)
            y = random.randint(0, max_y)
            crop = img.crop((x, y, x + crop_w, y + crop_h))
            buf = BytesIO()
            crop.save(buf, format="PNG")
            buf.seek(0)
            return buf
        except Exception as e:
            logger.error(f"裁剪封面失败：{e}")
            return None

    def get_audio_clip(self, duration_ms: int) -> Optional[BytesIO]:
        if not self.audio_bytes:
            logger.warning("[音频裁剪] audio_bytes 为空")
            return None
        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_file(BytesIO(self.audio_bytes), format="ogg")
            total_ms = len(audio)
            logger.info(f"[音频裁剪] 音频总长 {total_ms}ms")
            if total_ms <= duration_ms:
                clip = audio
                logger.info("[音频裁剪] 音频长度不足，使用全部")
            else:
                start = random.randint(0, total_ms - duration_ms)
                clip = audio[start : start + duration_ms]
                logger.info(f"[音频裁剪] 随机起点 {start}ms，截取 {duration_ms}ms")

            # 转为 QQ 语音原生的 SILK 参数：24000 Hz, 单声道, 16-bit PCM
            clip = clip.set_frame_rate(24000).set_channels(1).set_sample_width(2)
            buf = BytesIO()
            clip.export(
                buf, format="wav"
            )  # 导出为无损 WAV，go-cqhttp 会自动编码为 SILK
            buf.seek(0)
            logger.info(
                f"[音频裁剪] 导出 WAV 成功，大小 {buf.getbuffer().nbytes} bytes"
            )
            return buf
        except Exception as e:
            logger.error(f"[音频裁剪] 失败：{e}")
            return None

    def next_hint(self) -> Optional[Tuple[str, any]]:
        available = self.available_hints()
        if not available:
            return None
        cfg = HINT_CONFIG
        if "cover" in available and self.cover_index == 0:
            chosen = "cover"
        else:
            probs = cfg["hint_probabilities"]
            total_weight = sum(probs.get(h, 0) for h in available)
            if total_weight == 0:
                chosen = random.choice(available)
            else:
                r = random.random() * total_weight
                cumulative = 0
                chosen = available[-1]
                for h in available:
                    cumulative += probs.get(h, 0)
                    if r <= cumulative:
                        chosen = h
                        break
        if chosen == "cover":
            pct = cfg["cover_percentages"][self.cover_index]
            crop_buf = self.get_cover_crop(pct)
            if crop_buf is None:
                self.cover_disabled = True
                return self.next_hint()
            self.cover_index += 1
            return ("cover", crop_buf)
        elif chosen == "audio":
            duration = cfg["audio_durations"][self.audio_index]
            clip = self.get_audio_clip(duration)
            if clip is None:
                self.audio_disabled = True
                return self.next_hint()
            self.audio_index += 1
            return ("audio", clip)
        elif chosen == "meta":
            self.meta_used = True
            total = self.song["length"]
            mins, secs = divmod(total, 60)
            info = (
                f"曲师：{self.song['artist']}\n"
                f"时长：{mins}:{secs:02d}\n"
                f"BPM：{self.song['bpm']}\n"
                f"版本：{self.version or '未知'}"
            )
            return ("meta", info)
        return None

    def check_answer(self, text: str) -> bool:
        return check_song_match(text, self.song["title"], self.mc_title)

    async def send_hint(self):
        hint = self.next_hint()
        if hint is None:
            try:
                await self.bot.send_group_msg(
                    group_id=self.group_id, message=Message("已无更多提示，加油哦")
                )
            except Exception as e:
                logger.error(f"发送无提示消息失败：{e}")
            return
        hint_type, content = hint
        try:
            if hint_type == "cover":
                img_bytes = content.getvalue()
                b64 = base64.b64encode(img_bytes).decode()
                msg = MessageSegment.image(f"base64://{b64}")
                await self.bot.send_group_msg(group_id=self.group_id, message=msg)
            elif hint_type == "audio":
                audio_bytes = content.getvalue()
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp.write(audio_bytes)
                    tmp_path = tmp.name
                logger.info(
                    f"[发送语音] 临时文件：{tmp_path}，大小 {len(audio_bytes)} bytes"
                )
                try:
                    await self.bot.send_group_msg(
                        group_id=self.group_id,
                        message=MessageSegment.record(file=f"file:///{tmp_path}"),
                    )
                    logger.info("[发送语音] 语音消息已发送")
                finally:
                    Path(tmp_path).unlink(missing_ok=True)
            elif hint_type == "meta":
                await self.bot.send_group_msg(
                    group_id=self.group_id, message=Message(content)
                )
        except Exception as e:
            logger.error(f"发送提示失败：{e}")

    async def end_game(self, won: bool, winner_uid: Optional[int] = None):
        if not self.active:
            return
        self.active = False
        self.cancel_timer()  # 新增：取消超时计时器
        if self.cover_image:
            try:
                buf = BytesIO()
                self.cover_image.save(buf, format="PNG")
                buf.seek(0)
                b64 = base64.b64encode(buf.read()).decode()
                await self.bot.send_group_msg(
                    group_id=self.group_id,
                    message=MessageSegment.image(f"base64://{b64}"),
                )
            except Exception as e:
                logger.error(f"发送完整封面失败：{e}")
        title = self.song["title"]
        artist = self.song["artist"]
        if won and winner_uid:
            await self.bot.send_group_msg(
                group_id=self.group_id,
                message=Message(
                    f"🎉 恭喜 {MessageSegment.at(winner_uid)} 猜对了！\n答案是：{title} - {artist}"
                ),
            )
        else:
            await self.bot.send_group_msg(
                group_id=self.group_id,
                message=Message(f"😿 没有人猜对，答案是：{title} - {artist}"),
            )
        games.pop(self.group_id, None)


# ==================== 音频工具函数 ====================
async def fetch_cids_from_sid(sid: str) -> List[str]:
    url = f"https://m.mugzone.net/song/{sid}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(headers=headers, timeout=15) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
            html = resp.text
        cids = re.findall(r"/chart/(\d+)", html)
        seen = set()
        unique = []
        for c in cids:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique
    except Exception as e:
        logger.error(f"获取 CID 列表失败：{e}")
        return []


async def download_audio_from_cid(
    cid: str,
    store_account=None,
) -> Optional[Tuple[bytes, Optional[str], Optional[str]]]:
    import time

    ts = int(time.time())
    store_account = store_account or await malody_store_account()
    if not store_account:
        return None
    url = AUDIO_API + "?" + urlencode({"api": "202409", "uid": store_account[0], "key": store_account[1], "cid": cid, "t": ts})
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            logger.info("[音频下载] 请求谱面元数据")
            resp = await client.get(url)
            data = resp.json()
            if data.get("code") != 0 or not data.get("items"):
                return None
            items = data["items"]
            mc_content = None
            sound_ref = None
            ogg_data = None
            mc_title = None
            mc_version = None
            for item_idx, item in enumerate(items):
                file_url = item["file"]
                item_name = item.get("name", "")
                try:
                    resp2 = await client.get(file_url, timeout=httpx.Timeout(30))
                    resp2.raise_for_status()
                    raw = resp2.content
                except Exception as e:
                    logger.warning(f"[音频下载] Item {item_idx} 下载失败: {e}")
                    continue
                if raw[:4] == b"OggS":
                    if sound_ref:
                        base = item_name.split("/")[-1]
                        ref_base = sound_ref.split("/")[-1]
                        if (
                            base == sound_ref
                            or base == ref_base
                            or item_name.endswith(sound_ref)
                        ):
                            ogg_data = raw
                            break
                        elif ogg_data is None:
                            ogg_data = raw
                    else:
                        if ogg_data is None:
                            ogg_data = raw
                    continue
                if zipfile.is_zipfile(BytesIO(raw)):
                    with zipfile.ZipFile(BytesIO(raw)) as zf:
                        namelist = zf.namelist()
                        if mc_content is None:
                            for name in namelist:
                                if name.lower().endswith(".mc"):
                                    mc_content = zf.read(name)
                                    mc_data = json.loads(mc_content.decode("utf-8"))
                                    notes = mc_data.get("note", [])
                                    if notes:
                                        sound_ref = notes[-1].get("sound")
                                    mc_title = (
                                        mc_data.get("meta", {})
                                        .get("song", {})
                                        .get("title")
                                    )
                                    mc_version = mc_data.get("meta", {}).get("version")
                                    break
                        if sound_ref:
                            for name in namelist:
                                if name.lower().endswith(".ogg"):
                                    base_name = (
                                        name.rsplit("/", 1)[-1] if "/" in name else name
                                    )
                                    ref_base = (
                                        sound_ref.rsplit("/", 1)[-1]
                                        if "/" in sound_ref
                                        else sound_ref
                                    )
                                    if (
                                        base_name == sound_ref
                                        or base_name == ref_base
                                        or name == sound_ref
                                    ):
                                        ogg_data = zf.read(name)
                                        break
                        if mc_content and ogg_data:
                            break
                else:
                    try:
                        text = raw.decode("utf-8")
                        if text.strip().startswith("{"):
                            mc_data = json.loads(text)
                            notes = mc_data.get("note", [])
                            if notes:
                                sound_ref = notes[-1].get("sound")
                                mc_content = raw
                                mc_title = (
                                    mc_data.get("meta", {}).get("song", {}).get("title")
                                )
                                mc_version = mc_data.get("meta", {}).get("version")
                    except Exception:
                        pass
            if mc_content and sound_ref and ogg_data:
                return ogg_data, mc_title, mc_version
            else:
                return None
    except Exception as e:
        logger.error(f"[音频下载] 异常：{e}")
        return None


# ==================== 命令处理 ====================
ma_guess = on_command(
    "ma猜歌", aliases={"音频猜歌", "malody猜歌", "mag"}, priority=5, block=True
)


@ma_guess.handle()
async def handle_ma_guess(
    bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()
):
    if not isinstance(event, GroupMessageEvent):
        await ma_guess.finish("猜歌仅在群聊中可用")
    store_account = await malody_store_account(str(event.user_id))
    if not store_account:
        await ma_guess.finish("请先按 Malody 原有流程登录并绑定账号。")
    group_id = event.group_id
    if group_id in games and games[group_id].active:
        await ma_guess.finish("当前群已有进行中的猜歌，请等待结束")

    usage = (
        "用法：/ma猜歌 [lvmin=1] [lvmax=40] [count=100] [mode=0] "
        "[type=2] [word=关键词] [bpmmin=...] [bpmmax=...] [lenmin=...] [lenmax=...]\n"
        "无参数时复用本群上次搜索条件"
    )

    default_config = {
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

    if not arg_text:
        # 尝试复用历史参数
        if group_id in last_guess_params:
            config = last_guess_params[group_id].copy()

        else:
            config = default_config.copy()
    else:
        config = default_config.copy()
        parts = arg_text.split()
        for part in parts:
            if "=" not in part:
                # 等级简写 37-38
                level_match = re.match(r"^(\d{1,2})-(\d{1,2})$", part)
                if level_match:
                    config["lvmin"] = int(level_match.group(1))
                    config["lvmax"] = int(level_match.group(2))
                    continue
                else:
                    await ma_guess.finish(usage)
            k, v = part.split("=", 1)
            k = k.strip().lower()
            v = v.strip()
            if k not in config:
                await ma_guess.finish(usage)
            if k in (
                "lvmin",
                "lvmax",
                "count",
                "mode",
                "bpmmin",
                "bpmmax",
                "lenmin",
                "lenmax",
            ):
                try:
                    config[k] = int(v)
                except ValueError:
                    await ma_guess.finish(usage)
            else:
                config[k] = v

    # 校验
    if (
        not (1 <= config["lvmin"] <= 2147483648 and 1 <= config["lvmax"] <= 2147483648)
        or config["lvmin"] > config["lvmax"]
    ):
        await ma_guess.finish(usage)
    if not (10 <= config["count"] <= 1000):
        await ma_guess.finish(usage)
    if config["mode"] is not None and config["mode"] not in (0, 1, 2, 3):
        await ma_guess.finish(usage)
    if config["bpmmin"] is not None and config["bpmmin"] < 0:
        await ma_guess.finish(usage)
    if config["lenmin"] is not None and config["lenmin"] < 0:
        await ma_guess.finish(usage)

    try:
        songs = await asyncio.to_thread(fetch_songs,
            store_key=store_account[1],
            store_uid=store_account[0],
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
    except Exception as e:
        logger.error(f"获取歌曲列表失败：{e}")
        await ma_guess.finish("获取歌曲失败，请稍后重试")

    if not songs:
        await ma_guess.finish("没有符合条件的歌曲，请调整条件")

    # 保存本次成功使用的参数
    last_guess_params[group_id] = config.copy()
    _save_last_params()

    song = random.choice(songs)
    game = Game(song, bot, group_id, store_account)
    games[group_id] = game
    game.start_timer()  # 新增：启动超时计时器
    logger.info(f"[猜歌答案] 歌曲：{song['title']} - {song['artist']} (SID: {song['sid']})")
    # 将答案私发给机器人自己
    try:
        await bot.send_private_msg(
            user_id=bot.self_id,
            message=Message(f"答案：{song['title']} - {song['artist']}")
        )
    except Exception as e:
        logger.error(f"发送答案到私信失败：{e}")

    await asyncio.gather(game.download_cover(), game.download_audio())
    #await bot.send_group_msg(group_id=group_id, message=Message(""))
    await game.send_hint()


hint_cmd = on_command(
    "提示", aliases={"音频提示", "猜歌提示", "ts", "tishi"}, priority=5, block=True
)


@hint_cmd.handle()
async def handle_hint(bot: Bot, event: GroupMessageEvent):
    if not isinstance(event, GroupMessageEvent):
        return
    group_id = event.group_id
    game = games.get(group_id)
    if not game or not game.active:
        return
    await game.send_hint()


@on_notice().handle()
async def _poke_hint(bot: Bot, event: PokeNotifyEvent):
    if not isinstance(event, PokeNotifyEvent):
        return
    if not event.is_tome():
        return
    group_id = event.group_id
    game = games.get(group_id)
    if game and game.active:
        await game.send_hint()


answer_cmd = on_command(
    "答案",
    aliases={"结束", "结束猜歌", "取消猜歌", "answer", "ans"},
    priority=5,
    block=True,
)


@answer_cmd.handle()
async def handle_answer(bot: Bot, event: GroupMessageEvent):
    if not isinstance(event, GroupMessageEvent):
        return
    group_id = event.group_id
    game = games.get(group_id)
    if not game or not game.active:
        await answer_cmd.finish("当前没有进行中的猜歌")
    await game.end_game(won=False)


def _check_answer(event: MessageEvent) -> bool:
    if not isinstance(event, GroupMessageEvent):
        return False
    group_id = event.group_id
    game = games.get(group_id)
    if not game or not game.active:
        return False
    return game.check_answer(event.get_plaintext())


answer_matcher = on_message(rule=Rule(_check_answer), priority=10, block=False)


@answer_matcher.handle()
async def handle_guess(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    game = games.get(group_id)
    if not game or not game.active:
        return
    await game.end_game(won=True, winner_uid=event.user_id)
