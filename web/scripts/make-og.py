"""Brand images for darkwire.tech, all from one design (the wordmark in components/Wordmark.tsx).

    npm run og        (python scripts/make-og.py, from /web; needs Pillow)

Writes:
- app/favicon.ico (16 + 32), app/icon.svg, app/apple-icon.png (180), public/icon-192.png,
  public/icon-512.png: a lowercase "d" in --fg and a block cursor (#5a5a5a) on black, drawn
  cell by cell on a 16 grid so 16 and 32 are crisp (no scaling, no antialiasing). The larger
  icons keep the mark inside the maskable safe zone. The unseen state (lib/unseen.ts) paints
  the cursor --critical on a canvas copy.
- public/og.png: the static lockup ("darkwire" with the red square, faint ".tech", the mono
  tagline right-aligned to the end of ".tech"), 1200x630.
- public/og.gif: frame 1 is that same static lockup (platforms that show one frame get the
  finished mark); then ".tech" fades out, types back in (each character a dim red binary digit
  that flips once, then fades to the character, a faint block cursor after it), the cursor
  and the square blink twice in sync, and it holds. One fixed 8-color palette for every frame,
  so unchanged pixels stay identical and the GIF stays small.

Deterministic: fonts come from the geist npm package in node_modules, never the system.
Wordmark numbers mirror WORDMARK in components/Wordmark.tsx; keep them in step.
"""

import math
import struct
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "node_modules" / "geist" / "dist" / "fonts"
SANS_BOLD = FONTS / "geist-sans" / "Geist-Bold.ttf"
MONO = FONTS / "geist-mono" / "GeistMono-Regular.ttf"
PUBLIC = ROOT / "public"
APP = ROOT / "app"

# Colors (globals.css tokens and the WORDMARK config).
BG = (0x0A, 0x0A, 0x0A)  # --bg
BLACK = (0, 0, 0)  # icon background
FG = (0xF5, 0xF5, 0xF5)  # --fg
MUTED = (0x8B, 0x8B, 0x8B)  # --muted (tagline)
RED = (0xDC, 0x26, 0x26)  # --critical (the square)
TECH = (0x4A, 0x4A, 0x4A)  # ".tech"
BINARY = (0x3D, 0x1A, 0x1A)  # a character before it resolves
CURSOR = (0x24, 0x24, 0x24)  # #4a4a4a at 40% over --bg
RED_MID = (0x8C, 0x1C, 0x1C)  # the square half way through a blink (palette slot for fades)

# Wordmark geometry, in em of the word's font size (WORDMARK in Wordmark.tsx).
WORD_TRACKING = -0.03
# The square is measured from the font itself (as Wordmark.tsx does in the browser): side =
# the ı stem's width, top on the ascender of "d" (never above), at least 1px above the stem.
TECH_SIZE = 0.55
TECH_TRACKING = -0.04  # of the tech font size
TECH_GAP = -0.05  # of the tech font size
CURSOR_W = 0.4  # of the tech font size
CURSOR_H = 0.53  # of the tech font size (mono x-height)
CURSOR_GAP = 0.06  # of the tech font size

# Timing (ms).
CHAR_MS, FLIP_MS, FADE_MS = 700, 175, 350
BLINK_MS, BLINK_COUNT, BLINK_LOW = 1800, 2, 0.25
FADE_OUT_MS, PAUSE_MS = 800, 300

W, H = 1200, 630
WORD_SIZE = 132
TAG_SIZE = 22
TAG_GAP = 34


# --------------------------------------------------------------------------- icons

# The favicon: a lowercase "d" and a block cursor, drawn cell by cell on a 16 grid so it is
# crisp at 16 and 32 (32 = each cell 2x2). Inclusive cell ranges (x0, y0, x1, y1).
D_STEM = (6, 2, 7, 14)
D_BOWL = (1, 5, 6, 14)  # 2-cell stroke, rounded by leaving its two left corners open
CURSOR_BLOCK = (10, 8, 13, 13)
ICON_CURSOR = (0x5A, 0x5A, 0x5A)  # normal; the unseen state paints it --critical (lib/unseen.ts)


