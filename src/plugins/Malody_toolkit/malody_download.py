import asyncio
import io
import re
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional

import aiohttp
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent, PrivateMessageEvent
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import Message

# ---------- 配置 ----------
CONFIG = {
    "FALLBACK_API": "http://api.paimonnokoya.me/api/store/download",
    "CONCURRENCY": 4,
    "TIMEOUT": 60,
    "MAX_RETRIES": 3,
}


async def _get_store_cred():
    from src.plugin_runtime import malody_download_account
    return await malody_download_account() or (None, None)


async def _official_metadata(cid: str) -> dict | None:
    uid, store_token = await _get_store_cred()
    if not store_token:
        return None
    try:
        from nonebot import require
        from importlib import import_module
        plugin = require("MalodyVClientPlugin")
        get_download = import_module(plugin.__name__ + ".MalodyAPI.store.download").get_download
        import asyncio as aio
        return await aio.to_thread(get_download, store_token=store_token, uid=uid, cid=cid)
    except Exception:
        return None


async def fetch_metadata(session: aiohttp.ClientSession, cid: str) -> dict:
    """获取谱面元数据（优先官方API，私服后备）"""
    data = await _official_metadata(cid)
    if data is None or data.get("code") != 0 or not data.get("items"):
        import time
        ts = int(time.time())
        from urllib.parse import urlencode
        uid, store_token = await _get_store_cred()
        if not store_token:
            from src.plugin_runtime import MALODY_DOWNLOAD_HINT
            raise ValueError(MALODY_DOWNLOAD_HINT)
        url = CONFIG['FALLBACK_API'] + "?" + urlencode({"api": "202409", "uid": uid, "key": store_token, "cid": cid, "t": ts})
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            data = await resp.json()
    if data.get("code") != 0 or not data.get("items"):
        raise ValueError(f"Invalid metadata for CID {cid}")
    return data

# ---------- 工具函数 ----------
async def download_file(session: aiohttp.ClientSession, url: str, retries: int = CONFIG["MAX_RETRIES"]) -> bytes:
    """带重试的文件下载"""
    for attempt in range(retries + 1):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=CONFIG["TIMEOUT"])) as resp:
                resp.raise_for_status()
                return await resp.read()
        except Exception as e:
            if attempt == retries:
                raise
            logger.warning(f"[Retry] Download failed ({attempt+1}/{retries}): {url} - {e}")
            await asyncio.sleep(1)
    raise RuntimeError("Unreachable")

# ---------- 网页解析工具 ----------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
}

async def fetch_song_name_from_chart(cid: str) -> str:
    """从 chart 页面提取歌曲名（用于单个 CID）"""
    url = f"https://m.mugzone.net/chart/{cid}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS, timeout=15) as resp:
                if resp.status != 200:
                    return ""
                html = await resp.text()

        match = re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', html)
        if not match:
            return ""
        title = match.group(1)
        # 格式：歌曲名 模式 难度 Lv.xx (作者)
        m = re.match(r'^(.*?)\s+\d+K', title)
        if m:
            return m.group(1).strip()
        m = re.match(r'^(.*?)\s+Lv\.\d+', title)
        if m:
            return m.group(1).strip()
        return title.strip()
    except Exception:
        return ""

async def fetch_song_name_from_song(sid: str) -> str:
    """从 song 页面提取歌曲名（用于 SID）"""
    url = f"https://m.mugzone.net/song/{sid}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS, timeout=15) as resp:
                if resp.status != 200:
                    return ""
                html = await resp.text()

        match = re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', html)
        if match:
            return match.group(1).strip()
        return ""
    except Exception:
        return ""

async def fetch_cids_from_sid(sid: str) -> List[str]:
    """从 song 页面获取所有 CID"""
    url = f"https://m.mugzone.net/song/{sid}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS, timeout=15) as resp:
                if resp.status != 200:
                    logger.error(f"Song page returned {resp.status}")
                    return []
                html = await resp.text()

        # 提取所有 /chart/数字 的链接
        cids = re.findall(r'/chart/(\d+)', html)
        # 去重并保持顺序
        seen = set()
        unique_cids = []
        for cid in cids:
            if cid not in seen:
                seen.add(cid)
                unique_cids.append(cid)
        logger.info(f"[SID {sid}] 发现 CID: {unique_cids}")
        return unique_cids
    except Exception as e:
        logger.error(f"[SID {sid}] 获取 CID 列表失败: {e}")
        return []

# ---------- 打包逻辑 ----------
def safe_filename(original: str) -> str:
    """清理文件名中的非法字符"""
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-.")
    cleaned = "".join(c if c in allowed else "_" for c in original).strip()
    return cleaned if cleaned else "unnamed"

