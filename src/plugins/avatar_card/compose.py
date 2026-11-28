"""Club-card avatar: one artwork in, one composed card out."""

import colorsys
import hashlib
from functools import cache, lru_cache
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .matting import cutout

CANVAS = 1024
MARGIN = 24
TICK_X = MARGIN + 42
TICK_HALF = 5
TEXT_X = TICK_X + 22
GAP = 16  # vertical space between two type blocks
TYPE_BASE = 40  # last baseline distance above the margin

LABEL_SIZE = 22
LABEL_TRACKING = 14
NAME_SIZE = 146
NAME_WIDTH = 880
NAME_TRACKING = 3
NAME_TRAIL = 42
TRAIL_GAP = 11  # keeps the streak out of the glyph counters
TITLE_SIZE = 38
TITLE_WIDTH = 560
TITLE_TRACKING = 5
TITLE_TRAIL = 16
BRAND = "NYANMUSHI"
BRAND_SIZE = 26
BRAND_TRACKING = 14
MASK_PAD = 48  # room for shadow and trail

OUTLINE = 4  # rim width on the full canvas
RIM_SCALE = 4  # the rim is drawn this much larger, then boxed down
CUT = 63  # alpha below this is matte noise
FLOOR = 128  # kept alpha starts at half coverage
FAINT = 31  # ceiling for the band under the cut
INK = 1000  # kept pixels below this mean the matte found nobody

PLUGINS = Path(__file__).resolve().parents[1]
DISPLAY_FONT = (
    PLUGINS / "nonebot-plugin-for-osumania4k" / "nonebot_plugin_rework" / "tosu_plugin" / "styles"
    / "fonts" / "Torus-Bold.otf"
)


class NoSubject(Exception):
    pass


class Card:

    def __init__(self, source: Image.Image, name: str, title: str, size: int) -> None:
        self.name = name.strip().upper()
        self.title = title.strip().upper()
        self.size = size
        self.subject = cutout(_cover_crop(source.convert("RGB"), CANVAS))
        if _opaque_pixels(self.subject.getchannel("A")) < INK:
            raise NoSubject
        self.accent = _accent(self.subject)
        self.seed = int(hashlib.sha1(f"{name}|{title}".encode()).hexdigest()[:8], 16)

    def render(self) -> bytes:
        card = _backdrop(self.accent, self.seed)
        self._paint_subject(card)
        card.alpha_composite(_scrim())
        self._paint_type(card)
        if self.size != CANVAS:
            card = card.resize((max(1, self.size), max(1, self.size)), Image.LANCZOS)
        card.alpha_composite(_frame(self.size))  # after the resize, or the rule greys out
        return _encode(card)

    def _paint_subject(self, card: Image.Image) -> None:
        art = self.subject.crop(self.subject.getchannel("A").getbbox())
        if max(art.size) != CANVAS:
            scale = CANVAS / max(art.size)
            art = art.resize((max(1, round(art.width * scale)), max(1, round(art.height * scale))), Image.LANCZOS)
        soft = _matte(art.getchannel("A"))
        alpha = _lift(soft)
        art.putalpha(alpha)
        art = ImageEnhance.Contrast(ImageEnhance.Color(art).enhance(1.28)).enhance(1.10)

        left = (CANVAS - art.width) // 2
        top = (CANVAS - art.height) // 2
        card.alpha_composite(_glow(alpha, self.accent), (left, top))
        card.alpha_composite(_solid(art.size, (255, 255, 255), _plate(soft)), (left, top))
        card.alpha_composite(art, (left, top))

    def _paint_type(self, card: Image.Image) -> None:
        bottom = CANVAS - MARGIN - TYPE_BASE
        if self.title:
            font = _fit_font(self.title, TITLE_SIZE, TITLE_WIDTH, TITLE_TRACKING)
            bottom, _ = _paint_line(
                card, self.title, TEXT_X, bottom, font, TITLE_TRACKING,
                alpha=232, trail=TITLE_TRAIL, shadow=6,
            )
            bottom = _paint_label(card, "RANK", bottom - GAP, 200)

        font = _fit_font(self.name, NAME_SIZE, NAME_WIDTH, NAME_TRACKING)
        bottom, _ = _paint_line(
            card, self.name, TEXT_X, bottom - GAP, font, NAME_TRACKING,
            alpha=255, trail=NAME_TRAIL, shadow=18, tint=_saturate(self.accent, 0.25),
        )
        _paint_label(card, "PLAYER", bottom - GAP, 210)
        _paint_brand(card)


