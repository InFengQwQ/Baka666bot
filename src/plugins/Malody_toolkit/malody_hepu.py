from nonebot import on_command
from nonebot.log import logger
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from pathlib import Path

hepu = on_command("合谱", priority=5, block=True)

@hepu.handle()
async def handle_hepu(bot: Bot, event: GroupMessageEvent):
    file_path = Path(__file__).parent / "Malody合谱工具.html"
    if not file_path.exists():
        logger.warning(f"[Malody_toolkit] 合谱工具文件不存在: {file_path}")
        #await hepu.finish("合谱工具文件不存在，请联系维护者同步插件资源。")
        return
    try:
        await bot.upload_group_file(
            group_id=event.group_id,
            file=str(file_path),
            name="Malody合谱工具.html"
        )
    except Exception as e:
        logger.exception("[Malody_toolkit] 上传合谱工具文件失败")
        #await hepu.finish(f"上传合谱工具文件失败：请反馈bot主人")
        return
