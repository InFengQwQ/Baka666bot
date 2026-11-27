"""Club-card avatar: one artwork in, one composed card out."""

import colorsys
import hashlib
from functools import lru_cache
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
MASK_PAD = 48  # room for shadow and trail

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

FILL = 1.0  # the cut-out spans the canvas
OUTLINE = 4
ALPHA_CUT = 63  # a quarter of the range; below it the matte is noise
ALPHA_FLOOR = 128  # kept alphas start on the upper half of the range
FAINT_TOP = 31  # ceiling for the band under the cut
MIN_INK = 1000  # kept pixels below this mean the matte found nobody
FADE = 4  # the haze reaches this far inside the cut
RIM_HAZE = 63  # its ceiling over the artwork, a quarter of white

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
        if _kept_pixels(self.subject) < MIN_INK:
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
        _paint_frame(card, self.size)  # painted after the resize, or the rule greys out
        return _encode(card)

    def _paint_subject(self, card: Image.Image) -> None:
        art = self.subject.crop(self.subject.getchannel("A").getbbox())
        scale = CANVAS * FILL / max(art.width, art.height)
        target = (max(1, round(art.width * scale)), max(1, round(art.height * scale)))
        if target != art.size:
            art = art.resize(target, Image.LANCZOS)
        art.putalpha(_matte(art.getchannel("A")))
        art = ImageEnhance.Color(art).enhance(1.28)
        art = ImageEnhance.Contrast(art).enhance(1.10)

        left = (CANVAS - art.width) // 2
        top = (CANVAS - art.height) // 2
        alpha = art.getchannel("A")

        halo = alpha.resize((max(1, art.width // 4), max(1, art.height // 4)), Image.BILINEAR)
        halo = halo.filter(ImageFilter.GaussianBlur(14)).resize(art.size, Image.BILINEAR)
        glow = _solid(art.size, _saturate(self.accent, 0.35), halo.point(lambda value: int(value * 0.55)))
        card.alpha_composite(glow, (left, top))

        keep = _keep_mask(alpha)
        base = _solid(art.size, (255, 255, 255), keep)
        card.alpha_composite(base, (left, top))
        card.alpha_composite(art, (left, top))

        rim = _solid(art.size, (255, 255, 255), _rim_mask(keep))
        card.alpha_composite(rim, (left, top))

    def _paint_type(self, card: Image.Image) -> None:
        top = CANVAS - MARGIN - 40
        if self.title:
            font = _fit_font(self.title, TITLE_SIZE, TITLE_WIDTH, TITLE_TRACKING)
            top, _ = _paint_line(card, self.title, font, TEXT_X, top, 232, TITLE_TRACKING, trail=TITLE_TRAIL, shadow=6)
            top = _paint_label(card, "RANK", top - 16, 200)

        font = _fit_font(self.name, NAME_SIZE, NAME_WIDTH, NAME_TRACKING)
        top, _ = _paint_line(
            card, self.name, font, TEXT_X, top - 16, 255, NAME_TRACKING,
            trail=NAME_TRAIL, shadow=18, tint=_saturate(self.accent, 0.25),
        )
        _paint_label(card, "PLAYER", top - 16, 210)
        _paint_brand(card)


def _paint_frame(card: Image.Image, size: int) -> None:
    ink, glow = _frame_layers(size)
    card.alpha_composite(glow)
    card.alpha_composite(ink)


def render_card(source: Image.Image, name: str, title: str, size: int) -> bytes:
    return Card(source, name, title, size).render()


def _encode(card: Image.Image) -> bytes:
    buffer = BytesIO()
    # the frame carries the maker mark, so skip the bot-wide watermark
    card.convert("RGB").save(buffer, format="PNG", compress_level=4, watermark=False)
    return buffer.getvalue()


def _cover_crop(image: Image.Image, size: int) -> Image.Image:
    """Cover-crop, keeping the upper part of tall artwork where heads live."""
    width, height = image.size
    scale = max(size / width, size / height)
    resized = image.resize((max(size, round(width * scale)), max(size, round(height * scale))), Image.LANCZOS)
    left = (resized.width - size) // 2
    top = round((resized.height - size) * 0.25)
    return resized.crop((left, top, left + size, top + size))


def _solid(size: tuple[int, int], color, alpha: Image.Image) -> Image.Image:
    layer = Image.new("RGBA", size, tuple(color) + (0,))
    layer.putalpha(alpha)
    return layer


def _saturate(color, factor: float) -> tuple[int, int, int]:
    """Scale the saturation at full value, so the hue stays the character's."""
    h, s, _ = colorsys.rgb_to_hsv(*(c / 255 for c in color))
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, min(1.0, s * factor), 1.0))


def _accent(subject: Image.Image) -> tuple[int, int, int]:
    small = np.asarray(subject.convert("RGBA").resize((128, 128), Image.BILINEAR))
    opaque = small[small[:, :, 3] > 160][:, :3].astype(np.int16)
    if not len(opaque):  # kept pixels, but none solid enough to name a colour
        raise NoSubject
    ids = (opaque[:, 0] // 24) * 121 + (opaque[:, 1] // 24) * 11 + opaque[:, 2] // 24
    bins = 11**3
    counts = np.bincount(ids, minlength=bins)
    sums = np.stack([np.bincount(ids, weights=opaque[:, i], minlength=bins) for i in range(3)], axis=1)

    present = counts > 0
    mean = sums[present] / counts[present, None]
    high, low = mean.max(axis=1), mean.min(axis=1)
    score = (high - low) / np.maximum(high, 1) * (0.35 + high / 255) * counts[present] ** 0.35
    r, g, b = mean[int(np.argmax(score))]
    return int(r), int(g), int(b)


@lru_cache(maxsize=1)
def _aura_fields() -> tuple[np.ndarray, np.ndarray]:
    yy, xx = np.mgrid[0:CANVAS, 0:CANVAS].astype(np.float32)
    aura = np.sqrt(((xx - CANVAS * 0.5) / (CANVAS * 0.60)) ** 2 + ((yy - CANVAS * 0.22) / (CANVAS * 0.50)) ** 2)
    aura = (np.clip(1 - aura, 0, 1) ** 2 * 0.60)[..., None]
    vignette = np.sqrt(((xx - CANVAS / 2) / (CANVAS * 0.85)) ** 2 + ((yy - CANVAS * 0.42) / (CANVAS * 0.85)) ** 2)
    return aura, (0.25 * np.clip(vignette, 0, 1) ** 2)[..., None]


def _backdrop(accent, seed: int) -> Image.Image:
    h, _, _ = colorsys.rgb_to_hsv(*(c / 255 for c in accent))
    rng = np.random.default_rng(seed)

    top = np.array(colorsys.hsv_to_rgb(h, 0.55, 0.97), dtype=np.float32) * 255
    bottom = np.array(colorsys.hsv_to_rgb(h, 0.85, 0.60), dtype=np.float32) * 255
    ramp = np.linspace(0.0, 1.0, CANVAS, dtype=np.float32)[:, None]
    column = (top * (1 - ramp) + bottom * ramp).astype(np.uint8)[:, None, :]
    field = Image.fromarray(column, "RGB").resize((CANVAS, CANVAS), Image.NEAREST).convert("RGBA")

    # Clouds are soft: paint them small and scale up.
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

    aura, vignette = _aura_fields()
    tone = tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, 0.12, 1.0))
    glow = _solid((CANVAS, CANVAS), tone, Image.fromarray((aura[:, :, 0] * 255).astype(np.uint8), "L"))
    field.alpha_composite(glow)

    shade = _solid((CANVAS, CANVAS), (0, 0, 0), Image.fromarray((vignette[:, :, 0] * 255).astype(np.uint8), "L"))
    field.alpha_composite(shade)

    arr = np.asarray(field.convert("RGB"), dtype=np.int16)
    arr += rng.normal(0.0, 2.6, (CANVAS, CANVAS, 1)).astype(np.int16)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