def render_card(source: Image.Image, name: str, title: str, size: int) -> bytes:
    return Card(source, name, title, size).render()


def _cover_crop(image: Image.Image, size: int) -> Image.Image:
    """Cover-crop, keeping the upper part of tall artwork where heads live."""
    scale = max(size / image.width, size / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left = (resized.width - size) // 2
    top = round((resized.height - size) * 0.25)
    return resized.crop((left, top, left + size, top + size))


def _matte(raw: Image.Image) -> Image.Image:
    """Blur across the cut, so the model's own jitter reads as one soft edge."""
    return raw.filter(ImageFilter.GaussianBlur(2))


def _lift(soft: Image.Image) -> Image.Image:
    """Keep translucent parts visible: anything kept reads at least half solid."""
    a = np.asarray(soft, np.float32)
    lifted = np.where(a > CUT, FLOOR + (a - CUT) * (255 - FLOOR) / (255 - CUT), a * FAINT / CUT)
    return Image.fromarray(lifted.astype(np.uint8), "L")


def _opaque_pixels(alpha: Image.Image) -> int:
    return sum(alpha.histogram()[CUT + 1:])


def _plate(soft: Image.Image) -> Image.Image:
    """White under the art: everything kept, plus the rim traced on the same cut."""
    solid = (np.asarray(soft) > CUT).astype(np.uint8) * 255
    return ImageChops.lighter(Image.fromarray(solid, "L"), _stroke(_contour(soft), soft.size))


def _contour(alpha: Image.Image) -> np.ndarray:
    """One point per cell on the cut line, interpolated between pixels."""
    field = np.asarray(alpha, dtype=np.float32) / 255
    level = CUT / 255
    rows, cols = field.shape[0] - 1, field.shape[1] - 1
    yy, xx = np.indices((rows, cols), dtype=np.float32)
    xs = np.zeros((rows, cols), np.float32)
    ys = np.zeros((rows, cols), np.float32)
    hits = np.zeros((rows, cols), np.uint8)

    edges = (
        (field[:-1, :-1], field[:-1, 1:], xx, yy, True),
        (field[1:, :-1], field[1:, 1:], xx, yy + 1, True),
        (field[:-1, :-1], field[1:, :-1], xx, yy, False),
        (field[:-1, 1:], field[1:, 1:], xx + 1, yy, False),
    )
    for near, far, x, y, horizontal in edges:
        crosses = (near < level) != (far < level)
        t = np.divide(level - near, far - near, out=np.full_like(near, 0.5), where=far != near)
        xs += np.where(crosses, x + t, 0) if horizontal else np.where(crosses, x, 0)
        ys += np.where(crosses, y, 0) if horizontal else np.where(crosses, y + t, 0)
        hits += crosses

    kept = hits == 2  # four crossings are a saddle; the neighbouring discs cover it
    return np.stack((xs[kept] / 2, ys[kept] / 2), axis=1)


def _stroke(points: np.ndarray, size: tuple[int, int]) -> Image.Image:
    """Round brush along the contour: one width all the way, tips included."""
    big = Image.new("L", (size[0] * RIM_SCALE, size[1] * RIM_SCALE), 0)
    brush = ImageDraw.Draw(big)
    radius = OUTLINE * RIM_SCALE
    for x, y in points:
        cx, cy = x * RIM_SCALE, y * RIM_SCALE
        brush.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=255)
    return big.resize(size, Image.BOX)


