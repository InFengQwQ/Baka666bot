import sys
from nonebot import get_driver
from nonebot.log import logger

from .MalodyAPI.database import db

import logging

class SkipPrivateMessageDebug(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if "call=on_private_message" in msg:
            return False
        return True

logging.getLogger("nonebot").addFilter(SkipPrivateMessageDebug())

driver = get_driver()

@driver.on_startup
async def startup():
    await db.connect()
    logger.info("MalodyVClientPlugin 数据库已连接")

@driver.on_shutdown
async def shutdown():
    await db.close()
    logger.info("MalodyVClientPlugin 数据库已关闭")

from .matcher import login, mm, mmocr, mmbest, ma