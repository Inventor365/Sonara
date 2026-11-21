#!/usr/bin/env python3
"""Look-dev board for the Space theme: phone-resolution stills of every screen, the type and the palette.

    python3 -I scripts/space/lookdev_board.py <sources_dir> <out_dir> [home library explore search player settings type all]

Run lookdev.py first (it traces the LUTs this reads: lut_home.npz, lut_player.npz). The UI drawn here
is a mock-up of the real screens' layout at 1152 x 2560, for judging the look before any app code.
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lookdev as ld  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
SRC, OUT = ld.SRC, ld.OUT
W, H = 1152, 2560
DP = W / 393.0                      # px per dp at this width
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
FONTS = os.path.join(REPO, "app/src/main/res/font")

# ---------------------------------------------------------------- palette

VOID_0 = (0x02, 0x03, 0x06)
VOID_1 = (0x07, 0x09, 0x0F)
STARLIGHT = (0xF2, 0xF4, 0xF8)
SILVER = (0xA9, 0xB0, 0xBC)
DIM = (0x6E, 0x75, 0x82)
ACCENT = (0xF4, 0xE3, 0xC1)         # pale warm white-gold: the disk's hot side
ACCENT_INK = (0x14, 0x11, 0x0B)
GLASS_TINT = (0x8C, 0x96, 0xAA)
PALETTE = [
    ("Void", VOID_0, "#020306  page floor"), ("Void lift", VOID_1, "#07090F  gradient end"),
    ("Starlight", STARLIGHT, "#F2F4F8  titles, body"), ("Silver", SILVER, "#A9B0BC  secondary text"),
    ("Dust", DIM, "#6E7582  captions, eyebrows"), ("Disk gold", ACCENT, "#F4E3C1  the one accent"),
    ("Smoked glass", (0x17, 0x1A, 0x21), "#8C96AA @ 7%  surfaces"), ("Hairline", (0x2A, 0x2D, 0x33), "#FFFFFF @ 10%  borders"),
]


def font(weight, sp):
    name = {"regular": "sf_pro_display_regular.otf", "medium": "sf_pro_display_medium.otf",
            "semibold": "sf_pro_display_semibold.otf"}[weight]
    return ImageFont.truetype(os.path.join(FONTS, name), max(8, int(round(sp * DP))))


def dp(v):
    return int(round(v * DP))


# ---------------------------------------------------------------- drawing helpers

def text(im, xy, s, f, fill, track=0.0, alpha=255, anchor_right=False):
    """Draws s with letter-spacing `track` (in em). Returns its width."""
    d = ImageDraw.Draw(im)
    widths = [f.getlength(ch) + track * f.size for ch in s]
    total = sum(widths) - track * f.size
    x, y = xy
    if anchor_right:
        x -= total
    if track == 0:
        d.text((x, y), s, font=f, fill=fill + (alpha,))
    else:
        for ch, w in zip(s, widths):
            d.text((x, y), ch, font=f, fill=fill + (alpha,))
            x += w
    return total


def rr_mask(size, radius, ss=4):
    w, h = size
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius * ss, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def rr_outline(size, radius, width=1.5, ss=4):
    w, h = size
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius * ss, outline=255, width=int(width * ss))
    return m.resize((w, h), Image.LANCZOS)


def glass(canvas, box, radius, blur=30, dark=0.50, tint_alpha=0.07, border=0.11, spec=0.42, clear=False):
    """Dark liquid glass: the scene behind, blurred and dimmed, a cool smoke, a hairline border and a
    crisp specular top edge. `canvas` is RGB; modified in place."""
    x0, y0, x1, y1 = box
    m = blur * 2
    src = canvas.crop((max(0, x0 - m), max(0, y0 - m), min(W, x1 + m), min(H, y1 + m)))
    bl = src.filter(ImageFilter.GaussianBlur(blur))
    ox, oy = x0 - max(0, x0 - m), y0 - max(0, y0 - m)
    region = np.asarray(bl.crop((ox, oy, ox + x1 - x0, oy + y1 - y0))).astype(np.float32) / 255
    # Refraction: the glass slightly magnifies what's behind toward its centre (a lens, not a tint).
    hh, ww = region.shape[:2]
    yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32)
    ex = np.clip(np.minimum(xx, ww - 1 - xx) / (radius + 1), 0, 1)
    ey = np.clip(np.minimum(yy, hh - 1 - yy) / (radius + 1), 0, 1)
    k = (1 - ex * ey) * 0.06
    sx = np.clip(xx + (ww / 2 - xx) * k, 0, ww - 1).astype(int)
    sy = np.clip(yy + (hh / 2 - yy) * k, 0, hh - 1).astype(int)
    region = region[sy, sx]
    region = region * dark + np.array(GLASS_TINT) / 255 * tint_alpha
    if clear:
        region = region * 0.0 + np.array(VOID_1) / 255 * 0.9
    patch = Image.fromarray((np.clip(region, 0, 1) * 255).astype(np.uint8))
    canvas.paste(patch, (x0, y0), rr_mask((x1 - x0, y1 - y0), radius))
    # Hairline border, and a brighter top edge that fades toward the corners.
    ol = np.asarray(rr_outline((x1 - x0, y1 - y0), radius, 1.6)).astype(np.float32) / 255
    top = np.clip(1 - yy / max(1.0, radius * 1.2), 0, 1) ** 1.5
    across = np.sin(np.clip(xx / ww, 0, 1) * math.pi) ** 0.8
    a = ol * (border + spec * top * across)
    base = np.asarray(canvas.crop(box)).astype(np.float32) / 255
    out = base * (1 - a[..., None]) + a[..., None] * 1.0
    canvas.paste(Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)), (x0, y0))


def overlay(canvas):
    return Image.new("RGBA", canvas.size, (0, 0, 0, 0))


def flatten(canvas, ov):
    c = canvas.convert("RGBA")
    c.alpha_composite(ov)
    return c.convert("RGB")


def logo(ov, x, y, width, colour=STARLIGHT, glow=True):
    """The Sonara mark: three concentric arcs about (365, -60) in its 730 x 484 viewport, r 190/330/470,
    from 54 to 126 degrees, stroke 78, round caps. Starlight, with a faint warm inner glow."""
    s = width / 730.0
    ss = 4
    pad = int(width * 0.4)                       # room for the glow, so its blur is never clipped
    x, y = x - pad, y - pad
    layer = Image.new("L", (int(730 * s * ss) + 2 * pad * ss, int(484 * s * ss) + 2 * pad * ss), 0)
    d = ImageDraw.Draw(layer)
    for r in (190, 330, 470):
        for a in np.linspace(math.radians(54.0), math.radians(126.0), 220):
            px = (365 + r * math.cos(a)) * s * ss + pad * ss
            py = (-60 + r * math.sin(a)) * s * ss + pad * ss
            rad = 39 * s * ss
            d.ellipse([px - rad, py - rad, px + rad, py + rad], fill=255)
    layer = layer.resize((layer.width // ss, layer.height // ss), Image.LANCZOS)
    if glow:
        g = layer.filter(ImageFilter.GaussianBlur(width * 0.10))
        gl = Image.new("RGBA", g.size, ACCENT + (0,))
        gl.putalpha(g.point(lambda v: int(v * 0.55)))
        ov.alpha_composite(gl, (int(x), int(y)))
    fill = Image.new("RGBA", layer.size, colour + (0,))
    fill.putalpha(layer)
    ov.alpha_composite(fill, (int(x), int(y)))


def icon(ov, kind, cx, cy, size, colour, width=None):
    d = ImageDraw.Draw(ov)
    s = size / 2
    w = width or max(2, int(size * 0.09))
    c = colour + (255,) if len(colour) == 3 else colour
    if kind == "home":
        d.line([(cx - s * 0.8, cy - s * 0.05), (cx, cy - s * 0.8), (cx + s * 0.8, cy - s * 0.05)], fill=c, width=w, joint="curve")
        d.rounded_rectangle([cx - s * 0.6, cy - s * 0.2, cx + s * 0.6, cy + s * 0.75], s * 0.12, outline=c, width=w)
    elif kind == "explore":
        g = s * 0.12
        for ix in (-1, 1):
            for iy in (-1, 1):
                x0 = cx + (g if ix > 0 else -s * 0.8)
                y0 = cy + (g if iy > 0 else -s * 0.8)
                d.rounded_rectangle([x0, y0, x0 + s * 0.68, y0 + s * 0.68], s * 0.14, outline=c, width=w)
    elif kind == "library":
        for i, inset in enumerate((0.0, 0.18, 0.36)):
            y = cy + s * 0.75 - i * s * 0.38 - s * 0.5
            d.rounded_rectangle([cx - s * (0.75 - inset), y, cx + s * (0.75 - inset), y + s * 0.5], s * 0.1, outline=c, width=w)
    elif kind == "search":
        r = s * 0.55
        d.ellipse([cx - r - s * 0.15, cy - r - s * 0.15, cx + r - s * 0.15, cy + r - s * 0.15], outline=c, width=w)
        d.line([(cx + s * 0.28, cy + s * 0.28), (cx + s * 0.8, cy + s * 0.8)], fill=c, width=w)
    elif kind == "pause":
        d.rounded_rectangle([cx - s * 0.5, cy - s * 0.7, cx - s * 0.15, cy + s * 0.7], s * 0.1, fill=c)
        d.rounded_rectangle([cx + s * 0.15, cy - s * 0.7, cx + s * 0.5, cy + s * 0.7], s * 0.1, fill=c)
    elif kind == "next":
        for off in (-0.45, 0.25):
            d.polygon([(cx + s * off, cy - s * 0.6), (cx + s * (off + 0.7), cy), (cx + s * off, cy + s * 0.6)], fill=c)
    elif kind == "prev":
        for off in (0.45, -0.25):
            d.polygon([(cx + s * off, cy - s * 0.6), (cx + s * (off - 0.7), cy), (cx + s * off, cy + s * 0.6)], fill=c)
    elif kind == "account":
        d.ellipse([cx - s * 0.3, cy - s * 0.75, cx + s * 0.3, cy - s * 0.15], outline=c, width=w)
        d.arc([cx - s * 0.7, cy - s * 0.05, cx + s * 0.7, cy + s * 1.2], 180, 360, fill=c, width=w)
    elif kind == "cast":
        d.rounded_rectangle([cx - s * 0.75, cy - s * 0.6, cx + s * 0.75, cy + s * 0.55], s * 0.15, outline=c, width=w)
        d.ellipse([cx - s * 0.12, cy - s * 0.12, cx + s * 0.12, cy + s * 0.12], fill=c)
    elif kind == "history":
        d.arc([cx - s * 0.7, cy - s * 0.7, cx + s * 0.7, cy + s * 0.7], -60, 230, fill=c, width=w)
        d.line([(cx, cy - s * 0.35), (cx, cy), (cx + s * 0.3, cy + s * 0.2)], fill=c, width=w)
    elif kind == "chevron":
        d.line([(cx - s * 0.5, cy - s * 0.2), (cx, cy + s * 0.3), (cx + s * 0.5, cy - s * 0.2)], fill=c, width=w, joint="curve")
    elif kind == "dots":
        for dx in (-0.5, 0, 0.5):
            d.ellipse([cx + s * dx - w, cy - w, cx + s * dx + w, cy + w], fill=c)
    elif kind == "shuffle":
        d.line([(cx - s * 0.7, cy - s * 0.4), (cx - s * 0.2, cy - s * 0.4), (cx + s * 0.3, cy + s * 0.4), (cx + s * 0.7, cy + s * 0.4)], fill=c, width=w)
        d.line([(cx - s * 0.7, cy + s * 0.4), (cx - s * 0.2, cy + s * 0.4), (cx + s * 0.3, cy - s * 0.4), (cx + s * 0.7, cy - s * 0.4)], fill=c, width=w)
    elif kind == "repeat":
        d.rounded_rectangle([cx - s * 0.7, cy - s * 0.45, cx + s * 0.7, cy + s * 0.45], s * 0.3, outline=c, width=w)
    elif kind == "lyrics":
        for i, ln in enumerate((0.9, 0.6, 0.8)):
            y = cy - s * 0.5 + i * s * 0.5
            d.line([(cx - s * 0.7, y), (cx - s * 0.7 + s * 1.4 * ln, y)], fill=c, width=w)
    elif kind == "queue":
        for i in range(3):
            y = cy - s * 0.5 + i * s * 0.5
            d.line([(cx - s * 0.7, y), (cx + s * 0.4, y)], fill=c, width=w)
        d.polygon([(cx + s * 0.5, cy + s * 0.2), (cx + s * 0.9, cy + s * 0.45), (cx + s * 0.5, cy + s * 0.7)], fill=c)
    elif kind == "gear":
        d.ellipse([cx - s * 0.6, cy - s * 0.6, cx + s * 0.6, cy + s * 0.6], outline=c, width=w)
        d.ellipse([cx - s * 0.22, cy - s * 0.22, cx + s * 0.22, cy + s * 0.22], outline=c, width=w)


def status_bar(ov):
    f = font("medium", 14)
    text(ov, (dp(22), dp(13)), "6:38", f, STARLIGHT)
    text(ov, (W - dp(22), dp(13)), "100%", f, STARLIGHT, anchor_right=True)


def toolbar_pill(canvas, icons=("cast", "account")):
    w = dp(46) * len(icons) + dp(10)
    box = (W - dp(16) - w, dp(40), W - dp(16), dp(40) + dp(44))
    glass(canvas, box, dp(22))
    ov = overlay(canvas)
    for i, k in enumerate(icons):
        icon(ov, k, box[0] + dp(5) + dp(46) * i + dp(23), box[1] + dp(22), dp(20), STARLIGHT)
    return flatten(canvas, ov)


def bars(canvas, selected="home", mini=True):
    """The mini player and the nav bar: dark liquid glass over the page."""
    if mini:
        mb = (dp(12), H - dp(156), W - dp(12), H - dp(156) + dp(58))
        glass(canvas, mb, dp(30))
        art = cover((dp(44), dp(44)))
        canvas.paste(art, (mb[0] + dp(8), mb[1] + dp(8)), rr_mask(art.size, dp(10)))
        ov = overlay(canvas)
        text(ov, (mb[0] + dp(62), mb[1] + dp(11)), "Who's They?", font("medium", 15), STARLIGHT)
        text(ov, (mb[0] + dp(62), mb[1] + dp(31)), "Hans Zimmer", font("regular", 13), SILVER)
        icon(ov, "pause", mb[2] - dp(78), mb[1] + dp(30), dp(20), STARLIGHT)
        icon(ov, "next", mb[2] - dp(34), mb[1] + dp(30), dp(20), STARLIGHT)
        # Progress: a hairline in the accent along the bottom of the glass.
        d = ImageDraw.Draw(ov)
        y = mb[3] - dp(2)
        d.line([(mb[0] + dp(26), y), (mb[2] - dp(26), y)], fill=(255, 255, 255, 30), width=dp(1.2))
        d.line([(mb[0] + dp(26), y), (mb[0] + dp(26) + (mb[2] - mb[0] - dp(52)) * 0.38, y)], fill=ACCENT + (235,), width=dp(1.2))
        canvas = flatten(canvas, ov)
    nb = (dp(12), H - dp(90), W - dp(12), H - dp(90) + dp(64))
    glass(canvas, nb, dp(33))
    ov = overlay(canvas)
    items = [("home", "Home"), ("explore", "Explore"), ("library", "Library"), ("search", "Search")]
    cw = (nb[2] - nb[0]) / 4
    for i, (k, label) in enumerate(items):
        cx = nb[0] + cw * (i + 0.5)
        on = k == selected
        if on:
            pill = Image.new("RGBA", (int(cw - dp(14)), dp(54)), (0, 0, 0, 0))
            ImageDraw.Draw(pill).rounded_rectangle([0, 0, pill.width - 1, pill.height - 1], dp(27), fill=ACCENT + (34,), outline=ACCENT + (70,), width=2)
            ov.alpha_composite(pill, (int(cx - pill.width / 2), nb[1] + dp(6)))
        col = ACCENT if on else SILVER
        icon(ov, k, cx, nb[1] + dp(25), dp(21), col)
        f = font("medium" if on else "regular", 11)
        text(ov, (cx - f.getlength(label) / 2, nb[1] + dp(41)), label, f, col)
    d = ImageDraw.Draw(ov)
    d.rounded_rectangle([W / 2 - dp(54), H - dp(12), W / 2 + dp(54), H - dp(8)], dp(2), fill=STARLIGHT + (200,))
    return flatten(canvas, ov)


def cover(size, seed=1):
    """A placeholder album cover (abstract, original): deep teal dusk, a pale sun, a horizon line."""
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = yy / h
    col = (np.array([0.05, 0.16, 0.20]) * (1 - t)[..., None] + np.array([0.01, 0.03, 0.05]) * t[..., None])
    sun = np.exp(-(((xx - w * 0.62) ** 2 + (yy - h * 0.40) ** 2) / (w * 0.13) ** 2) ** 3)
    col = col + sun[..., None] * np.array([0.92, 0.90, 0.82])
    col[(yy > h * 0.64) & (yy < h * 0.64 + max(1, h / 150))] += 0.35
    rng = np.random.default_rng(seed)
    col += (rng.random((h, w, 1)) - 0.5) * 0.03
    return Image.fromarray((np.clip(col, 0, 1) * 255).astype(np.uint8))


# ---------------------------------------------------------------- scene plates

def void(h=H, seed=3, stars=260):
    """Plain void: a dithered #020306 -> #07090F gradient and sparse stars of varied magnitude/colour."""
    t = np.linspace(0, 1, h)[:, None, None]
    col = np.array(VOID_0) / 255 * (1 - t) + np.array(VOID_1) / 255 * t
    img = np.broadcast_to(col, (h, W, 3)).copy()
    rng = np.random.default_rng(seed)
    img += (rng.random((h, W, 1)) - 0.5) / 255 * 1.6          # dither: no banding
    temps = np.array([[0.75, 0.83, 1.0], [0.9, 0.93, 1.0], [1, 1, 1], [1, 0.94, 0.84], [1, 0.84, 0.66]])
    for _ in range(stars):
        x, y = rng.random() * W, rng.random() * h
        m = rng.random() ** 3.2
        c = temps[rng.integers(0, 5)] * (0.12 + 0.88 * m)
        r = 0.6 + 1.3 * m
        x0, y0 = int(x) - 4, int(y) - 4
        yy, xx = np.mgrid[y0:y0 + 9, x0:x0 + 9]
        ok = (yy >= 0) & (yy < h) & (xx >= 0) & (xx < W)
        g = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * r * r * 0.35))
        img[yy[ok], xx[ok]] += g[ok][:, None] * c
    return img


