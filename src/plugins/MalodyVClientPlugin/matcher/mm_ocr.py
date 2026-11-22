from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, Message
from nonebot.params import CommandArg
from nonebot_plugin_waiter import waiter

from .handler.mmocr_handler import process_mm_ocr

mmocr_cmd = on_command("mmocr", aliases={"mm识别", "mmocr"}, priority=5)


def extract_image_url(message: Message) -> str | None:
    for seg in message:
        if seg.type == "image" or "url" in seg.data:
            return seg.data.get("url", "")
    return None


async def ask_level(bot: Bot, event: Event) -> int | None:
    """向用户询问等级，返回整数或 None（超时/取消）"""
    await bot.send(event, "请输入等级（Level）：")
    resp = await waiter.wait_for(bot, event, timeout=30)
    if resp is None:
        await bot.send(event, "等待超时，已取消。")
        return None
    text = resp.get_plaintext().strip()
    try:
        lv = int(text)
        if lv <= 0 or lv >= 65536:
            await bot.send(event, "等级不合法，已取消。")
            return None
        return lv
    except ValueError:
        await bot.send(event, "输入非数字，已取消。")
        return None


async def ask_ratio(bot: Bot, event: Event) -> float | None:
    """向用户询问倍率，返回浮点数或 None"""
    await bot.send(event, "请输入倍率（Ratio）：")
    resp = await waiter.wait_for(bot, event, timeout=30)
    if resp is None:
        await bot.send(event, "等待超时，已取消。")
        return None
    text = resp.get_plaintext().strip()
    try:
        r = float(text)
        if r <= 0:
            await bot.send(event, "倍率须大于 0，已取消。")
            return None
        return r
    except ValueError:
        await bot.send(event, "输入非数字，已取消。")
        return None


@mmocr_cmd.handle()
async def handle_mmocr(bot: Bot, event: Event, args: Message = CommandArg()):
    # 提取命令后的文本参数
    text = args.extract_plain_text().strip()
    parts = text.split()

    # 获取图片（命令消息本身或回复消息）
    img_url = extract_image_url(args)
    if not img_url and event.reply:
        img_url = extract_image_url(event.reply.message)

    if not img_url:
        await mmocr_cmd.finish("请回复一张 Malody 结算截图，并使用 /mmocr [等级] [倍率]")

    # 尝试从命令参数中直接获取 level / ratio
    level = None
    ratio = None
    if len(parts) >= 1:
        try:
            level = int(parts[0])
        except ValueError:
            pass
    if len(parts) >= 2:
        try:
            ratio = float(parts[1])
        except ValueError:
            pass

    # 参数不全则逐个询问
    if level is None:
        level = await ask_level(bot, event)
        if level is None:
            return
    if ratio is None:
        ratio = await ask_ratio(bot, event)
        if ratio is None:
            return

    # 执行 OCR
    reply = await process_mm_ocr(img_url, level, ratio)
    await mmocr_cmd.finish(reply)