def d_cells() -> set[tuple[int, int]]:
    cells = set()
    x0, y0, x1, y1 = D_STEM
    cells |= {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
    x0, y0, x1, y1 = D_BOWL
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            if x <= x0 + 1 or y <= y0 + 1 or y >= y1 - 1:  # left stroke, top and bottom strokes
                cells.add((x, y))
    cells -= {(x0, y0), (x0, y1)}  # round the bowl's left corners
    return cells


def draw_mark(im: Image.Image, ox: float, oy: float, u: float, cursor=ICON_CURSOR) -> None:
    """The mark with each 16-grid cell u pixels wide, its grid origin at (ox, oy)."""
    d = ImageDraw.Draw(im)
    box = lambda x0, y0, x1, y1: [round(ox + x0 * u), round(oy + y0 * u), round(ox + (x1 + 1) * u) - 1, round(oy + (y1 + 1) * u) - 1]
    for x, y in d_cells():
        d.rectangle(box(x, y, x, y), fill=FG)
    d.rectangle(box(*CURSOR_BLOCK), fill=cursor)


def grid_icon(size: int, cursor=ICON_CURSOR) -> Image.Image:
    """16 and 32: the grid at 1 or 2 pixels per cell, filling the icon."""
    im = Image.new("RGB", (size, size), BLACK)
    draw_mark(im, 0, 0, size / 16, cursor)
    return im


def safe_icon(size: int) -> Image.Image:
    """Larger icons: the mark (cells x 1-13, y 2-14) scaled into the central 60% (the maskable
    safe zone), centered, on whole pixels."""
    im = Image.new("RGB", (size, size), BLACK)
    u = round(size * 0.6 / 13)
    ox = round(size / 2 - 7.5 * u)  # mark center x = (1 + 14) / 2 = 7.5 cells
    oy = round(size / 2 - 8.5 * u)  # mark center y = (2 + 15) / 2 = 8.5 cells
    draw_mark(im, ox, oy, u)
    return im


def png_bytes(im: Image.Image) -> bytes:
    b = BytesIO()
    im.save(b, format="PNG", optimize=True)
    return b.getvalue()


def write_ico(path: Path, images: list[Image.Image]) -> None:
    """ICO with PNG entries, each drawn at its own size (no resampling)."""
    datas = [png_bytes(im.convert("RGBA")) for im in images]  # ICO readers want RGBA PNGs
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for im, data in zip(images, datas):
        w, h = im.size
        entries += struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.write_bytes(header + entries + b"".join(datas))


def icon_svg() -> str:
    """The 16 grid as SVG rects (crispEdges); browsers use it where they prefer SVG."""
    rects = "".join(f'<rect x="{x}" y="{y}" width="1" height="1" fill="#f5f5f5"/>' for x, y in sorted(d_cells()))
    x0, y0, x1, y1 = CURSOR_BLOCK
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">'
        '<rect width="16" height="16" fill="#000"/>'
        + rects
        + f'<rect x="{x0}" y="{y0}" width="{x1 - x0 + 1}" height="{y1 - y0 + 1}" fill="#5a5a5a"/>'
        "</svg>\n"
    )


# --------------------------------------------------------------------------- lockup

def tracked(draw, xy, text, font, fill, tracking):
    """Pillow has no letter-spacing: place each glyph at the prefix width plus tracking."""
    x, y = xy
    for i, ch in enumerate(text):
        draw.text((x + font.getlength(text[:i]) + tracking * i, y), ch, font=font, fill=fill)


def tracked_len(text, font, tracking):
    return font.getlength(text) + tracking * (len(text) - 1)