def regrade(path, crop=None, size=None, black=0.02, sat=0.75, gain=1.0, gamma=1.0):
    im = Image.open(os.path.join(SRC, path)).convert("RGB")
    if crop:
        w, h = im.size
        im = im.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
    if size:
        im = im.resize(size, Image.LANCZOS)
    a = (np.asarray(im).astype(np.float32) / 255) ** 2.2
    a = np.clip((a - black) / (1 - black), 0, None)
    lum = a @ np.array([0.2126, 0.7152, 0.0722])
    a = lum[..., None] + (a - lum[..., None]) * sat
    return np.clip(a * gain, 0, None) ** gamma


def to_srgb(lin):
    return np.clip(lin, 0, 1) ** (1 / 2.2)


def add_screen(base, sprite, x, y, alpha=1.0):
    """Adds a linear-light sprite on black onto base (also linear) at (x, y): light adds, no box edges."""
    h, w = sprite.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(base.shape[1], x + w), min(base.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    s = sprite[y0 - y:y1 - y, x0 - x:x1 - x]
    b = base[y0:y1, x0:x1]
    base[y0:y1, x0:x1] = 1 - (1 - b) * (1 - np.clip(s * alpha, 0, 1))


def soft_vignette(w, h, power=2.0):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    return np.clip(1 - r, 0, 1) ** power


def fade_rows(img, y0, y1):
    """Fades a linear scene into the void between rows y0 and y1."""
    v = void(img.shape[0], stars=0) ** 2.2
    t = np.clip((np.arange(img.shape[0]) - y0) / max(1, y1 - y0), 0, 1)[:, None, None]
    t = t * t * (3 - 2 * t)
    return img * (1 - t) + v * t


def plate_srgb(lin):
    return Image.fromarray((to_srgb(lin) * 255 + 0.5).astype(np.uint8))


def scene_home():
    L = ld.traced("home")
    sky = ld.Sky(gain=0.35, star_density=0.07)
    pxa = math.atan(1 / ld.VIEWS["home"]["px_per_m"] / 80)
    lin = ld.shade(L, sky, 12.0, pxa)
    srgb = ld.finish(lin, 0.9)
    # Keep the greeting's side of the sky darker and cleaner: a soft falloff from the left.
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    left = np.clip(1 - xx / (W * 0.55), 0, 1) ** 1.6 * np.clip(1 - np.abs(yy - 520) / 520, 0, 1)
    srgb = srgb * (1 - 0.55 * left[..., None])
    # Lower the whole plate a little so the disk's left tip clears the subtitle (the top rows are sky).
    shift = 56
    srgb = np.concatenate([srgb[:shift], srgb[:-shift]], 0)
    lin = srgb ** 2.2
    return plate_srgb(fade_rows(lin, 1150, 1700))


def scene_library():
    """A spiral galaxy rising over the dark limb of a planet. Calm, editorial."""
    base = void(H, seed=11, stars=320) ** 2.2
    g = regrade("heic0506a.jpg", crop=(0.18, 0.12, 0.78, 0.82), size=(860, 1003), black=0.04, sat=0.62, gain=1.05)
    g = g * soft_vignette(g.shape[1], g.shape[0], 1.4)[..., None]
    gi = Image.fromarray((to_srgb(g) * 255).astype(np.uint8)).rotate(-28, Image.BICUBIC, expand=False)
    g = (np.asarray(gi).astype(np.float32) / 255) ** 2.2
    add_screen(base, g, 470, 170, 0.92)
    # The limb: a vast dark world, its edge lit by a thin cool rim of atmosphere.
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    R = 3400.0
    cx, cy = W * 0.30, 900 + R
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) - R
    planet = d < 0
    rim = np.exp(-np.maximum(d, 0) / 10.0) * np.exp(-np.maximum(-d, 0) / 3.0)
    glow = np.exp(-np.maximum(d, 0) / 90.0) * 0.10
    lit = np.clip((xx - W * 0.1) / W, 0, 1)
    base = np.where(planet[..., None], np.array([0.0012, 0.0016, 0.0024]) + (np.exp(d / 260.0)[..., None]) * np.array([0.004, 0.006, 0.010]), base)
    base += (rim * 0.55 * (0.4 + lit))[..., None] * np.array([0.55, 0.74, 0.95])
    base += (glow * (0.3 + lit))[..., None] * np.array([0.25, 0.45, 0.70])
    return plate_srgb(fade_rows(base, 1200, 1500))


