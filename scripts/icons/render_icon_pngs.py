#!/usr/bin/env python3
"""Renders the app's adaptive launcher icons to PNG, for the README and the website.

    python3 scripts/icons/render_icon_pngs.py <out_dir> [size]

Needs cairosvg (pip install cairosvg). Each icon's background and foreground VectorDrawables are
converted to SVG (paths, fills, strokes and the linear and radial gradients these icons use), drawn
on the 108-unit adaptive canvas, cropped to the 72 units a launcher shows, and masked to a circle,
as most launchers present them.
"""
import io
import os
import re
import sys
import xml.etree.ElementTree as ET

import cairosvg
from PIL import Image, ImageDraw

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../app/src/main/res")
A = "{http://schemas.android.com/apk/res/android}"

ICONS = [
    ("sonara", "ic_launcher_background", "ic_launcher_foreground"),
    ("vice", "ic_theme_vice_background", "ic_theme_vice_foreground"),
    ("doom", "ic_theme_doom_background", "ic_theme_doom_foreground"),
    ("winter-night", "ic_theme_winter_background", "ic_theme_winter_foreground"),
    ("winter-day", "ic_theme_winter_light_background", "ic_theme_winter_light_foreground"),
    ("space", "ic_theme_space_background", "ic_theme_space_foreground"),
]


def color(c):
    """#AARRGGBB / #RRGGBB / #RGB -> (svg colour, opacity)."""
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) == 8:
        return "#" + c[2:], int(c[:2], 16) / 255
    return "#" + c, 1.0


def vd_to_svg(path, prefix):
    root = ET.parse(path).getroot()
    vw = float(root.get(A + "viewportWidth"))
    vh = float(root.get(A + "viewportHeight"))
    defs, body = [], []
    gid = 0
    for p in root.iter("path"):
        d = p.get(A + "pathData")
        attrs = {"d": d, "fill": "none"}
        for kind in ("fill", "stroke"):
            val = p.get(A + kind + "Color")
            grad = None
            for aapt in p:
                if aapt.tag.endswith("attr") and aapt.get("name") == "android:" + kind + "Color":
                    grad = aapt.find("gradient")
            if grad is not None:
                gid += 1
                gname = f"{prefix}{gid}"  # unique across layers: both layers count from 1
                stops = "".join(
                    f'<stop offset="{it.get(A + "offset")}" stop-color="{color(it.get(A + "color"))[0]}" '
                    f'stop-opacity="{color(it.get(A + "color"))[1]:.4f}"/>'
                    for it in grad.findall("item")
                )
                if grad.get(A + "type") == "radial":
                    defs.append(
                        f'<radialGradient id="{gname}" gradientUnits="userSpaceOnUse" cx="{grad.get(A + "centerX")}" '
                        f'cy="{grad.get(A + "centerY")}" r="{grad.get(A + "gradientRadius")}">{stops}</radialGradient>'
                    )
                else:
                    defs.append(
                        f'<linearGradient id="{gname}" gradientUnits="userSpaceOnUse" x1="{grad.get(A + "startX")}" '
                        f'y1="{grad.get(A + "startY")}" x2="{grad.get(A + "endX")}" y2="{grad.get(A + "endY")}">{stops}</linearGradient>'
                    )
                attrs[kind] = f"url(#{gname})"
            elif val:
                c, a = color(val)
                attrs[kind] = c
                attrs[kind + "-opacity"] = f"{a:.4f}"
        if p.get(A + "strokeWidth"):
            attrs["stroke-width"] = p.get(A + "strokeWidth")
        if p.get(A + "strokeLineCap"):
            attrs["stroke-linecap"] = p.get(A + "strokeLineCap")
        if p.get(A + "fillAlpha"):
            attrs["fill-opacity"] = p.get(A + "fillAlpha")
        if p.get(A + "fillType") == "evenOdd":
            attrs["fill-rule"] = "evenodd"
        body.append("<path " + " ".join(f'{k}="{v}"' for k, v in attrs.items()) + "/>")
    return vw, vh, f'<defs>{"".join(defs)}</defs>{"".join(body)}'


def render(name, bg, fg, size):
    parts = []
    for i, layer in enumerate((bg, fg)):
        vw, vh, inner = vd_to_svg(os.path.join(RES, "drawable", layer + ".xml"), f"l{i}g")
        parts.append(inner)
    # The launcher shows the middle 72 of the 108 units.
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="18 18 72 72">'
           + "".join(f"<g>{p}</g>" for p in parts) + "</svg>")
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size * 4 - 1, size * 4 - 1], fill=255)
    im.putalpha(mask.resize((size, size), Image.LANCZOS))
    return im


if __name__ == "__main__":
    out = sys.argv[1]
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 256
    os.makedirs(out, exist_ok=True)
    for name, bg, fg in ICONS:
        im = render(name, bg, fg, size)
        im.save(os.path.join(out, f"icon-{name}.png"), optimize=True)
        print("wrote", f"icon-{name}.png")