class Lockup:
    def __init__(self):
        self.word = ImageFont.truetype(str(SANS_BOLD), WORD_SIZE)
        self.tech_size = round(WORD_SIZE * TECH_SIZE)
        self.tech = ImageFont.truetype(str(MONO), self.tech_size)
        self.tag = ImageFont.truetype(str(MONO), TAG_SIZE)
        self.w_track = WORD_TRACKING * WORD_SIZE
        self.t_track = TECH_TRACKING * self.tech_size

        word_text = "darkwıre"
        self.word_text = word_text
        word_w = tracked_len(word_text, self.word, self.w_track)
        gap = TECH_GAP * self.tech_size
        self.tech_adv = self.tech.getlength("0") + self.t_track  # mono: one advance per cell
        tech_w = 5 * self.tech_adv
        # Center on the visible "darkwire.tech"; the cursor's space hangs past the "h".
        total = word_w + gap + tech_w

        ascent, _ = self.word.getmetrics()
        t_box = self.tag.getbbox("live security news + CVEs")
        w_top = self.word.getbbox("dk")[1]
        # Vertical centering on the ink: the square's top to the tagline's bottom.
        self.baseline_off = ascent  # draw origin to baseline
        square_top_rel = self._square_rect(0, 0)[1]  # relative to the draw origin
        ink_top = min(square_top_rel, w_top)
        word_bottom = ascent  # baseline
        tag_h = t_box[3] - t_box[1]
        block = (word_bottom - ink_top) + TAG_GAP + tag_h
        self.x0 = (W - total) / 2
        self.y0 = (H - block) / 2 - ink_top
        self.tech_x = self.x0 + word_w + gap
        # Baselines line up: the tech font's origin sits so its baseline matches the word's.
        self.tech_y = self.y0 + ascent - self.tech.getmetrics()[0]
        self.cursor_x = lambda n: self.tech_x + n * self.tech_adv + CURSOR_GAP * self.tech_size
        self.reserve_end = self.x0 + total
        self.tag_y = self.y0 + word_bottom + TAG_GAP - t_box[1]
        self.tag_x = self.reserve_end - self.tag.getlength("live security news + CVEs")

    def _square_rect(self, x0, y0):
        """The square over the ı from the font's own ink: side = stem width, top on the
        ascender of "d", at least 1px above the stem (the square gives up a pixel before it
        rises above the ascender)."""
        f = self.word
        stem_box = f.getbbox("ı")  # (x0, y0, x1, y1) from the draw origin
        asc_top = f.getbbox("d")[1]
        prefix = tracked_len("darkw", f, self.w_track) + self.w_track
        stem_w = stem_box[2] - stem_box[0]
        bottom = stem_box[1] - max(1, round(0.024 * WORD_SIZE))
        side = min(stem_w, bottom - asc_top)
        cx = prefix + (stem_box[0] + stem_box[2]) / 2
        left = round(x0 + cx - side / 2)
        top = round(y0 + bottom - side)
        return (left, top, left + side, top + side)

    def draw(self, typed=5, char_state=None, tech_alpha=1.0, cursor=None, square_alpha=1.0):
        """typed: characters fully shown; char_state: (index, digit, fade 0..1) for the one
        resolving; tech_alpha: whole ".tech" (fade-out); cursor: None or alpha."""
        im = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(im)
        tracked(d, (self.x0, self.y0), self.word_text, self.word, FG, self.w_track)
        sq = self._square_rect(self.x0, self.y0)
        d.rectangle([round(sq[0]), round(sq[1]), round(sq[2]) - 1, round(sq[3]) - 1], fill=mix(RED, BG, square_alpha))
        tech_color = mix(TECH, BG, tech_alpha)
        for i, ch in enumerate(".tech"[:typed]):
            d.text((self.tech_x + i * self.tech_adv, self.tech_y), ch, font=self.tech, fill=tech_color)
        n = typed
        if char_state:
            i, digit, fade = char_state
            x = self.tech_x + i * self.tech_adv
            if fade < 1:
                d.text((x, self.tech_y), digit, font=self.tech, fill=mix(BINARY, BG, 1 - fade))
            if fade > 0:
                d.text((x, self.tech_y), ".tech"[i], font=self.tech, fill=mix(TECH, BG, fade))
            n = i + 1
        if cursor is not None:
            cx = self.cursor_x(n)
            base = self.tech_y + self.tech.getmetrics()[0]
            ch = CURSOR_H * self.tech_size
            d.rectangle([round(cx), round(base - ch), round(cx + CURSOR_W * self.tech_size) - 1, round(base) - 1], fill=mix(CURSOR, BG, cursor))
        d.text((self.tag_x, self.tag_y), "live security news + CVEs", font=self.tag, fill=MUTED)
        return im


