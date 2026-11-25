import asyncio

import nonebot

nonebot.init()
nonebot.load_plugin("nonebot_plugin_orm")

import nonebot_plugin_orm

asyncio.run(nonebot_plugin_orm.init_orm())

from nonebot_plugin_orm.__main__ import orm

orm(["upgrade"], standalone_mode=False)
