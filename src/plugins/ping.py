from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event

ping = on_command("ping", aliases={"测试"}, priority=10, block=True)

@ping.handle()
async def handle_ping(bot: Bot, event: Event):
    await ping.finish("Pong! Baka666Bot 已准备就绪！")