def mix(a, b, t):
    """a over b at alpha t."""
    return tuple(round(a[k] * t + b[k] * (1 - t)) for k in range(3))


PALETTE = [BG, FG, MUTED, RED, TECH, BINARY, CURSOR, RED_MID]


def palette_image():
    p = Image.new("P", (1, 1))
    flat = [c for rgb in PALETTE for c in rgb]
    p.putpalette(flat + [0] * (768 - len(flat)))
    return p


def blink_value(t_ms):
    f = (t_ms % BLINK_MS) / BLINK_MS
    return BLINK_LOW + (1 - BLINK_LOW) * (0.5 + 0.5 * math.cos(2 * math.pi * f))


def gif_frames(lock: Lockup):
    """(image, duration ms) pairs."""
    frames = [(lock.draw(), 2400)]  # frame 1: the finished mark
    step = 100
    for t in range(step, FADE_OUT_MS + 1, step):  # ".tech" fades out
        frames.append((lock.draw(tech_alpha=1 - t / FADE_OUT_MS), step))
    frames.append((lock.draw(typed=0, cursor=1.0), PAUSE_MS))
    digits = ["1", "0", "1", "1", "0"]
    flips = ["0", "1", "0", "0", "1"]
    for i in range(5):
        frames.append((lock.draw(typed=i, char_state=(i, digits[i], 0.0), cursor=1.0), FLIP_MS))
        frames.append((lock.draw(typed=i, char_state=(i, flips[i], 0.0), cursor=1.0), FLIP_MS))
        for k, fade in enumerate((1 / 3, 2 / 3, 1.0)):
            frames.append((lock.draw(typed=i, char_state=(i, flips[i], fade), cursor=1.0), round(FADE_MS / 3)))
    blink_step = 150
    for t in range(0, BLINK_COUNT * BLINK_MS, blink_step):
        v = blink_value(t)
        frames.append((lock.draw(cursor=v, square_alpha=v), blink_step))
    frames.append((lock.draw(), 4000))  # hold
    return frames


def main():
    # Icons
    write_ico(APP / "favicon.ico", [grid_icon(16), grid_icon(32)])
    (APP / "icon.svg").write_text(icon_svg(), encoding="utf-8")
    safe_icon(180).save(APP / "apple-icon.png", optimize=True)
    safe_icon(192).save(PUBLIC / "icon-192.png", optimize=True)
    safe_icon(512).save(PUBLIC / "icon-512.png", optimize=True)

    lock = Lockup()
    lock.draw().save(PUBLIC / "og.png", optimize=True)

    pal = palette_image()
    frames = [(im.quantize(palette=pal, dither=Image.Dither.NONE), ms) for im, ms in gif_frames(lock)]
    first, rest = frames[0][0], [f for f, _ in frames[1:]]
    first.save(
        PUBLIC / "og.gif",
        save_all=True,
        append_images=rest,
        duration=[ms for _, ms in frames],
        loop=0,
        optimize=False,
        disposal=1,
    )
    for name in ("app/favicon.ico", "app/icon.svg", "app/apple-icon.png", "public/icon-192.png", "public/icon-512.png", "public/og.png", "public/og.gif"):
        print(name, (ROOT / name).stat().st_size)


if __name__ == "__main__":
    main()