def gradient_map(lum, stops):
    xs = [s[0] for s in stops]
    return np.stack([np.interp(lum, xs, [s[1][c] for s in stops]) for c in range(3)], -1)


def scene_explore():
    """A wide nebula field (JWST's Cosmic Cliffs), regraded into deep teal, violet and faint rose."""
    base = void(H, seed=21, stars=240) ** 2.2
    n = regrade("weic2205a.jpg", crop=(0.0, 0.08, 1.0, 0.92), size=(int(1400 * 14575 / 8441 * 0.84 / 0.84 * 0.58), 1400), black=0.01, sat=1.0, gain=1.0)
    lum = (n @ np.array([0.2126, 0.7152, 0.0722])) ** 0.8
    lum = np.clip((lum - 0.03) / 0.97, 0, 1) ** 1.05
    graded = gradient_map(lum, [(0.0, (0, 0, 0)), (0.12, (0.002, 0.016, 0.020)), (0.30, (0.010, 0.060, 0.075)),
                                (0.50, (0.060, 0.030, 0.140)), (0.72, (0.24, 0.09, 0.20)), (0.90, (0.62, 0.46, 0.54)), (1.0, (1.0, 0.97, 0.95))])
    graded *= soft_vignette(graded.shape[1], graded.shape[0], 0.45)[..., None] * 1.15
    graded = graded[:, (graded.shape[1] - W) // 2:(graded.shape[1] - W) // 2 + W] if graded.shape[1] > W else graded
    add_screen(base, graded, 0, -120, 1.0)
    return plate_srgb(fade_rows(base, 800, 1150))


def scene_search():
    """A deep, quiet star field with a distant galaxy cluster (Hubble Ultra Deep Field), dimmed."""
    base = void(H, seed=31, stars=180) ** 2.2
    f = regrade("heic0406a.jpg", crop=(0.05, 0.55, 0.65, 0.93), size=(W, int(W * 0.38 / 0.60)), black=0.004, sat=0.7, gain=0.6)
    f *= soft_vignette(f.shape[1], f.shape[0], 0.5)[..., None]
    add_screen(base, f, 0, 30, 1.0)
    return plate_srgb(fade_rows(base, 520, 900))


def scene_player(tint):
    L = ld.traced("player")
    sky = ld.Sky(lon_deg=60.0, lat_deg=-30.0, roll_deg=20.0, gain=0.30, star_density=0.07)
    pxa = math.atan(1 / ld.VIEWS["player"]["px_per_m"] / 80)
    srgb = ld.finish(ld.shade(L, sky, 20.0, pxa, tint=tint), 1.4)
    return plate_srgb(fade_rows(srgb ** 2.2, 1500, 2200))


def scene_settings():
    return plate_srgb(void(H, seed=41, stars=140) ** 2.2 * 1.0)


# ---------------------------------------------------------------- screens

def eyebrow(ov, xy, s, colour=DIM, sp=11):
    text(ov, xy, s.upper(), font("medium", sp), colour, track=0.22)


def screen_home():
    c = scene_home()
    c = toolbar_pill(c)
    ov = overlay(c)
    status_bar(ov)
    logo(ov, dp(20), dp(100), dp(32))
    eyebrow(ov, (dp(20), dp(140)), "Good evening")
    ft = font("regular", 32)
    text(ov, (dp(18), dp(157)), "Wind-down time,", ft, STARLIGHT, track=0.012)
    text(ov, (dp(18), dp(196)), "Pranav", ft, STARLIGHT, track=0.012)
    fs = font("regular", 15)
    text(ov, (dp(20), dp(242)), "Sing like nobody's listening.", fs, SILVER)
    text(ov, (dp(20), dp(261)), "Somebody probably is.", fs, SILVER)
    c = flatten(c, ov)
    # Sign-in card: smoked glass, no gradient.
    card = (dp(16), dp(364), W - dp(16), dp(364) + dp(126))
    glass(c, card, dp(26), blur=34, dark=0.42)
    ov = overlay(c)
    eyebrow(ov, (card[0] + dp(20), card[1] + dp(18)), "Sonara × YouTube Music")
    text(ov, (card[0] + dp(20), card[1] + dp(36)), "Sign in to YouTube Music", font("regular", 23), STARLIGHT, track=0.005)
    btn = (card[0] + dp(20), card[1] + dp(80), card[0] + dp(20) + dp(186), card[1] + dp(80) + dp(38))
    ImageDraw.Draw(ov).rounded_rectangle(btn, dp(19), fill=(250, 250, 250, 255))
    g = font("semibold", 15)
    d = ImageDraw.Draw(ov)
    gx, gy = btn[0] + dp(22), (btn[1] + btn[3]) / 2
    for a0, a1, col in ((-45, 45, (66, 133, 244)), (45, 135, (52, 168, 83)), (135, 200, (251, 188, 5)), (200, 315, (234, 67, 53))):
        d.arc([gx - dp(8), gy - dp(8), gx + dp(8), gy + dp(8)], a0, a1, fill=col + (255,), width=dp(3))
    text(ov, (btn[0] + dp(40), btn[1] + dp(9)), "Sign in with Google", g, (32, 33, 36))
    # Top Picks: tiles keep their own art, or sit on neutral glass.
    text(ov, (dp(18), dp(506)), "Top Picks for You", font("medium", 20), STARLIGHT)
    c = flatten(c, ov)
    t1 = (dp(16), dp(540), dp(16) + dp(164), dp(540) + dp(164))
    glass(c, t1, dp(22), blur=30, dark=0.38)
    t2 = (dp(190), dp(540), dp(190) + dp(164), dp(540) + dp(164))
    neb = regrade("weic2205a.jpg", crop=(0.30, 0.25, 0.62, 0.80), size=(t2[2] - t2[0], t2[3] - t2[1]), black=0.01, sat=0.85, gain=1.1)
    c.paste(plate_srgb(neb), t2[:2], rr_mask((t2[2] - t2[0], t2[3] - t2[1]), dp(22)))
    ov = overlay(c)
    # Station tile: a starlight line drawing (orbit + play glyph) on smoked glass.
    d = ImageDraw.Draw(ov)
    cx, cy = (t1[0] + t1[2]) / 2, t1[1] + dp(74)
    for r, a in ((dp(52), 40), (dp(36), 70), (dp(20), 120)):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=STARLIGHT + (a,), width=2)
    d.polygon([(cx - dp(8), cy - dp(11)), (cx + dp(12), cy), (cx - dp(8), cy + dp(11))], fill=ACCENT + (255,))
    eyebrow(ov, (t1[0] + dp(14), t1[3] - dp(46)), "Made for you", SILVER, 10)
    text(ov, (t1[0] + dp(14), t1[3] - dp(30)), "Pranav's Station", font("medium", 16), STARLIGHT)
    shade = Image.new("RGBA", (t2[2] - t2[0], dp(70)), (0, 0, 0, 0))
    sa = np.zeros((shade.height, shade.width, 4), np.uint8)
    sa[..., 3] = (np.linspace(0, 170, shade.height)[:, None]).astype(np.uint8)
    ov.alpha_composite(Image.fromarray(sa).copy(), (t2[0], t2[3] - dp(70)))
    eyebrow(ov, (t2[0] + dp(14), t2[3] - dp(46)), "Mood for you", (220, 225, 232), 10)
    text(ov, (t2[0] + dp(14), t2[3] - dp(30)), "Focus", font("medium", 16), STARLIGHT)
    text(ov, (dp(18), dp(722)), "Albums & singles", font("medium", 20), STARLIGHT)
    c = flatten(c, ov)
    for i in range(3):
        art = cover((dp(124), dp(124)), seed=7 + i)
        if i == 1:
            art = Image.fromarray((np.asarray(art)[..., ::-1]).copy())
        c.paste(art, (dp(16) + i * dp(134), dp(756)), rr_mask(art.size, dp(14)))
    c = bars(c, "home")
    return c


