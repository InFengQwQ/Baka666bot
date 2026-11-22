"""ma download - 获取谱面下载信息"""
import asyncio
from nonebot.adapters.onebot.v11 import Bot, Event
from src.plugin_runtime import malody_download_account, MALODY_DOWNLOAD_HINT
from ...MalodyAPI.store.download import get_download
from ...render.components import simple_card


async def handle(bot: Bot, event: Event, args: str):
    qq = str(event.get_user_id())
    account = await malody_download_account(qq)
    if not account:
        await bot.send(event, MALODY_DOWNLOAD_HINT)
        return
    uid, store_token = account
    cid = args.strip()
    if not cid or not cid.isdigit():
        await bot.send(event, "用法: ma download <CID>")
        return
    try:
        r = await asyncio.to_thread(get_download, store_token=store_token, uid=uid, cid=cid)
        items = r.get("items", [])
        rows = [("CID", cid), ("SID", str(r.get("sid", "?"))), ("UID", str(r.get("uid", "?")))]
        for it in items:
            rows.append((f"  {it.get('name','?')}", it.get("file", "")[:40]))
        img = await simple_card(f"下载: CID {cid}", rows)
        await bot.send(event, __import__("nonebot.adapters.onebot.v11").MessageSegment.image(img))
    except Exception:
        await bot.send(event, "获取失败")
