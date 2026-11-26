import sys
import os
from pathlib import Path

project_root = Path(__file__).resolve().parent
os.chdir(project_root)
plugin_tool_root = project_root / "src" / "plugins" / "Malody_toolkit" / "tools"
os.environ["BAKA_DATA_DIR"] = str(project_root / "data")
os.environ["BAKA_TOOLS_DIR"] = str(plugin_tool_root)

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter
from nonebot.message import event_preprocessor
from nonebot.exception import IgnoredException
from nonebot.adapters.onebot.v11 import PrivateMessageEvent
from loguru import logger as loguru_logger


#-------------------------------------------------------------------------#
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
# ---------- 水印配置 ----------
WATERMARK_TEXT = "Baka666Bot @猫猫虫小窝"
WATERMARK_OPACITY = 180          # 透明度 0-255
WATERMARK_MARGIN = 30            # 距离底部边距（像素）

def add_watermark_to_image(image: Image.Image) -> Image.Image:
    """为单张图像添加底部水印（返回新图像，不修改原图）"""
    # 确保图像是 RGBA 模式以便处理透明度
    if image.mode != 'RGBA':
        img = image.convert('RGBA')
    else:
        img = image.copy()
    
    draw = ImageDraw.Draw(img, 'RGBA')
    
    # 尝试加载中文字体（根据你的系统调整路径）
    try:
        font = ImageFont.truetype("msyh.ttc", max(20, img.width // 40))
    except:
        font = ImageFont.load_default()
    
    # 获取文字尺寸
    bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    x = (img.width - text_w) // 2
    y = img.height - text_h - WATERMARK_MARGIN
    
    # 先绘制半透明黑色阴影，再绘制白色文字
    draw.text((x+2, y+2), WATERMARK_TEXT, font=font, fill=(0, 0, 0, WATERMARK_OPACITY//2))
    draw.text((x, y), WATERMARK_TEXT, font=font, fill=(255, 255, 255, WATERMARK_OPACITY))
    
    return img

def patched_save(self, fp, format=None, **params):
    """在保存前自动添加水印，并按需消除透明度"""
    # 仅对 PNG/JPEG/WEBP 等常见格式添加水印
    if format in ('PNG', 'JPEG', 'WEBP'):
        watermarked = add_watermark_to_image(self)

        # 原有：JPEG 合成到白色背景
        if format == 'JPEG' and watermarked.mode == 'RGBA':
            background = Image.new('RGB', watermarked.size, (255, 255, 255))
            background.paste(watermarked, mask=watermarked.split()[3])
            watermarked = background

        # 新增：PNG 合成到黑色背景（消除透明度）
        elif format == 'PNG' and watermarked.mode == 'RGBA':
            background = Image.new('RGB', watermarked.size, (0, 0, 0))
            background.paste(watermarked, mask=watermarked.split()[3])
            watermarked = background

        # 如果你希望 WEBP 也不带透明度，可以按同样方式处理
        # elif format == 'WEBP' and watermarked.mode == 'RGBA':
        #     background = Image.new('RGB', watermarked.size, (0, 0, 0))
        #     background.paste(watermarked, mask=watermarked.split()[3])
        #     watermarked = background

        return _original_save(watermarked, fp, format=format, **params)
    else:
        return _original_save(self, fp, format=format, **params)

# 保存原始的 save 方法
_original_save = Image.Image.save

# 应用猴子补丁
Image.Image.save = patched_save

#---------------------------------------------------------------------#

# 初始化 NoneBot
nonebot.init(_env_file=[".env", "config/adapters.env", "config/malody.env"])
loguru_logger.add(
    "logs/bot_{time:YYYY-MM-DD}.log",   # 日志文件路径（支持时间格式化）
    rotation="10 MB",                   # 达到 10 MB 自动轮转
    retention=7,                        # 保留最近 7 个日志文件
    encoding="utf-8",
    level="DEBUG",                      # 记录 DEBUG 及以上级别
)

# 添加全局事件拦截：除了主人外，只允许在群聊中触发
@event_preprocessor
async def block_non_superuser_private(event: PrivateMessageEvent):
    superusers = nonebot.get_driver().config.superusers
    if str(event.user_id) not in superusers:
        raise IgnoredException("非超级用户禁止私聊使用机器人")

# 暂时仅启用 QQ；Discord / Telegram 的账号配置保留，恢复服务时再注册适配器。
driver = nonebot.get_driver()
driver.register_adapter(ONEBOT_V11Adapter)

# Filter progress/acknowledgement/error chatter at the OneBot API boundary.
# This also covers third-party plugins loaded from src/plugins.
from src.outbound_filter import install_outbound_message_filter

install_outbound_message_filter()

# These two plugins are imported directly by several local plugins. Loading them
# first avoids dependency-order races during plugin directory discovery.
nonebot.load_plugin("nonebot_plugin_waiter")
nonebot.load_plugin("nonebot_plugin_alconna")

# 加载配置中的插件
nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    nonebot.run()
