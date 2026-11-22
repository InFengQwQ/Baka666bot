import asyncio
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageOps
import httpx
from pathlib import Path

# Fallback fonts just in case nonebot_plugin_osubot isn't available
import nonebot
from importlib.util import find_spec
_spec = find_spec("nonebot_plugin_osubot")
plugin_dir = (Path(_spec.origin).parent / "nonebot_plugin_osubot" if _spec.origin.endswith(".pyd") else Path(_spec.origin).parent) if _spec and _spec.origin else Path(__file__).parent
font_dir = plugin_dir / "osufile" / "fonts"

if font_dir.exists():
    Torus_Regular_20 = ImageFont.truetype(str(font_dir / "Torus Regular.otf"), 20)
    Torus_SemiBold_25 = ImageFont.truetype(str(font_dir / "Torus SemiBold.otf"), 25)
    Torus_Regular_25 = ImageFont.truetype(str(font_dir / "Torus Regular.otf"), 25)
else:
    # Use default windows fonts if not found
    try:
        Torus_Regular_20 = ImageFont.truetype("msyh.ttc", 20)
        Torus_SemiBold_25 = ImageFont.truetype("msyh.ttc", 25)
        Torus_Regular_25 = ImageFont.truetype("msyh.ttc", 25)
    except:
        Torus_Regular_20 = ImageFont.load_default()
        Torus_SemiBold_25 = ImageFont.load_default()
        Torus_Regular_25 = ImageFont.load_default()

def draw_fillet(img, radii):
    # 画圆（用于分离4个角）
    circle = Image.new("L", (radii * 2, radii * 2), 0)
    draw = ImageDraw.Draw(circle)
    draw.ellipse((0, 0, radii * 2, radii * 2), fill=255)
    # 原图
    img = img.convert("RGBA")
    w, h = img.size
    # 画4个角
    alpha = Image.new("L", img.size, 255)
    alpha.paste(circle.crop((0, 0, radii, radii)), (0, 0))
    alpha.paste(circle.crop((radii, 0, radii * 2, radii)), (w - radii, 0))
    alpha.paste(circle.crop((radii, radii, radii * 2, radii * 2)), (w - radii, h - radii))
    alpha.paste(circle.crop((0, radii, radii, radii * 2)), (0, h - radii))
    img.putalpha(alpha)
    return img

def draw_fillet2(img, radii):
    circle = Image.new("L", (radii * 2, radii * 2), 0)
    draw = ImageDraw.Draw(circle)
    draw.ellipse((0, 0, radii * 2, radii * 2), fill=255)
    img = img.convert("RGBA")
    w, h = img.size
    
    # 变暗
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(0.5)
    
    # 画4个角
    alpha = Image.new("L", img.size, 255)
    alpha.paste(circle.crop((0, 0, radii, radii)), (0, 0))
    alpha.paste(circle.crop((radii, 0, radii * 2, radii)), (w - radii, 0))
    alpha.paste(circle.crop((radii, radii, radii * 2, radii * 2)), (w - radii, h - radii))
    alpha.paste(circle.crop((0, radii, radii, radii * 2)), (0, h - radii))
    
    # 模糊
    img = img.filter(ImageFilter.BoxBlur(radius=2))
    img.putalpha(alpha)
    return img

