import asyncio
import sys
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Existing volumes predate the log directory, so create it before the sink opens.
(Path(__file__).resolve().parent.parent / "data" / "logs").mkdir(parents=True, exist_ok=True)

import nonebot
from sqlalchemy.util import greenlet_spawn

nonebot.init()
nonebot.load_plugin("nonebot_plugin_waiter")
nonebot.load_plugin("nonebot_plugin_alconna")
nonebot.load_from_toml("pyproject.toml")

import nonebot_plugin_orm
from nonebot_plugin_orm import migrate

nonebot_plugin_orm._init_orm()


async def upgrade() -> None:
    with migrate.AlembicConfig(
        cmd_opts=Namespace(cmd=(migrate.upgrade, [], []))
    ) as config:
        await greenlet_spawn(migrate.upgrade, config)


asyncio.run(upgrade())
