"""Link-preview images for darkwire.tech: public/og.png (static) and public/og.gif (the dot pulses).

    npm run og        (python scripts/make-og.py, from /web; needs Pillow)

Deterministic: same fonts in, same bytes out. Fonts come from the geist npm package in
node_modules, never the system. 1200x630, --bg, a red dot and the wordmark, a mono tagline,
the domain bottom-left. No border, gradient, glow or grid (CLAUDE.md Banned).

The GIF has 24 frames at 100ms (one 2.4s cycle, looping forever). Only the dot changes:
opacity 1.0 -> 0.35 -> 1.0 with a cosine ease, frame 1 at full opacity so platforms that show
only the first frame get the lit dot. Palette: 8 colors in every frame. The static artwork is
quantized once to 5 fixed colors so it stays byte-identical across frames; the dot gets 3
slots (full, 2/3 and 1/3 edge coverage) recolored per frame, which keeps its edge smooth.
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "node_modules" / "geist" / "dist" / "fonts"
SANS = FONTS / "geist-sans" / "Geist-Medium.ttf"
MONO = FONTS / "geist-mono" / "GeistMono-Regular.ttf"
OUT = ROOT / "public"

W, H = 1200, 630
GUTTER = 96
BG = (0x0A, 0x0A, 0x0A)  # --bg
FG = (0xF5, 0xF5, 0xF5)  # --fg
MUTED = (0x73, 0x73, 0x73)  # --muted
DIM = (0x52, 0x52, 0x52)  # --dim
RED = (0xDC, 0x26, 0x26)  # --critical

WORD_SIZE = 96
TRACKING = -0.02 * WORD_SIZE
TAG_SIZE = 22
DOMAIN_SIZE = 18
DOT = 28
DOT_GAP = 26  # dot to wordmark
TAG_GAP = 30  # wordmark to tagline
DOMAIN_BOTTOM = 64  # from the bottom edge to the domain's baseline area

FRAMES = 24
FRAME_MS = 100
LOW = 0.35
SS = 4  # supersampling for the dot's edge


def tracked(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font, fill, tracking: float) -> None:
    """Pillow has no letter-spacing: place each glyph at the prefix width plus tracking."""
    x, y = xy
    for i, ch in enumerate(text):
        draw.text((x + font.getlength(text[:i]) + tracking * i, y), ch, font=font, fill=fill)


def layout():
    word = ImageFont.truetype(str(SANS), WORD_SIZE)
    tag = ImageFont.truetype(str(MONO), TAG_SIZE)
    domain = ImageFont.truetype(str(MONO), DOMAIN_SIZE)

    # Vertical centering on the visible ink: wordmark top to tagline bottom.
    w_box = word.getbbox("darkwire")  # (x0, y0, x1, y1) relative to the draw origin
    t_box = tag.getbbox("live security news + CVEs")
    block = (w_box[3] - w_box[1]) + TAG_GAP + (t_box[3] - t_box[1])
    top = (H - block) / 2
    word_y = top - w_box[1]
    tag_y = top + (w_box[3] - w_box[1]) + TAG_GAP - t_box[1]

    text_x = GUTTER + DOT + DOT_GAP
    # The dot sits on the middle of the lowercase x-height, as in the nav's wordmark.
    x_box = word.getbbox("a")
    dot_cy = word_y + (x_box[1] + x_box[3]) / 2
    d_box = domain.getbbox("darkwire.tech")
    domain_y = H - DOMAIN_BOTTOM - d_box[3]
    return word, tag, domain, text_x, word_y, tag_y, dot_cy, domain_y


def static_art() -> tuple[Image.Image, tuple[float, float]]:
    """Everything but the dot, and the dot's center."""
    word, tag, domain, text_x, word_y, tag_y, dot_cy, domain_y = layout()
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    tracked(d, (text_x, word_y), "darkwire", word, FG, TRACKING)
    d.text((text_x, tag_y), "live security news + CVEs", font=tag, fill=MUTED)
    d.text((GUTTER, domain_y), "darkwire.tech", font=domain, fill=DIM)
    return img, (GUTTER + DOT / 2, dot_cy)


def dot_coverage(center: tuple[float, float]) -> Image.Image:
    """Antialiased coverage of the dot (L mode, 0-255), drawn at SS x and scaled down."""
    big = Image.new("L", (W * SS, H * SS), 0)
    cx, cy = center[0] * SS, center[1] * SS
    r = DOT / 2 * SS
    ImageDraw.Draw(big).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    return big.resize((W, H), Image.Resampling.BOX)


def blend(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=True))


def opacity(frame: int) -> float:
    """1.0 at frame 0, LOW at the middle of the cycle, cosine ease in and out."""
    return LOW + (1 - LOW) * (0.5 + 0.5 * math.cos(2 * math.pi * frame / FRAMES))


def make_png(art: Image.Image, coverage: Image.Image) -> Path:
    img = Image.composite(Image.new("RGB", (W, H), RED), art, coverage)
    path = OUT / "og.png"
    img.save(path, optimize=True)
    return path


def make_gif(art: Image.Image, coverage: Image.Image) -> Path:
    # Static artwork: 5 colors, once, so every frame shares the exact same pixels.
    base = art.quantize(colors=5, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    static_palette = base.getpalette()[: 5 * 3]
    # Dot pixels by coverage band: full (index 5), 2/3 (6), 1/3 (7); the faintest edge stays bg.
    levels = coverage.point(lambda v: 5 if v >= 213 else 6 if v >= 128 else 7 if v >= 43 else 0)
    mask = coverage.point(lambda v: 255 if v >= 43 else 0)
    # Merge on raw palette indices (base is 0-4, the dot 5-7), not on colors.
    index_data = bytes(
        lv if m else bi for bi, lv, m in zip(base.tobytes(), levels.tobytes(), mask.tobytes(), strict=True)
    )

    frames = []
    for i in range(FRAMES):
        a = opacity(i)
        dot = [blend(BG, RED, a * c) for c in (1.0, 2 / 3, 1 / 3)]
        frame = Image.frombytes("P", (W, H), index_data)
        frame.putpalette(static_palette + [v for rgb in dot for v in rgb])
        frames.append(frame)

    path = OUT / "og.gif"
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_MS,
        loop=0,
        disposal=1,
        optimize=True,
    )
    return path


def main() -> None:
    for font in (SANS, MONO):
        if not font.exists():
            raise SystemExit(f"missing {font}: run npm install in /web (geist is a devDependency)")
    art, center = static_art()
    coverage = dot_coverage(center)
    png = make_png(art, coverage)
    gif = make_gif(art, coverage)
    for p in (png, gif):
        print(f"{p.relative_to(ROOT)}: {p.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