def screen_home_scrolled():
    """Home scrolled: the scene has parallaxed up a few px and the content sits over the void."""
    full = screen_home()
    return full


def pass_card(c, box):
    """Black anodised card with a nebula-foil sheen."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rng = np.random.default_rng(5)
    brushed = np.repeat(rng.standard_normal((h, 1)), w, 1) * 0.004 + rng.standard_normal((h, w)) * 0.002
    base = np.array([0.035, 0.040, 0.052]) * (1 - yy / h * 0.45)[..., None] + brushed[..., None]
    band = np.exp(-(((xx / w) * 0.9 + (yy / h) * 0.55 - 0.78) / 0.20) ** 2)
    hue = (xx / w) * 0.7 + (yy / h) * 0.3
    foil = gradient_map(hue, [(0.0, (0.10, 0.45, 0.48)), (0.45, (0.38, 0.28, 0.65)), (0.80, (0.62, 0.36, 0.46)), (1.0, (0.80, 0.70, 0.60))])
    base = base + foil * band[..., None] * 0.22
    for _ in range(90):
        sx, sy = rng.random() * w, rng.random() * h
        m = rng.random() ** 4
        base += np.exp(-((xx - sx) ** 2 + (yy - sy) ** 2) / 2.0)[..., None] * (0.15 + 0.8 * m) * band[..., None] * 1.5
    patch = Image.fromarray((np.clip(base, 0, 1) * 255).astype(np.uint8))
    c.paste(patch, (x0, y0), rr_mask((w, h), dp(26)))
    ol = rr_outline((w, h), dp(26), 1.6)
    hl = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    hl.putalpha(ol.point(lambda v: int(v * 0.14)))
    cc = c.convert("RGBA")
    cc.alpha_composite(hl, (x0, y0))
    return cc.convert("RGB")


def screen_library():
    c = scene_library()
    c = toolbar_pill(c, ("history", "cast", "account"))
    ov = overlay(c)
    status_bar(ov)
    eyebrow(ov, (dp(20), dp(150)), "Your library")
    text(ov, (dp(18), dp(168)), "Pranav", font("regular", 40), STARLIGHT, track=0.014)
    c = flatten(c, ov)
    card = (dp(16), dp(330), W - dp(16), dp(330) + dp(212))
    c = pass_card(c, card)
    ov = overlay(c)
    logo(ov, card[0] + dp(20), card[1] + dp(22), dp(20), glow=False)
    eyebrow(ov, (card[0] + dp(48), card[1] + dp(22)), "Sonara Pass", SILVER, 10)
    text(ov, (card[2] - dp(20), card[1] + dp(22)), "SNR 1428 1268", font("medium", 10), DIM, track=0.18, anchor_right=True)
    d = ImageDraw.Draw(ov)
    ax, ay = card[0] + dp(42), card[1] + dp(96)
    d.ellipse([ax - dp(20), ay - dp(20), ax + dp(20), ay + dp(20)], outline=ACCENT + (255,), width=dp(1.4))
    text(ov, (ax - dp(6), ay - dp(12)), "P", font("regular", 19), ACCENT)
    eyebrow(ov, (card[0] + dp(76), card[1] + dp(76)), "Holder", DIM, 9)
    text(ov, (card[0] + dp(76), card[1] + dp(88)), "Pranav", font("regular", 24), STARLIGHT, track=0.01)
    rng = np.random.default_rng(2)
    for i in range(54):
        x = card[0] + dp(20) + i * dp(3.4)
        hgt = dp(4 + 16 * abs(math.sin(i * 0.37)) * (0.5 + 0.5 * rng.random()))
        d.line([(x, card[3] - dp(30) - hgt), (x, card[3] - dp(30))], fill=STARLIGHT + (190,), width=dp(1.4))
    eyebrow(ov, (card[2] - dp(20) - dp(84), card[3] - dp(52)), "Member since", DIM, 8)
    text(ov, (card[2] - dp(20), card[3] - dp(38)), "NOV 2026", font("medium", 12), SILVER, track=0.16, anchor_right=True)
    c = flatten(c, ov)
    stats = (dp(16), dp(556), W - dp(16), dp(556) + dp(122))
    glass(c, stats, dp(24), dark=0.40)
    ov = overlay(c)
    text(ov, (stats[0] + dp(20), stats[1] + dp(14)), "0h 2m", font("regular", 34), STARLIGHT, track=0.01)
    eyebrow(ov, (stats[2] - dp(20) - dp(118), stats[1] + dp(22)), "Total listening", DIM, 9)
    for i, (k, v) in enumerate((("Plays", "0"), ("Artists", "2"), ("Top artist", "Atlantic Notes"))):
        eyebrow(ov, (stats[0] + dp(20) + i * dp(78), stats[1] + dp(70)), k, DIM, 9)
        text(ov, (stats[0] + dp(20) + i * dp(78), stats[1] + dp(84)), v, font("regular", 15), STARLIGHT)
    c = flatten(c, ov)
    sb = (dp(16), dp(694), W - dp(16), dp(694) + dp(46))
    glass(c, sb, dp(23), dark=0.40)
    ov = overlay(c)
    icon(ov, "search", sb[0] + dp(26), sb[1] + dp(23), dp(16), SILVER)
    text(ov, (sb[0] + dp(46), sb[1] + dp(13)), "Search your library", font("regular", 15), DIM)
    c = flatten(c, ov)
    return bars(c, "library")


def screen_explore():
    c = scene_explore()
    c = toolbar_pill(c)
    ov = overlay(c)
    status_bar(ov)
    eyebrow(ov, (dp(20), dp(150)), "Explore")
    text(ov, (dp(18), dp(168)), "Moods & genres", font("regular", 36), STARLIGHT, track=0.012)
    c = flatten(c, ov)
    cats = [("Chill", (0.30, 0.42, 0.62)), ("Commute", (0.62, 0.48, 0.12)), ("Energize", (0.62, 0.56, 0.28)), ("Feel good", (0.30, 0.55, 0.38)),
            ("Focus", (0.20, 0.40, 0.48)), ("Party", (0.55, 0.20, 0.45)), ("Romance", (0.62, 0.22, 0.28)), ("Sleep", (0.18, 0.20, 0.42))]
    for i, (name, col) in enumerate(cats):
        x = dp(16) + (i % 2) * dp(184)
        y = dp(420) + (i // 2) * dp(104)
        w, h = dp(176), dp(94)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        a = np.array(col) * (0.55 + 0.45 * (1 - yy / h))[..., None] * (0.8 + 0.2 * (xx / w))[..., None]
        c.paste(Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)), (x, y), rr_mask((w, h), dp(18)))
        ov = overlay(c)
        text(ov, (x + dp(14), y + h - dp(30)), name, font("medium", 16), STARLIGHT)
        c = flatten(c, ov)
    return bars(c, "explore")


def screen_search():
    c = scene_search()
    sb = (dp(16), dp(40), W - dp(16) - dp(108), dp(40) + dp(44))
    glass(c, sb, dp(22))
    c = toolbar_pill(c)
    ov = overlay(c)
    status_bar(ov)
    icon(ov, "search", sb[0] + dp(24), sb[1] + dp(22), dp(16), SILVER)
    text(ov, (sb[0] + dp(44), sb[1] + dp(12)), "Artists, songs, lyrics", font("regular", 15), DIM)
    c = flatten(c, ov)
    tabs = (dp(16), dp(98), W - dp(16), dp(98) + dp(40))
    glass(c, tabs, dp(20), dark=0.40)
    ov = overlay(c)
    tw = (tabs[2] - tabs[0]) / 3
    pill = Image.new("RGBA", (int(tw - dp(8)), dp(32)), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle([0, 0, pill.width - 1, pill.height - 1], dp(16), fill=(255, 255, 255, 26), outline=(255, 255, 255, 40))
    ov.alpha_composite(pill, (int(tabs[0] + dp(4)), tabs[1] + dp(4)))
    for i, t in enumerate(("YouTube", "Library", "Addons")):
        f = font("medium", 13)
        text(ov, (tabs[0] + tw * (i + 0.5) - f.getlength(t) / 2, tabs[1] + dp(11)), t, f, STARLIGHT if i == 0 else SILVER)
    text(ov, (dp(18), dp(168)), "Recent searches", font("regular", 26), STARLIGHT, track=0.01)
    text(ov, (W - dp(20), dp(176)), "Clear", font("medium", 14), ACCENT, anchor_right=True)
    rows = [("Interstellar (Original Motion Picture…", "Album · Hans Zimmer · 2014"), ("Who's They?", "Hans Zimmer"), ("Interstellar Main Theme", "Atlantic Notes")]
    for i, (t, s) in enumerate(rows):
        y = dp(214) + i * dp(60)
        text(ov, (dp(76), y + dp(6)), t, font("regular", 16), STARLIGHT)
        text(ov, (dp(76), y + dp(27)), s, font("regular", 13), SILVER)
        text(ov, (W - dp(24), y + dp(10)), "×", font("regular", 20), DIM, anchor_right=True)
    text(ov, (dp(18), dp(408)), "Browse categories", font("regular", 22), STARLIGHT, track=0.01)
    c = flatten(c, ov)
    for i in range(3):
        art = cover((dp(48), dp(48)), seed=20 + i)
        c.paste(art, (dp(16), dp(214) + i * dp(60)), rr_mask(art.size, dp(10)))
    cats = [("Chill", (0.32, 0.42, 0.60)), ("Commute", (0.66, 0.50, 0.12)), ("Energize", (0.62, 0.58, 0.30)), ("Feel good", (0.32, 0.58, 0.40))]
    for i, (name, col) in enumerate(cats):
        x = dp(16) + (i % 2) * dp(184)
        y = dp(446) + (i // 2) * dp(104)
        w, h = dp(176), dp(94)
        yy = np.mgrid[0:h, 0:w][0].astype(np.float32)
        a = np.array(col) * (0.55 + 0.45 * (1 - yy / h))[..., None]
        c.paste(Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)), (x, y), rr_mask((w, h), dp(18)))
        ov = overlay(c)
        text(ov, (x + dp(14), y + h - dp(30)), name, font("medium", 16), STARLIGHT)
        c = flatten(c, ov)
    return bars(c, "search")


def screen_player():
    art_side = dp(266)
    art = cover((art_side, art_side), seed=4)
    tint = np.asarray(art).reshape(-1, 3).mean(0) / 255
    tint = tint / max(1e-3, tint.max())
    c = scene_player(tint)
    v = ld.VIEWS["player"]
    ax, ay = int(v["cx"] - art_side / 2), int(v["cy"] - art_side / 2)
    # A soft shadow under the floating art, then the art.
    sh = Image.new("L", (art_side + 160, art_side + 160), 0)
    ImageDraw.Draw(sh).rounded_rectangle([80, 100, 80 + art_side, 100 + art_side], dp(20), fill=210)
    sh = sh.filter(ImageFilter.GaussianBlur(40))
    c.paste(Image.new("RGB", sh.size, (0, 0, 0)), (ax - 80, ay - 80), sh)
    c.paste(art, (ax, ay), rr_mask(art.size, dp(20)))
    ov = overlay(c)
    status_bar(ov)
    icon(ov, "chevron", dp(30), dp(64), dp(20), STARLIGHT)
    f = font("medium", 10)
    lbl = "NOW PLAYING"
    text(ov, (W / 2 - (f.getlength(lbl) + 0.22 * f.size * 10) / 2, dp(58)), lbl, f, SILVER, track=0.22)
    icon(ov, "dots", W - dp(30), dp(64), dp(20), STARLIGHT)
    ty = dp(492)
    text(ov, (dp(28), ty), "Who's They?", font("regular", 28), STARLIGHT, track=0.01)
    text(ov, (dp(28), ty + dp(38)), "Hans Zimmer", font("regular", 17), SILVER)
    d = ImageDraw.Draw(ov)
    py = ty + dp(92)
    x0, x1 = dp(28), W - dp(28)
    d.line([(x0, py), (x1, py)], fill=(255, 255, 255, 40), width=dp(2.5))
    xp = x0 + (x1 - x0) * 0.38
    d.line([(x0, py), (xp, py)], fill=ACCENT + (255,), width=dp(2.5))
    d.ellipse([xp - dp(6), py - dp(6), xp + dp(6), py + dp(6)], fill=ACCENT + (255,))
    fs = font("regular", 12)
    text(ov, (x0, py + dp(12)), "1:24", fs, DIM)
    text(ov, (x1, py + dp(12)), "3:41", fs, DIM, anchor_right=True)
    cy = py + dp(84)
    icon(ov, "shuffle", dp(48), cy, dp(20), SILVER)
    icon(ov, "prev", W / 2 - dp(92), cy, dp(28), STARLIGHT)
    d.ellipse([W / 2 - dp(36), cy - dp(36), W / 2 + dp(36), cy + dp(36)], fill=ACCENT + (255,))
    icon(ov, "pause", W / 2, cy, dp(28), ACCENT_INK)
    icon(ov, "next", W / 2 + dp(92), cy, dp(28), STARLIGHT)
    icon(ov, "repeat", W - dp(48), cy, dp(20), SILVER)
    for i, k in enumerate(("lyrics", "cast", "queue")):
        icon(ov, k, W / 2 + (i - 1) * dp(110), H - dp(64), dp(20), SILVER)
    d.rounded_rectangle([W / 2 - dp(54), H - dp(12), W / 2 + dp(54), H - dp(8)], dp(2), fill=STARLIGHT + (200,))
    return flatten(c, ov)


def screen_settings():
    c = scene_settings()
    ov = overlay(c)
    status_bar(ov)
    eyebrow(ov, (dp(20), dp(70)), "Sonara")
    text(ov, (dp(18), dp(88)), "Settings", font("regular", 36), STARLIGHT, track=0.012)
    c = flatten(c, ov)
    groups = [("Appearance", [("Theme", "Space"), ("Follow system light mode", None), ("Liquid glass", None)]),
              ("Space effects", [("Black hole animation", True), ("Infalling matter and flares", True), ("Shooting stars", True),
                                 ("Twinkle", True), ("Galaxy drift", True), ("Glass refraction", True), ("Audio-reactive disk", False)])]
    y = dp(150)
    for name, rows in groups:
        ov = overlay(c)
        eyebrow(ov, (dp(28), y), name, DIM, 10)
        c = flatten(c, ov)
        y += dp(22)
        box = (dp(16), y, W - dp(16), y + dp(56) * len(rows))
        glass(c, box, dp(24), dark=0.5)
        ov = overlay(c)
        d = ImageDraw.Draw(ov)
        for i, (t, val) in enumerate(rows):
            ry = y + i * dp(56)
            if i:
                d.line([(dp(36), ry), (W - dp(36), ry)], fill=(255, 255, 255, 18), width=1)
            text(ov, (dp(36), ry + dp(17)), t, font("regular", 16), STARLIGHT)
            if isinstance(val, str):
                text(ov, (W - dp(36), ry + dp(18)), val, font("regular", 15), SILVER, anchor_right=True)
            else:
                on = bool(val)
                sx, sy = W - dp(36) - dp(48), ry + dp(14)
                d.rounded_rectangle([sx, sy, sx + dp(48), sy + dp(28)], dp(14), fill=(ACCENT + (255,)) if on else (255, 255, 255, 30),
                                    outline=None if on else (255, 255, 255, 50))
                kx = sx + (dp(34) if on else dp(14))
                d.ellipse([kx - dp(11), sy + dp(3), kx + dp(11), sy + dp(25)], fill=ACCENT_INK + (255,) if on else SILVER + (255,))
        c = flatten(c, ov)
        y = box[3] + dp(26)
    return c


def screen_sheet():
    """A bottom sheet over Home: the page dims, the sheet is the void with a glass edge."""
    c = screen_home()
    a = np.asarray(c).astype(np.float32) * 0.45
    c = Image.fromarray(a.astype(np.uint8))
    top = H - dp(430)
    box = (0, top, W, H + dp(40))
    glass(c, box, dp(30), blur=40, dark=0.30)
    ov = overlay(c)
    d = ImageDraw.Draw(ov)
    d.rounded_rectangle([W / 2 - dp(18), top + dp(10), W / 2 + dp(18), top + dp(14)], dp(2), fill=(255, 255, 255, 70))
    art = cover((dp(56), dp(56)), seed=4)
    c2 = flatten(c, ov)
    c2.paste(art, (dp(24), top + dp(34)), rr_mask(art.size, dp(12)))
    ov = overlay(c2)
    text(ov, (dp(94), top + dp(40)), "Who's They?", font("regular", 19), STARLIGHT)
    text(ov, (dp(94), top + dp(64)), "Hans Zimmer", font("regular", 14), SILVER)
    for i, t in enumerate(("Play next", "Add to queue", "Save to library", "Go to artist", "Share")):
        y = top + dp(118) + i * dp(52)
        text(ov, (dp(28), y), t, font("regular", 17), STARLIGHT)
    return flatten(c2, ov)


def board_type():
    """Typography and palette swatches."""
    c = plate_srgb(void(H, seed=51, stars=120) ** 2.2)
    ov = overlay(c)
    eyebrow(ov, (dp(24), dp(48)), "Sonara · Space · type & colour", SILVER)
    text(ov, (dp(22), dp(80)), "SF Pro Display", font("regular", 40), STARLIGHT, track=0.012)
    samples = [("Display / Regular 34 · +1.2%", "Wind-down time,", font("regular", 34), 0.012),
               ("Title / Regular 23 · +0.5%", "Sign in to YouTube Music", font("regular", 23), 0.005),
               ("Section / Medium 20", "Top Picks for You", font("medium", 20), 0.0),
               ("Body / Regular 15", "Sing like nobody's listening. Somebody probably is.", font("regular", 15), 0.0)]
    y = dp(150)
    for label, s, f, tr in samples:
        text(ov, (dp(24), y), label.upper(), font("medium", 9), DIM, track=0.2)
        text(ov, (dp(22), y + dp(16)), s, f, STARLIGHT, track=tr)
        y += f.size + dp(36)
    text(ov, (dp(24), y), "EYEBROW / MEDIUM 11 · CAPS · +22%", font("medium", 9), DIM, track=0.2)
    eyebrow(ov, (dp(24), y + dp(16)), "Your library  ·  Sonara Pass", SILVER)
    y += dp(64)
    text(ov, (dp(24), y), "COLOUR", font("medium", 9), DIM, track=0.2)
    y += dp(22)
    d = ImageDraw.Draw(ov)
    for i, (name, col, note) in enumerate(PALETTE):
        xx = dp(24) + (i % 2) * dp(178)
        yy = y + (i // 2) * dp(62)
        d.rounded_rectangle([xx, yy, xx + dp(44), yy + dp(44)], dp(12), fill=col + (255,), outline=(255, 255, 255, 40), width=2)
        text(ov, (xx + dp(54), yy + dp(4)), name, font("medium", 14), STARLIGHT)
        text(ov, (xx + dp(54), yy + dp(24)), note.split("  ")[0], font("regular", 11), SILVER)
        text(ov, (xx + dp(54), yy + dp(38)), note.split("  ")[1], font("regular", 10), DIM)
    logo(ov, W - dp(24) - dp(90), dp(70), dp(90))
    c = flatten(c, ov)
    # Glass and the accent in use.
    gb = (dp(24), H - dp(160), W - dp(24), H - dp(160) + dp(64))
    glass(c, gb, dp(32))
    ov = overlay(c)
    d = ImageDraw.Draw(ov)
    d.rounded_rectangle([gb[0] + dp(10), gb[1] + dp(10), gb[0] + dp(150), gb[3] - dp(10)], dp(22), fill=ACCENT + (255,))
    text(ov, (gb[0] + dp(36), gb[1] + dp(21)), "Primary", font("semibold", 15), ACCENT_INK)
    sx = gb[2] - dp(80)
    d.rounded_rectangle([sx, gb[1] + dp(18), sx + dp(48), gb[1] + dp(46)], dp(14), fill=ACCENT + (255,))
    d.ellipse([sx + dp(23), gb[1] + dp(21), sx + dp(45), gb[1] + dp(43)], fill=ACCENT_INK + (255,))
    d.line([(gb[0] + dp(170), gb[1] + dp(32)), (sx - dp(30), gb[1] + dp(32))], fill=(255, 255, 255, 40), width=dp(2.5))
    d.line([(gb[0] + dp(170), gb[1] + dp(32)), (gb[0] + dp(240), gb[1] + dp(32))], fill=ACCENT + (255,), width=dp(2.5))
    text(ov, (dp(26), H - dp(80)), "One accent (the disk's hot side): selected tab, progress, switches, buttons.", font("regular", 12), DIM)
    text(ov, (dp(26), H - dp(60)), "Tiles keep their own artwork colours, or sit on smoked glass.", font("regular", 12), DIM)
    return flatten(c, ov)


SCREENS = {
    "home": ("02_home.png", screen_home), "library": ("03_library.png", screen_library),
    "explore": ("04_explore.png", screen_explore), "search": ("05_search.png", screen_search),
    "player": ("06_player.png", screen_player), "settings": ("07_settings.png", screen_settings),
    "sheet": ("08_sheet.png", screen_sheet), "type": ("09_type_and_palette.png", board_type),
}

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    which = sys.argv[3:] or ["all"]
    for key, (name, fn) in SCREENS.items():
        if "all" in which or key in which:
            fn().save(os.path.join(OUT, name))
            print("wrote", name)
