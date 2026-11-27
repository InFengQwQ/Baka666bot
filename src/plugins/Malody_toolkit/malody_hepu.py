import base64
from pathlib import Path

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.log import logger

hepu = on_command("合谱", priority=5, block=True)

ASSET = Path(__file__).parent / "Malody合谱工具.html"


@hepu.handle()
async def handle_hepu(bot: Bot, event: GroupMessageEvent):
    if not ASSET.exists():
        logger.warning(f"[Malody_toolkit] 合谱工具文件不存在: {ASSET}")
        return
    # NapCat cannot read the source tree, so hand it the bytes.
    payload = base64.b64encode(ASSET.read_bytes()).decode()
    try:
        await bot.upload_group_file(
            group_id=event.group_id,
            file=f"base64://{payload}",
            name="Malody合谱工具.html",
        )
    except Exception:
        logger.exception("[Malody_toolkit] 上传合谱工具文件失败")
