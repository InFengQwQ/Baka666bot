import time
from pathlib import Path
from urllib.parse import quote

import httpx
from PIL import Image, ImageDraw, ImageFont

from nonebot import on_command, get_driver
from nonebot.adapters.onebot.v11 import MessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from nonebot.log import logger
from src.plugin_runtime import credential, osubot_font
from src.storage import plugin_data

# ---------- 路径 & 配置 ----------
plugin_dir = Path(__file__).parent
HELP_IMAGE = plugin_data("image_generation") / "help_image.png"

driver = get_driver()
config = driver.config

KEY = credential("POLLINATIONS_KEY")

COOLDOWN_SECONDS = 300
cooldown_map = {}

# ---------- 字体加载 ----------
FONT_TITLE = osubot_font(36)
FONT_BODY = None    # 正文字体 (中文字体)

def load_fonts():
    global FONT_BODY

    # 1. 加载中文字体（正文）
    cjk_candidates = [
        r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑
        r"C:\Windows\Fonts\simsun.ttc",    # 宋体
        r"C:\Windows\Fonts\simhei.ttf",    # 黑体
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for path in cjk_candidates:
        if Path(path).exists():
            try:
                FONT_BODY = ImageFont.truetype(path, 22)
                logger.info(f"已加载中文字体：{path}")
                return
            except Exception:
                continue

    # 都没找到则用默认字体（无法显示中文）
    FONT_BODY = ImageFont.load_default()
    logger.warning("未找到中文字体，帮助图片中文可能无法正常显示")

# ---------- 帮助图片内容 ----------
HELP_LINES = [
    ("/生图 使用帮助", "title"),
    ("", "blank"),
    ("基本用法：", "body"),
    ("/生图 <提示词> [可选参数]", "cmd"),
    ("", "blank"),
    ("可选参数（可任意组合）：", "body"),
    ("  --width <整数>       宽度，默认512", "cmd"),
    ("  --height <整数>      高度，默认512", "cmd"),
    ("  --model <模型>       模型名：flux(默认), dreamshaper, sdxl", "cmd"),
    ("  --seed <整数>        随机种子，固定可复现", "cmd"),
    ("  --negative <文本>    负面提示词", "cmd"),
    ("  --nologo             去除水印（默认开启）", "cmd"),
    ("  --enhance            增强画质", "cmd"),
    ("  --private            私密生成", "cmd"),
    ("", "blank"),
    ("冷却机制：", "body"),
    ("  普通用户每5分钟一次，超级用户无限制", "cmd"),
    ("", "blank"),
    ("示例：", "body"),
    ('  /生图 一只戴帽子的猫', "cmd"),
    ('  /生图 赛博朋克城市 --width 1024 --height 768 --model dreamshaper', "cmd"),
    ('  /生图 山水画 --negative 模糊 --seed 42 --enhance', "cmd"),
]

def create_help_image():
    """生成帮助图片并保存，失败返回 False"""
    if FONT_BODY is None:
        logger.error("字体未加载，无法生成帮助图片")
        return False

    try:
        width = 960
        line_height = 36
        padding_top = 40
        padding_left = 50
        img_height = padding_top + len(HELP_LINES) * line_height + 40

        img = Image.new("RGB", (width, img_height), color=(25, 25, 35))
        draw = ImageDraw.Draw(img)

        y = padding_top
        for text, style in HELP_LINES:
            if style == "title":
                font = FONT_TITLE if FONT_TITLE else FONT_BODY
                color = (255, 215, 0)
            elif style == "cmd":
                font = FONT_BODY
                color = (100, 255, 150)
            elif style == "body":
                font = FONT_BODY
                color = (200, 200, 200)
            else:
                y += line_height
                continue

            draw.text((padding_left, y), text, fill=color, font=font)
            y += line_height

        img.save(HELP_IMAGE, format="PNG")
        logger.info(f"帮助图片已生成：{HELP_IMAGE}")
        return True

    except Exception as e:
        logger.error(f"生成帮助图片失败：{e}")
        return False

# 插件初始化：加载字体，需要时生成帮助图片
load_fonts()
if not HELP_IMAGE.exists():
    logger.info("帮助图片不存在，开始生成...")
    create_help_image()
else:
    logger.info("帮助图片已存在，跳过生成")

# ---------- 指令注册 ----------
img_gen = on_command("生图", aliases={"生成图片", "画图"}, priority=5, block=True)
help_cmd = on_command("生图帮助", aliases={"绘图帮助"}, priority=5, block=True)

# ---------- 帮助指令 ----------
@help_cmd.handle()
async def handle_help(event: MessageEvent):
    if HELP_IMAGE.exists():
        # 发送本地图片文件（OneBot V11 支持文件路径和 bytes）
        with open(HELP_IMAGE, "rb") as f:
            img_bytes = f.read()
        await help_cmd.finish(MessageSegment.image(img_bytes))
    else:
        # 降级为纯文本
        text_help = (
            "/生图 <提示词> [参数]\n"
            "参数：--width, --height, --model, --seed, --negative, "
            "--nologo, --enhance, --private\n"
            "示例：/生图 一只猫 --width 768 --height 768"
        )
        await help_cmd.finish(text_help)

# ---------- 参数解析 ----------
def parse_args(text: str):
    parts = text.split()
    prompt_parts = []
    options = {
        "width": 512,
        "height": 512,
        "model": "flux",
        "seed": None,
        "negative": None,
        "nologo": True,
        "enhance": False,
        "private": False
    }
    i = 0
    while i < len(parts):
        part = parts[i]
        if part.startswith("--"):
            key = part[2:].lower()
            if key in ("width", "height", "model", "seed", "negative"):
                if i + 1 < len(parts) and not parts[i+1].startswith("--"):
                    value = parts[i+1]
                    if key in ("width", "height"):
                        try:
                            options[key] = int(value)
                        except ValueError:
                            pass
                    elif key == "seed":
                        try:
                            options["seed"] = int(value)
                        except ValueError:
                            pass
                    elif key == "negative":
                        options["negative"] = value
                    elif key == "model":
                        options["model"] = value
                    i += 2
                    continue
                else:
                    i += 1
                    continue
            elif key == "nologo":
                options["nologo"] = True
            elif key == "enhance":
                options["enhance"] = True
            elif key == "private":
                options["private"] = True
            else:
                prompt_parts.append(part)
            i += 1
        else:
            prompt_parts.append(part)
            i += 1

    prompt = " ".join(prompt_parts)
    return prompt, options

def build_url(prompt: str, options: dict) -> str:
    encoded_prompt = quote(prompt, safe='')
    base = f"https://image.pollinations.ai/prompt/{encoded_prompt}"
    params = [
        f"key={KEY}",
        f"width={options['width']}",
        f"height={options['height']}",
        f"model={options['model']}"
    ]
    if options["seed"] is not None:
        params.append(f"seed={options['seed']}")
    if options["negative"]:
        params.append(f"negative={quote(options['negative'], safe='')}")
    if options["nologo"]:
        params.append("nologo=true")
    if options["enhance"]:
        params.append("enhance=true")
    if options["private"]:
        params.append("private=true")
    return base + "?" + "&".join(params)

# ---------- 主生图指令 ----------
@img_gen.handle()
async def handle_gen(event: MessageEvent, args: Message = CommandArg()):
    if not KEY:
        await img_gen.finish("图片生成服务暂不可用。")
    user_id = str(event.user_id)  # OneBot 事件中的 user_id
    superusers = [str(uid) for uid in config.superusers]  # 确保都是字符串
    is_superuser = user_id in superusers

    if not is_superuser:
        last_time = cooldown_map.get(user_id, 0)
        remaining = COOLDOWN_SECONDS - (time.time() - last_time)
        if remaining > 0:
            await img_gen.finish(f"冷却中，请等待 {int(remaining)} 秒后再试。")

    raw_text = args.extract_plain_text().strip()
    if not raw_text:
        await img_gen.finish("请提供提示词，发送 /生图帮助 查看用法")

    prompt, options = parse_args(raw_text)
    if not prompt:
        await img_gen.finish("提示词不能为空！")

    url = build_url(prompt, options)
    await img_gen.send("正在生成图片，请稍候...")

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                if not is_superuser:
                    cooldown_map[user_id] = time.time()
                await img_gen.finish(MessageSegment.image(resp.content))
            elif resp.status_code == 401:
                await img_gen.finish("Key无效")
            elif resp.status_code == 402:
                await img_gen.finish("余额不足")
            elif resp.status_code == 429:
                await img_gen.finish("请求频繁")
            else:
                await img_gen.finish(f"{resp.status_code}")
    except httpx.TimeoutException:
        await img_gen.finish("超时")
    except Exception as e:
        logger.error(f"生图异常：{e}")
        #await img_gen.finish("出错")
