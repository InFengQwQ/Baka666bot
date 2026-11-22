from src.plugin_runtime import required_malody_account, malody_web_cookies
import re
from io import BytesIO
from typing import Optional
import html as html_module   # 避免与变量名冲突，实际可 import html

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.params import CommandArg

# ---------- 配置 ----------
from pathlib import Path

FONT_PATH = str(
    Path(__file__).parent / "fonts" / "Torus SemiBold.otf"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Referer": "https://m.mugzone.net/page/all/chart?type=3",
}

# 模式图标映射
MODE_NAMES = {
    0: "Key",
    1: "Step",
    2: "DJ",
    3: "Catch",
    4: "Pad",
    5: "Taiko",
    6: "Ring",
    7: "Slide",
}

# ---------- 网络请求 ----------
async def fetch_html(url: str) -> str:
    async with httpx.AsyncClient(headers=HEADERS, cookies=await malody_web_cookies(), verify=False, timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text

# ---------- 搜索 ----------
async def search_song(keyword: str) -> Optional[int]:
    """返回第一个匹配的 sid，找不到返回 None"""
    url = f"https://m.mugzone.net/page/search?keyword={keyword}"
    html = await fetch_html(url)

    # 提取第一个 <a class="textfix" href="/song/数字">
    match = re.search(r'<a\s+class="textfix"\s+href="/song/(\d+)"', html)
    if not match:
        return None
    return int(match.group(1))

# ---------- 歌曲详情解析 ----------
async def get_song_detail(sid: int) -> dict:
    url = f"https://m.mugzone.net/song/{sid}"
    html = await fetch_html(url)

    # 封面
    cover_match = re.search(r'background-image:url\(([^)]+)\)', html)
    cover_url = cover_match.group(1) if cover_match else ""

    # 标题和艺术家
    title_match = re.search(r'<h2 class="textfix title"><span class="textfix artist">(.+?)</span> - (.+?)</h2>', html)
    if title_match:
        artist = title_match.group(1).strip()
        title = title_match.group(2).strip()
    else:
        artist, title = "Unknown", "Unknown"

    # 元数据
    id_match = re.search(r'<label>ID</label>:s<span>(\d+)</span>', html)
    length_match = re.search(r'<label>Length</label>:<span>([^<]+)</span>', html)
    bpm_match = re.search(r'<label>BPM</label>:<span>([^<]+)</span>', html)
    update_match = re.search(r'<label>Last updated</label>:<span class="textfix">([^<]+)</span>', html)

    # 谱面列表
    charts = []
    items = re.finditer(r'<h2 class="item">(.*?)</h2>', html, re.DOTALL)
    for item in items:
        block = item.group(1)
        ver_match = re.search(r'<a href="/chart/(\d+)"[^>]*>(.*?)</a>', block)
        if not ver_match:
            continue
        cid = int(ver_match.group(1))
        version = ver_match.group(2).strip()

        mode_match = re.search(r'/static/img/mode/mode-(\d+)\.png', block)
        mode = int(mode_match.group(1)) if mode_match else 0

        cols = re.findall(r'<i class="col\d+">(.*?)</i>', block)
        chart_len = cols[0] if len(cols) > 0 else ""
        status = cols[1] if len(cols) > 1 else ""
        heat = cols[2] if len(cols) > 2 else ""
        creator_raw = cols[3] if len(cols) > 3 else ""
        last_update = cols[4] if len(cols) > 4 else ""

        creator_match = re.search(r'<a[^>]*>([^<]+)</a>', creator_raw)
        creator = creator_match.group(1) if creator_match else creator_raw

        # 谱面长度转分:秒
        chart_length_formatted = chart_len
        if chart_len.isdigit():
            total_sec = int(chart_len)
            mins = total_sec // 60
            secs = total_sec % 60
            chart_length_formatted = f"{mins}:{secs:02d}"

        charts.append({
            "cid": cid,
            "version": html_module.unescape(version),
            "mode": mode,
            "length": chart_length_formatted,
            "status": html_module.unescape(status),
            "heat": heat,
            "creator": html_module.unescape(creator),
            "last_update": last_update,
        })

    raw_length = html_module.unescape(length_match.group(1)) if length_match else ""
    # 将 "129s" 转为 mm:ss
    length_formatted = raw_length
    if raw_length.endswith("s"):
        try:
            total_sec = int(raw_length[:-1])
            mins = total_sec // 60
            secs = total_sec % 60
            length_formatted = f"{mins}:{secs:02d}"
        except:
            pass

    return {
        "sid": sid,
        "title": html_module.unescape(title),
        "artist": html_module.unescape(artist),
        "cover_url": cover_url,
        "length": length_formatted,
        "bpm": html_module.unescape(bpm_match.group(1)) if bpm_match else "",
        "last_update": html_module.unescape(update_match.group(1)) if update_match else "",
        "charts": charts,
    }

# ---------- 图片渲染 ----------
def load_font(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.truetype("msyh.ttc", size)

def hex_to_rgba(hex_color, alpha=255):
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return (r, g, b, alpha)

MODE_COLORS_V2 = {
    0: "#5B9BFF",
    1: "#FFA34D",
    2: "#FF65AE",
    3: "#3FD9A3",
    4: "#FFD166",
    5: "#F25F5C",
    6: "#B36BFF",
    7: "#00D4D4",
}

def create_cover_background(cover_img: Image.Image, target_size: tuple) -> Image.Image:
    tw, th = target_size
    cw, ch = cover_img.size
    ratio = max(tw / cw, th / ch)
    new_size = (int(cw * ratio), int(ch * ratio))
    cover_resized = cover_img.resize(new_size, Image.LANCZOS)
    left = (new_size[0] - tw) // 2
    top = (new_size[1] - th) // 2
    cover_cropped = cover_resized.crop((left, top, left + tw, top + th))
    return cover_cropped

async def render_song_image(data: dict) -> bytes:
    WIDTH = 1200
    MARGIN = 40
    CARD_RADIUS = 20

    COVER_SIZE = 200
    COVER_TOP = 60
    COVER_LEFT = MARGIN

    TEXT_X = COVER_LEFT + COVER_SIZE + 40
    TEXT_AREA_WIDTH = WIDTH - TEXT_X - MARGIN

    STAT_CARD_W = 140
    STAT_CARD_H = 70
    STAT_CARD_GAP = 24
    STAT_START_Y_OFFSET = -60

    CHART_CARD_H = 100
    CHART_CARD_GAP = 16
    CHART_Y_START = COVER_TOP + COVER_SIZE + 40

    font_title = load_font(60)
    font_artist = load_font(36)
    font_meta_label = load_font(22)
    font_meta_value = load_font(32)
    font_chart_title = load_font(30)
    font_chart_body = load_font(24)
    font_section_title = load_font(48)

    # 处理背景
    cover_img = None
    if data.get("cover_url"):
        try:
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.get(data["cover_url"], timeout=10)
                cover_img = Image.open(BytesIO(resp.content)).convert("RGBA")
        except Exception:
            pass

    chart_count = len(data["charts"])
    charts_total_height = chart_count * (CHART_CARD_H + CHART_CARD_GAP) if chart_count else 0
    total_height = CHART_Y_START + 40 + charts_total_height + 120

    if cover_img:
        bg = create_cover_background(cover_img, (WIDTH, total_height))
        bg = bg.filter(ImageFilter.GaussianBlur(60))
        overlay = Image.new("RGBA", (WIDTH, total_height), hex_to_rgba("#0a0a1a", 130))
        bg = Image.alpha_composite(bg.convert("RGBA"), overlay)
    else:
        bg = Image.new("RGBA", (WIDTH, total_height), hex_to_rgba("#12122A"))
    draw = ImageDraw.Draw(bg)

    # 封面阴影
    shadow_size = COVER_SIZE + 20
    shadow = Image.new("RGBA", (shadow_size, shadow_size), (0,0,0,0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (10, 10, COVER_SIZE+10, COVER_SIZE+10),
        radius=CARD_RADIUS,
        fill=(0,0,0,160)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    bg.alpha_composite(shadow, (COVER_LEFT, COVER_TOP))

    if cover_img:
        cover = cover_img.resize((COVER_SIZE, COVER_SIZE), Image.LANCZOS)
        mask = Image.new("L", (COVER_SIZE, COVER_SIZE), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0,0,COVER_SIZE,COVER_SIZE), radius=CARD_RADIUS, fill=255)
        cover.putalpha(mask)
        bg.alpha_composite(cover, (COVER_LEFT + 10, COVER_TOP + 10))

    # 标题
    title = data["title"]
    title_font = font_title
    while draw.textlength(title, font=title_font) > TEXT_AREA_WIDTH - 40:
        title_font = load_font(title_font.size - 2)
        if title_font.size < 30:
            break
    draw.text((TEXT_X, COVER_TOP + 10), title, font=title_font, fill="#FFFFFF")

    # 艺术家
    artist = data["artist"]
    draw.text((TEXT_X, COVER_TOP + 10 + title_font.size + 16), artist, font=font_artist, fill="#B0B5CC")

    # 统计卡片
    stats = [
        ("    BPM", data.get("bpm", "--")),
        ("  LENGTH", data.get("length", "--")),
        ("  CHARTS", str(chart_count)),
    ]
    stat_start_x = TEXT_X
    stat_start_y = COVER_TOP + COVER_SIZE + STAT_START_Y_OFFSET   # 封面下方 30px

    for i, (label, value) in enumerate(stats):
        sx = stat_start_x + i * (STAT_CARD_W + STAT_CARD_GAP)
        sy = stat_start_y

        draw.rounded_rectangle(
            (sx, sy, sx + STAT_CARD_W, sy + STAT_CARD_H),
            radius=14,
            fill=hex_to_rgba("#1E1E3A", 200),
            outline=hex_to_rgba("#3A3A5C", 120),
            width=1
        )
        draw.text((sx + 16, sy + 10), label, font=font_meta_label, fill="#8A8FA8")
        value_text = str(value)
        val_bbox = draw.textbbox((0,0), value_text, font=font_meta_value)
        val_w = val_bbox[2] - val_bbox[0]
        val_h = val_bbox[3] - val_bbox[1]
        # 垂直居中：卡片高度 - 上方标签高度，剩下区域用于数值
        label_area_bottom = sy + 10 + font_meta_label.size   # 标签文字的下边缘大致位置
        avail_h = (sy + STAT_CARD_H) - label_area_bottom
        text_y = label_area_bottom + (avail_h - val_h) // 2 - val_bbox[1]   # 减去 top 偏移，对齐视觉边界
        draw.text(
            (sx + (STAT_CARD_W - val_w) // 2, text_y),
            value_text,
            font=font_meta_value,
            fill="#FFFFFF"
        )

    # 谱面卡片
    heats = [int(c.get("heat", 0)) for c in data["charts"]]
    max_heat = max(heats) if heats else 1

    # ---------- 预计算最大文本宽度 ----------
    charts_list = data["charts"]
    mode_text_widths = []
    heat_text_widths = []
    for chart in charts_list:
        mode_name = MODE_NAMES.get(chart.get("mode", 0), "UNK")
        mw = draw.textbbox((0,0), mode_name, font=font_chart_body)
        mode_text_widths.append(mw[2] - mw[0])
        heat_str = str(chart.get("heat", 0))
        hw = draw.textbbox((0,0), heat_str, font=font_chart_body)
        heat_text_widths.append(hw[2] - hw[0])

    max_mode_w = max(mode_text_widths) if mode_text_widths else 70
    max_heat_w = max(heat_text_widths) if heat_text_widths else 30

    # 统一的背景框宽度（含内边距）
    pad_x = 12          # 模式标签左右内边距
    tag_pad_x = 8       # 热度标签左右内边距
    unified_block_w = max_mode_w + pad_x * 2
    unified_heat_tag_w = max_heat_w + tag_pad_x * 2
    tag_pad_y = 4       # 热度标签上下内边距
    y = CHART_Y_START
    for chart in data["charts"]:
        card_rect = (MARGIN, y, WIDTH - MARGIN, y + CHART_CARD_H)
        draw.rounded_rectangle(
            card_rect,
            radius=CARD_RADIUS,
            fill=hex_to_rgba("#1C1C36", 180),
            outline=hex_to_rgba("#3A3A5C", 100),
            width=1
        )

        mode = chart.get("mode", 0)
        mode_color = MODE_COLORS_V2.get(mode, "#888888")
        mode_name = MODE_NAMES.get(mode, "UNK")
        block_x = MARGIN + 20
        block_y = y + 20
        block_h = 30   # 高度保持30，宽度动态计算

        # 计算完整模式名的尺寸
        abbrev = mode_name   # 直接使用完整名称
        abbrev_bbox = draw.textbbox((0,0), abbrev, font=font_chart_body)
        abbrev_w = abbrev_bbox[2] - abbrev_bbox[0]
        abbrev_h = abbrev_bbox[3] - abbrev_bbox[1]
        pad_x = 12   # 左右内边距
        block_w = unified_block_w
        block_h = 30

        # 背景矩形
        draw.rounded_rectangle(
            (block_x, block_y, block_x + block_w, block_y + block_h),
            radius=8,
            fill=mode_color,
            outline=hex_to_rgba("#FFFFFF", 30),
            width=1
        )

        # 文字居中，同时减去 bbox 的 left/top 消除下沉
        abbrev = mode_name   # 完整模式名
        abbrev_bbox = draw.textbbox((0,0), abbrev, font=font_chart_body)
        abbrev_w = abbrev_bbox[2] - abbrev_bbox[0]
        abbrev_h = abbrev_bbox[3] - abbrev_bbox[1]
        text_x = block_x + (block_w - abbrev_w) // 2 - abbrev_bbox[0]
        text_y = block_y + (block_h - abbrev_h) // 2 - abbrev_bbox[1]
        draw.text((text_x, text_y), abbrev, font=font_chart_body, fill="#111122")

        version = chart.get("version", "")
        creator = chart.get("creator", "")
        cid = chart.get("cid", "")
        draw.text((block_x + block_w + 24, y + 12), version, font=font_chart_title, fill="#FFFFFF")
        # 显示 cid
        draw.text((block_x + block_w + 24, y + 48), f"by {creator}  |  cid:{cid}", font=font_chart_body, fill="#8A8FA8")

        length = chart.get("length", "")
        status = chart.get("status", "")
        info_text = f"{length}  |  {status}"
        info_bbox = draw.textbbox((0,0), info_text, font=font_chart_body)
        info_w = info_bbox[2] - info_bbox[0]
        # 向左移动 80 像素，给右侧热度条留出足够空间
        draw.text((WIDTH - MARGIN - info_w - 120, y + 15), info_text, font=font_chart_body, fill="#C0C5D8")

        heat = int(chart.get("heat", 0))
        bar_width = 150   # 略微缩短，为统一宽度留空间
        bar_x = WIDTH - MARGIN - bar_width - unified_heat_tag_w - 30  # 动态留出标签位置
        bar_y = y + 55
        draw.rounded_rectangle(
            (bar_x, bar_y, bar_x + bar_width, bar_y + 14),
            radius=7,
            fill=hex_to_rgba("#2A2A4A", 200)
        )
        fill_ratio = min(heat / max_heat, 1) if max_heat else 0
        if fill_ratio > 0:
            draw.rounded_rectangle(
                (bar_x, bar_y, bar_x + bar_width * fill_ratio, bar_y + 14),
                radius=7,
                fill=hex_to_rgba("#FF5E7A")
            )
        # 火焰色标签
        # 使用统一宽度
        heat_text = str(heat)
        heat_bbox = draw.textbbox((0,0), heat_text, font=font_chart_body)
        heat_text_w = heat_bbox[2] - heat_bbox[0]
        heat_text_h = heat_bbox[3] - heat_bbox[1]

        bg_w = unified_heat_tag_w
        bg_h = heat_text_h + tag_pad_y * 2

        tag_x = bar_x + bar_width + 12
        tag_y = bar_y - 4

        bg_x = tag_x
        bg_y = tag_y
        draw.rounded_rectangle(
            (bg_x, bg_y, bg_x + bg_w, bg_y + bg_h),
            radius=6,
            fill=hex_to_rgba("#FF5E3A", 220),
            outline=hex_to_rgba("#FF8A6A", 100),
            width=1
        )
        # 文字水平居中 + 修正下沉
        text_x = bg_x + (bg_w - heat_text_w) // 2 - heat_bbox[0]
        text_y = bg_y + tag_pad_y - heat_bbox[1]
        draw.text((text_x, text_y), heat_text, font=font_chart_body, fill="#FFFFFF")

        y += CHART_CARD_H + CHART_CARD_GAP

    buf = BytesIO()
    bg.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

# ---------- 命令响应 ----------
sm = on_command("sm", aliases={"搜歌"}, priority=5)

@sm.handle()
async def _(args: Message = CommandArg()):
    keyword = args.extract_plain_text().strip()
    if not keyword:
        await sm.finish("请提供歌曲关键词，例如：/sm Back! to the Future")

    # ----- 新增：识别直接输入的 sid -----
    sid_match = re.match(r'^[sS]\s*(\d+)$', keyword)
    if sid_match:
        sid = int(sid_match.group(1))
    else:
        sid = await search_song(keyword)
        if not sid:
            await sm.finish("未找到匹配的歌曲。")
    # -----------------------------------

    detail = await get_song_detail(sid)
    img_bytes = await render_song_image(detail)
    await sm.finish(MessageSegment.image(img_bytes))