async def download_and_package_single(cid: str, output_dir: Path, shared_state: dict) -> None:
    """
    下载单个 CID 的所有文件，并将文件添加到共享的压缩包状态中
    shared_state 包含:
      - archive: ZipFile 对象
      - used_names: set 已用文件名（用于去重）
      - processed_hashes: set 已处理的 hash
      - semaphore: asyncio.Semaphore
    """
    connector = aiohttp.TCPConnector(limit=CONFIG["CONCURRENCY"] * 2)
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            meta = await fetch_metadata(session, cid)
        except Exception as e:
            logger.error(f"[CID {cid}] 获取元数据失败: {e}")
            return
        items = meta["items"]

        async def process_item(item: dict):
            if item["hash"] in shared_state["processed_hashes"]:
                return
            shared_state["processed_hashes"].add(item["hash"])

            async with shared_state["semaphore"]:
                try:
                    raw = await download_file(session, item["file"])
                except Exception as e:
                    logger.error(f"[CID {cid}] 下载文件失败 {item['name']}: {e}")
                    return

            # 尝试解压 zip
            entries = []
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        data = zf.read(info)
                        name = _unique_name(info.filename, shared_state["used_names"])
                        entries.append((name, data))
            except zipfile.BadZipFile:
                name = _unique_name(item["name"], shared_state["used_names"])
                entries = [(name, raw)]

            # 写入共享压缩包
            for name, data in entries:
                shared_state["archive"].writestr(f"0/{name}", data)

        tasks = [process_item(item) for item in items]
        await asyncio.gather(*tasks, return_exceptions=True)

def _unique_name(original: str, used_names: set) -> str:
    """在 used_names 集合中生成唯一文件名"""
    clean = original.lstrip("/").lstrip("0/") or "unnamed"
    final = clean
    counter = 1
    stem, ext = Path(clean).stem, Path(clean).suffix
    while final in used_names:
        final = f"{stem}_{counter}{ext}"
        counter += 1
    used_names.add(final)
    return final

async def build_mcz(cids: List[str], output_path: Path):
    """为多个 CID 构建一个 .mcz 文件"""
    shared = {
        "used_names": set(),
        "processed_hashes": set(),
        "semaphore": asyncio.Semaphore(CONFIG["CONCURRENCY"]),
    }
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as mcz:
        mcz.writestr("0/", "")
        shared["archive"] = mcz
        tasks = [download_and_package_single(cid, output_path.parent, shared) for cid in cids]
        await asyncio.gather(*tasks)

# ---------- 命令处理 ----------
download_cmd = on_command("download", block=True)

@download_cmd.handle()
async def handle_download(bot: Bot, event: MessageEvent, arg: Message = CommandArg()):
    from src.plugin_runtime import MALODY_DOWNLOAD_HINT
    if not (await _get_store_cred())[1]:
        await bot.send(event, MALODY_DOWNLOAD_HINT)
        await download_cmd.finish()
    raw = arg.extract_plain_text().strip()
    if not raw:
        logger.error("未提供参数")
        await download_cmd.finish()

    # 解析前缀 c 或 s
    prefix = raw[0].lower()
    id_str = raw[1:]
    if prefix not in ('c', 's') or not id_str.isdigit():
        logger.error(f"无效参数格式: {raw}，应为 c<CID> 或 s<SID>")
        await download_cmd.finish()

    logger.info(f"收到下载请求: {raw}, 来自 {event.get_user_id()}")

    try:
        if prefix == 'c':
            cid = id_str
            # 获取歌曲名（从 chart 页面）
            song_name = await fetch_song_name_from_chart(cid) or f"chart_{cid}"
            safe_name = safe_filename(song_name)
            # 临时文件
            tmpdir = Path(tempfile.mkdtemp())
            mcz_path = tmpdir / f"{safe_name}.mcz"
            # 打包单个 CID
            await build_mcz([cid], mcz_path)
        else:  # prefix == 's'
            sid = id_str
            # 获取该 SID 下的所有 CID
            cids = await fetch_cids_from_sid(sid)
            if not cids:
                logger.error(f"[SID {sid}] 未找到任何谱面")
                await download_cmd.finish()
            # 获取歌曲名（从 song 页面）
            song_name = await fetch_song_name_from_song(sid) or f"song_{sid}"
            safe_name = safe_filename(song_name)
            tmpdir = Path(tempfile.mkdtemp())
            mcz_path = tmpdir / f"{safe_name}.mcz"
            # 打包所有 CID
            await build_mcz(cids, mcz_path)

        # 上传文件
        if isinstance(event, GroupMessageEvent):
            await bot.upload_group_file(
                group_id=event.group_id,
                file=str(mcz_path.absolute()),
                name=mcz_path.name
            )
        elif isinstance(event, PrivateMessageEvent):
            await bot.upload_private_file(
                user_id=event.user_id,
                file=str(mcz_path.absolute()),
                name=mcz_path.name
            )
        else:
            logger.warning(f"不支持的消息类型: {type(event)}")
    except Exception as e:
        logger.error(f"处理失败: {e}")
    finally:
        await download_cmd.finish()