@lru_cache(maxsize=1)
def _scrim() -> Image.Image:
    """A soft pool in the type corner so white glyphs hold on pale artwork."""
    yy, xx = np.mgrid[0:CANVAS, 0:CANVAS].astype(np.float32)
    pool = np.sqrt(((xx - CANVAS * 0.30) / (CANVAS * 0.62)) ** 2 + ((yy - CANVAS * 0.94) / (CANVAS * 0.54)) ** 2)
    alpha = np.clip(1 - pool, 0, 1) ** 1.4 * 170
    alpha += np.clip((yy / CANVAS - 0.72) / 0.28, 0, 1) ** 2 * 45
    return _solid((CANVAS, CANVAS), (0, 0, 0), Image.fromarray(np.clip(alpha, 0, 190).astype(np.uint8), "L"))


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    """Max over a disc, so a hard mask grows and a soft one keeps its ramp."""
    padded = np.pad(mask, radius)
    grown = padded.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                np.maximum(grown, np.roll(padded, (dy, dx), (0, 1)), out=grown)
    return grown[radius:-radius, radius:-radius]


def _kept_pixels(subject: Image.Image) -> int:
    return sum(subject.getchannel("A").histogram()[ALPHA_CUT + 1:])


def _remap_alpha(value: int) -> int:
    if value <= ALPHA_CUT:
        return value * FAINT_TOP // ALPHA_CUT
    return ALPHA_FLOOR + (value - ALPHA_CUT) * (255 - ALPHA_FLOOR) // (255 - ALPHA_CUT)


def _matte(alpha: Image.Image) -> Image.Image:
    """Blur before the cut, so jitter across a narrow band picks one side."""
    return alpha.filter(ImageFilter.GaussianBlur(2)).point(_remap_alpha)


def _keep_mask(alpha: Image.Image) -> Image.Image:
    """Full white on the kept pixels; both white layers share it."""
    return Image.fromarray((np.asarray(alpha) > ALPHA_CUT).astype(np.uint8) * 255, "L")


