import asyncio
import sys
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import nonebot
from sqlalchemy.util import greenlet_spawn

nonebot.init()
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