def _glow(alpha: Image.Image, accent) -> Image.Image:
    halo = alpha.resize((max(1, alpha.width // 4), max(1, alpha.height // 4)), Image.BILINEAR)
    halo = halo.filter(ImageFilter.GaussianBlur(14)).resize(alpha.size, Image.BILINEAR)
    return _solid(alpha.size, _saturate(accent, 0.35), halo.point(lambda value: value * 55 // 100))


def _solid(size: tuple[int, int], color, alpha: Image.Image) -> Image.Image:
    layer = Image.new("RGBA", size, tuple(color) + (0,))
    layer.putalpha(alpha)
    return layer


def _saturate(color, factor: float) -> tuple[int, int, int]:
    """Scale the saturation at full value, so the hue stays the character's."""
    h, s, _ = colorsys.rgb_to_hsv(*(c / 255 for c in color))
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, min(1.0, s * factor), 1.0))


def _accent(subject: Image.Image) -> tuple[int, int, int]:
    """The liveliest colour band of the subject, from a coarse RGB histogram."""
    small = np.asarray(subject.resize((128, 128), Image.BILINEAR))
    opaque = small[small[:, :, 3] >= 160][:, :3].astype(np.int16)
    if not len(opaque):  # kept pixels, but none solid enough to name a colour
        raise NoSubject

    step, bins = 24, 11
    ids = (opaque[:, 0] // step) * bins**2 + (opaque[:, 1] // step) * bins + opaque[:, 2] // step
    counts = np.bincount(ids, minlength=bins**3)
    sums = np.stack([np.bincount(ids, weights=opaque[:, i], minlength=bins**3) for i in range(3)], axis=1)

    present = counts > 0
    mean = sums[present] / counts[present, None]
    high, low = mean.max(axis=1), mean.min(axis=1)
    score = (high - low) / np.maximum(high, 1) * (0.35 + high / 255) * counts[present] ** 0.35
    r, g, b = mean[int(np.argmax(score))]
    return int(r), int(g), int(b)


@cache
def _mesh() -> tuple[np.ndarray, np.ndarray]:
    yy, xx = np.mgrid[0:CANVAS, 0:CANVAS].astype(np.float32)
    return yy, xx


@cache
def _aura() -> np.ndarray:
    yy, xx = _mesh()
    pool = np.sqrt(((xx - CANVAS * 0.5) / (CANVAS * 0.60)) ** 2 + ((yy - CANVAS * 0.22) / (CANVAS * 0.50)) ** 2)
    return np.clip(1 - pool, 0, 1) ** 2 * 0.60


@cache
def _vignette() -> np.ndarray:
    yy, xx = _mesh()
    pool = np.sqrt(((xx - CANVAS / 2) / (CANVAS * 0.85)) ** 2 + ((yy - CANVAS * 0.42) / (CANVAS * 0.85)) ** 2)
    return 0.25 * np.clip(pool, 0, 1) ** 2


@cache
def _scrim() -> Image.Image:
    """A soft pool in the type corner so white glyphs hold on pale artwork."""
    yy, xx = _mesh()
    pool = np.sqrt(((xx - CANVAS * 0.30) / (CANVAS * 0.62)) ** 2 + ((yy - CANVAS * 0.94) / (CANVAS * 0.54)) ** 2)
    alpha = np.clip(1 - pool, 0, 1) ** 1.4 * 170
    alpha += np.clip((yy / CANVAS - 0.72) / 0.28, 0, 1) ** 2 * 45
    return _solid((CANVAS, CANVAS), (0, 0, 0), Image.fromarray(np.clip(alpha, 0, 190).astype(np.uint8), "L"))


def _backdrop(accent, seed: int) -> Image.Image:
    h, _, _ = colorsys.rgb_to_hsv(*(c / 255 for c in accent))
    rng = np.random.default_rng(seed)

    top = np.array(colorsys.hsv_to_rgb(h, 0.55, 0.97), dtype=np.float32) * 255
    bottom = np.array(colorsys.hsv_to_rgb(h, 0.85, 0.60), dtype=np.float32) * 255
    ramp = np.linspace(0.0, 1.0, CANVAS, dtype=np.float32)[:, None]
    column = (top * (1 - ramp) + bottom * ramp).astype(np.uint8)[:, None, :]
    field = Image.fromarray(column, "RGB").resize((CANVAS, CANVAS), Image.NEAREST).convert("RGBA")

    # clouds are soft: paint them small and scale up
    small = 384
    clouds = Image.new("RGBA", (small, small), (0, 0, 0, 0))
    for _ in range(20):
        radius = int(rng.integers(34, 110))
        side = radius * 4
        light = rng.random() < 0.6
        tint = np.array(colorsys.hsv_to_rgb(h, 0.25 if light else 0.90, 1.0 if light else 0.55), dtype=np.float32) * 255
        tile = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        center = side / 2
        ImageDraw.Draw(tile).ellipse(
            (center - radius, center - radius, center + radius, center + radius),
            fill=tuple(tint.astype(int).tolist()) + (int(rng.integers(30, 70)),),
        )
        clouds.alpha_composite(
            tile.filter(ImageFilter.GaussianBlur(radius * 0.45)),
            (int(rng.integers(-radius * 2, small - radius)), int(rng.integers(-radius * 2, small - radius))),
        )
    field.alpha_composite(clouds.resize((CANVAS, CANVAS), Image.BILINEAR))

    tone = tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, 0.12, 1.0))
    field.alpha_composite(_solid((CANVAS, CANVAS), tone, Image.fromarray((_aura() * 255).astype(np.uint8), "L")))
    field.alpha_composite(_solid((CANVAS, CANVAS), (0, 0, 0), Image.fromarray((_vignette() * 255).astype(np.uint8), "L")))

    arr = np.asarray(field.convert("RGB"), dtype=np.int16)
    arr += rng.normal(0.0, 2.6, (CANVAS, CANVAS, 1)).astype(np.int16)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


@lru_cache(maxsize=8)
def _frame(size: int) -> Image.Image:
    """Rule and its glow in one layer."""
    scale = size / CANVAS
    margin = max(1, round(MARGIN * scale))
    inner = margin + max(1, round(10 * scale))
    if size < 2 * inner + 1:  # too small for the rule
        return Image.new("RGBA", (size, size), (255, 255, 255, 0))
    ink = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(ink)
    draw.rectangle((margin, margin, size - margin - 1, size - margin - 1), outline=(26, 12, 8, 70), width=1)
    draw.rectangle(
        (margin + 1, margin + 1, size - margin - 2, size - margin - 2),
        outline=(255, 255, 255, 240), width=max(1, round(2 * scale)),
    )
    draw.rectangle((inner, inner, size - inner - 1, size - inner - 1), outline=(255, 255, 255, 84), width=1)
    layer = ink.filter(ImageFilter.GaussianBlur(max(1, round(5 * scale))))
    layer.alpha_composite(ink)
    return layer


@lru_cache(maxsize=64)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(DISPLAY_FONT), size)


def _line_width(text: str, font, tracking: int) -> float:
    return sum(font.getlength(char) for char in text) + tracking * max(0, len(text) - 1)


def _line_mask(text: str, font, tracking: int) -> Image.Image:
    """Glyphs at their own spacing, padded with room for shadow and trail."""
    raw = Image.new("L", (int(_line_width(text, font, tracking)) + 16, int(font.size * 2.4)), 0)
    draw = ImageDraw.Draw(raw)
    x = 8
    for char in text:
        draw.text((x, font.size * 1.15), char, 255, font=font, anchor="ls")
        x += font.getlength(char) + tracking

    ink = raw.crop(raw.getbbox())
    mask = Image.new("L", (ink.width + 2 * MASK_PAD, ink.height + 2 * MASK_PAD), 0)
    mask.paste(ink, (MASK_PAD, MASK_PAD))
    return mask


def _fit_font(text: str, max_size: int, max_width: int, tracking: int) -> ImageFont.FreeTypeFont:
    size = max_size
    while _line_width(text, _font(size), tracking) > max_width:
        size -= 3
    return _font(size)


def _paint_line(card: Image.Image, text: str, x: int, bottom: int, font, tracking: int,
                alpha: int = 255, trail: int = 0, shadow: int = 0,
                tint: tuple[int, int, int] | None = None) -> tuple[int, Image.Image]:
    mask = _line_mask(text, font, tracking)
    top = bottom - (mask.height - 2 * MASK_PAD)
    x -= MASK_PAD
    y = top - MASK_PAD

    if shadow:
        soft = mask.filter(ImageFilter.GaussianBlur(shadow)).point(lambda value: value * 55 // 100)
        card.alpha_composite(_solid(mask.size, (14, 5, 2), soft), (x, y + 9))

    if trail:
        spill = ImageChops.subtract(_motion_trail(mask, trail), mask.filter(ImageFilter.MaxFilter(TRAIL_GAP)))
        spill = ImageChops.multiply(spill, _stripes(mask.size, max(5, round(font.size / 20))))
        ink = _solid(mask.size, (255, 255, 255), spill.point(lambda value: value * alpha // 255 * 70 // 100))
        card.alpha_composite(ink, (x, y))

    stencil = mask.point(lambda value: value * alpha // 255)
    if tint:
        ramp = np.linspace(0.0, 0.10, mask.height, dtype=np.float32)[:, None]
        tone = np.array(tint, dtype=np.float32)[None, :]
        column = (1 - ramp) * 255 + ramp * tone
        gradient = Image.fromarray(np.repeat(column[:, None, :], mask.width, axis=1).astype(np.uint8), "RGB")
        card.paste(gradient, (x, y), stencil)
    else:
        card.alpha_composite(_solid(mask.size, (255, 255, 255), stencil), (x, y))
    return top, mask


def _paint_label(card: Image.Image, text: str, bottom: int, alpha: int) -> int:
    """Label and tick; the tick takes its density from the label's own ink."""
    top, mask = _paint_line(card, text, TEXT_X, bottom, _font(LABEL_SIZE), LABEL_TRACKING, alpha=alpha)
    ink = np.asarray(mask.point(lambda value: value * alpha // 255))
    tone = int(np.percentile(ink[ink > 0], 75))
    tick = Image.new("L", (2 * TICK_HALF, 2 * TICK_HALF + 1), 0)
    ImageDraw.Draw(tick).polygon(
        [(0, 0), (0, 2 * TICK_HALF), (2 * TICK_HALF - 1, TICK_HALF)], fill=tone,
    )
    centre = top + (mask.height - 2 * MASK_PAD) // 2
    card.alpha_composite(_solid(tick.size, (255, 255, 255), tick), (TICK_X, centre - TICK_HALF))
    return top


def _paint_brand(card: Image.Image) -> None:
    mask = _line_mask(BRAND, _font(BRAND_SIZE), BRAND_TRACKING).rotate(-90, expand=True)
    body = _solid(mask.size, (255, 255, 255), mask.point(lambda value: value * 78 // 100))
    right = CANVAS - MARGIN - BRAND_SIZE
    card.alpha_composite(body, (right - body.width + MASK_PAD, MARGIN + 56 - MASK_PAD))


def _stripes(size: tuple[int, int], period: int) -> Image.Image:
    stripes = Image.new("L", size, 0)
    draw = ImageDraw.Draw(stripes)
    for y in range(0, size[1], period):
        draw.rectangle((0, y, size[0], y + max(1, period // 2)), fill=255)
    return stripes


def _motion_trail(mask: Image.Image, reach: int) -> Image.Image:
    """Rightward motion trail: each row keeps a fading copy of the pixels left of it."""
    trail = np.asarray(mask, dtype=np.float32).copy()
    covered, step = 0, 1
    while covered < reach:
        shift = min(step, reach - covered)
        shifted = np.zeros_like(trail)
        shifted[:, shift:] = trail[:, :-shift] * 0.95**shift
        np.maximum(trail, shifted, out=trail)
        covered += shift
        step *= 2
    return Image.fromarray(trail.astype(np.uint8), "L")


def _encode(card: Image.Image) -> bytes:
    buffer = BytesIO()
    # the frame carries the maker mark, so skip the bot-wide watermark
    card.convert("RGB").save(buffer, format="PNG", compress_level=4, watermark=False)
    return buffer.getvalue()