async def draw_malody_bp(uid: str, mode_name: str, records: list,
                        user_name: str = None, avatar_url: str = None,
                        rank_text: str = None, mode_stats: dict = None,
                        precision: int = 2,
                        range_display: str = None) -> bytes:    # 新增
    bplist_len = len(records)
    total_mm = sum(bp.get('total', 0) for bp in records)
    total_mm_str = f"{total_mm:.{precision}f}"
    im = Image.new('RGBA', (1420, 280 + 177 * ((bplist_len + 1) // 2 - 1) if bplist_len > 0 else 280), (31, 41, 46, 255))
    
    bg_path = plugin_dir / "osufile" / "work" / "bg.jpg"
    if bg_path.exists():
        bg = Image.open(str(bg_path)).convert("RGBA")
        im.alpha_composite(bg.resize(im.size))
    
    draw = ImageDraw.Draw(im)
    f_div = Image.new('RGBA', (1450, 2), (255, 255, 255, 255)).convert('RGBA')
    im.alpha_composite(f_div, (0, 100))
    
    title_text = f'Malody {mode_name} | {range_display}' if range_display else f'Malody {mode_name} | Best'
    draw.text((1388, 80), title_text, font=Torus_SemiBold_25, anchor='rm')
    
    # 绘制用户信息
    next_y = 20
    if user_name:
        draw.text((115, next_y), user_name, font=Torus_Regular_25, anchor="lm")
        next_y += 30
    draw.text((115, next_y), f"UID: {uid}", font=Torus_SemiBold_25, anchor="lm")
    next_y += 30
    if rank_text:
        draw.text((115, next_y), rank_text, font=Torus_Regular_25, anchor="lm")
        next_y += 30

        # 如果同时有 rank 和 mode_stats，把统计数据放在 rank 右侧同一行
    if rank_text and mode_stats:
        stats_line = (
            f"Exp.{mode_stats.get('exp','?')}  "
            f"Play:{mode_stats.get('playcount','?')}  "
            f"Acc:{mode_stats.get('acc','?')}  "
            f"Combo:{mode_stats.get('combo','?')}  "
            f"MM:{total_mm_str}"
        )
        # rank 绘制在 (115, rank_y) 处，右侧留出足够距离（示例 200px）
        draw.text((115 + 200, next_y - 30), stats_line, font=Torus_Regular_20, anchor="lm")
    elif mode_stats:
        # 如果没有 rank，则按原样放在下方
        stats_line = (
            f"Exp.{mode_stats.get('exp','?')}  "
            f"Play:{mode_stats.get('playcount','?')}  "
            f"Acc:{mode_stats.get('acc','?')}  "
            f"Combo:{mode_stats.get('combo','?')}  "
            f"MM:{total_mm_str}"
        )
        draw.text((115, next_y), stats_line, font=Torus_Regular_20, anchor="lm")

    async with httpx.AsyncClient(verify=False) as client:
        if avatar_url:
            try:
                resp_av = await client.get(avatar_url, timeout=5.0)
                if resp_av.status_code == 200:
                    avatar = Image.open(BytesIO(resp_av.content)).convert("RGBA")
                    avatar = avatar.resize((75, 75))
                    avatar_fillet = draw_fillet(avatar, 15)
                    im.alpha_composite(avatar_fillet, (30, 10))
            except Exception:
                pass

        for num, bp in enumerate(records):
            h_num = 177 * (num // 2)
            offset = 695 * (num % 2)
            
            draw.text((40 + offset, 190 + h_num), str(num + 1), font=Torus_Regular_20, anchor='rm')
            
            sid = bp.get('sid')
            try:
                if sid:
                    resp = await client.get(f"http://cni.machart.top/cover/{sid}!small", timeout=5.0)
                    if resp.status_code == 200:
                        original_cover = Image.open(BytesIO(resp.content)).convert('RGBA')
                        
                        # 制作模糊背景 (不拉伸)
                        banner = ImageOps.fit(original_cover, (650, 150), Image.Resampling.LANCZOS)
                        banner_with_fillet = draw_fillet2(banner, 15)
                        im.alpha_composite(banner_with_fillet, (45 + offset, 114 + h_num))
                        
                        # 在左边放一个 150x150 的不拉伸正方形
                        bg_imag_raw = ImageOps.fit(original_cover, (150, 150), Image.Resampling.LANCZOS)
                        bg_imag = draw_fillet(bg_imag_raw, 15)
                        im.alpha_composite(bg_imag, (45 + offset, 114 + h_num))
            except Exception:
                pass
                
            metadata = f"{bp.get('title', 'Unknown')}"
            if len(metadata) > 30:
                metadata = metadata[:27] + "..."
            draw.text((210 + offset, 135 + h_num), metadata, font=Torus_Regular_25, anchor='lm')
            
            draw.text((210 + offset, 168 + h_num), bp.get('version', 'Unknown')[:30], font=Torus_Regular_20, anchor='lm', fill=(238, 171, 0, 255))
            score = bp.get('total', 0)
            
            # MM 和 MM 值对齐，使用底边基线对齐
            draw.text((645 + offset, 185 + h_num), f"{score:.{precision}f}", font=Torus_SemiBold_25, anchor='rs', fill=(255, 102, 171, 255))
            draw.text((648 + offset, 185 + h_num), 'MM', font=Torus_SemiBold_25, anchor='ls', fill=(209, 148, 176, 255))
            
            # SID 和 CID 放在卡片右下角
            draw.text((680 + offset, 245 + h_num), f"SID:{bp.get('sid', 'Unk')} CID:{bp.get('cid', 'Unk')}", font=Torus_Regular_20, anchor='rm')

    bio = BytesIO()
    im.convert('RGB').save(bio, "JPEG", quality=85)
    return bio.getvalue()