def _rim_mask(keep: Image.Image) -> Image.Image:
    """Solid one width outside the cut, a faint haze inside; painted over the artwork."""
    keep = np.asarray(keep)
    fade = (255 - _dilate(255 - keep, FADE)).astype(np.uint8)
    fade = np.asarray(Image.fromarray(fade, "L").filter(ImageFilter.GaussianBlur(FADE / 4)), dtype=np.int32)
    haze = RIM_HAZE * (255 - fade) // 255
    return Image.fromarray(np.where(keep > 0, haze, _dilate(keep, OUTLINE)).astype(np.uint8), "L")


@lru_cache(maxsize=8)
def _frame_layers(size: int) -> tuple[Image.Image, Image.Image]:
    scale = size / CANVAS
    margin = max(1, round(MARGIN * scale))
    inner = margin + max(1, round(10 * scale))
    if size < 2 * inner + 1:  # too small for the rule
        blank = Image.new("RGBA", (size, size), (255, 255, 255, 0))
        return blank, blank
    ink = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(ink)
    draw.rectangle((margin, margin, size - margin - 1, size - margin - 1), outline=(26, 12, 8, 70), width=1)
    draw.rectangle(
        (margin + 1, margin + 1, size - margin - 2, size - margin - 2),
        outline=(255, 255, 255, 240), width=max(1, round(2 * scale)),
    )
    draw.rectangle((inner, inner, size - inner - 1, size - inner - 1), outline=(255, 255, 255, 84), width=1)
    return ink, ink.filter(ImageFilter.GaussianBlur(max(1, round(5 * scale))))


@lru_cache(maxsize=64)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(DISPLAY_FONT), size)


def _line_width(text: str, font, tracking: int) -> float:
    return sum(font.getlength(char) for char in text) + tracking * max(0, len(text) - 1)


def _line_mask(text: str, font, tracking: int) -> Image.Image:
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


def _paint_line(card: Image.Image, text: str, font, x: int, bottom: int, opacity: int, tracking: int,
                trail: int = 0, shadow: int = 0, tint=None) -> tuple[int, Image.Image]:
    mask = _line_mask(text, font, tracking)
    height = mask.height - 2 * MASK_PAD
    top = bottom - height
    x -= MASK_PAD
    y = top - MASK_PAD

    if shadow:
        soft = mask.filter(ImageFilter.GaussianBlur(shadow)).point(lambda v: int(v * 0.55))
        card.alpha_composite(_solid(mask.size, (14, 5, 2), soft), (x, y + 9))

    if trail:
        spill = ImageChops.subtract(_motion_trail(mask, trail), mask.filter(ImageFilter.MaxFilter(TRAIL_GAP)))
        spill = ImageChops.multiply(spill, _stripe_mask(mask.size, max(5, round(font.size / 20))))
        ink = _solid(mask.size, (255, 255, 255), spill.point(lambda v: int(v * opacity / 255 * 0.70)))
        card.alpha_composite(ink, (x, y))

    stencil = mask.point(lambda v: v * opacity // 255)
    if tint:
        ramp = np.linspace(0.0, 0.10, mask.height, dtype=np.float32)[:, None]
        tone = np.array(tint, dtype=np.float32)[None, :]
        column = (1 - ramp) * 255 + ramp * tone
        grad = Image.fromarray(np.repeat(column[:, None, :], mask.width, axis=1).astype(np.uint8), "RGB")
        card.paste(grad, (x, y), stencil)
    else:
        card.alpha_composite(_solid(mask.size, (255, 255, 255), stencil), (x, y))
    return top, mask


def _paint_label(card: Image.Image, text: str, bottom: int, opacity: int) -> int:
    """Label and tick; the tick takes its density from the label's own ink."""
    label_top, mask = _paint_line(card, text, _font(LABEL_SIZE), TEXT_X, bottom, opacity, LABEL_TRACKING)
    ink = np.asarray(mask.point(lambda v: v * opacity // 255))
    tone = int(np.percentile(ink[ink > 0], 75))
    tick = Image.new("L", (2 * TICK_HALF, 2 * TICK_HALF + 1), 0)
    ImageDraw.Draw(tick).polygon(
        [(0, 0), (0, 2 * TICK_HALF), (2 * TICK_HALF - 1, TICK_HALF)], fill=tone,
    )
    centre = label_top + (mask.height - 2 * MASK_PAD) // 2
    card.alpha_composite(_solid(tick.size, (255, 255, 255), tick), (TICK_X, centre - TICK_HALF))
    return label_top


def _paint_brand(card: Image.Image) -> None:
    mask = _line_mask(BRAND, _font(BRAND_SIZE), BRAND_TRACKING).rotate(-90, expand=True)
    body = _solid(mask.size, (255, 255, 255), mask.point(lambda v: v * 0.78))
    right = CANVAS - MARGIN - BRAND_SIZE
    card.alpha_composite(body, (right - body.width + MASK_PAD, MARGIN + 56 - MASK_PAD))


def _stripe_mask(size: tuple[int, int], period: int) -> Image.Image:
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
