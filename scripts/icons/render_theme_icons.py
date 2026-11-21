#!/usr/bin/env python3
"""Theme launcher icons, v2: the Sonara mark exactly as ic_launcher_foreground draws it — the same
three arcs, stroke width and position — recoloured, on a themed background with a faint texture.

Writes, per theme T: drawable/ic_theme_T_background.xml, drawable/ic_theme_T_foreground.xml,
drawable/ic_theme_T_preview.xml (both flattened, for Compose previews) and mipmap-anydpi/ic_theme_T.xml
(adaptive icon whose monochrome layer is the plain mark, for themed icons).
"""
import math
import random

import os
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../app/src/main/res")

# The mark, verbatim from ic_launcher_foreground.xml: inner, middle, outer.
ARCS = [
    "M40.46,39.34A22,22 0 0 0 67.54,39.34",
    "M31.84,50.37A36,36 0 0 0 76.16,50.37",
    "M23.22,61.40A50,50 0 0 0 84.78,61.40",
]
# Horizontal extent of each arc, for its stroke gradient.
SPAN = [(40.46, 67.54), (31.84, 76.16), (23.22, 84.78)]
STROKE = 8.5

HEAD = """<?xml version="1.0" encoding="utf-8"?>
<!-- {note} -->
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:aapt="http://schemas.android.com/aapt"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
"""


def gradient(attr, kind, items, **geo):
    g = " ".join(f'android:{k}="{v}"' for k, v in geo.items())
    s = f'        <aapt:attr name="android:{attr}">\n            <gradient android:type="{kind}" {g}>\n'
    for off, c in items:
        s += f'                <item android:offset="{off}" android:color="{c}" />\n'
    return s + "            </gradient>\n        </aapt:attr>\n"


def rect(fill_items=None, color=None, x0=0, y0=0, w=108, h=108, kind="linear", **geo):
    d = f"M{x0},{y0}h{w}v{h}h-{w}z"
    if color:
        return f'    <path android:pathData="{d}" android:fillColor="{color}" />\n'
    return f'    <path android:pathData="{d}">\n' + gradient("fillColor", kind, fill_items, **geo) + "    </path>\n"


def circle(cx, cy, r, color=None, items=None):
    d = f"M{cx},{cy}m-{r},0a{r},{r} 0 1,1 {2*r},0a{r},{r} 0 1,1 -{2*r},0"
    if color:
        return f'    <path android:pathData="{d}" android:fillColor="{color}" />\n'
    return f'    <path android:pathData="{d}">\n' + gradient("fillColor", "radial", items, centerX=cx, centerY=cy, gradientRadius=r) + "    </path>\n"


def mark(arc_stops, glow=None, glow_width=15.0):
    """The three arcs, each stroked with its own left-to-right gradient; an optional soft glow is
    the same arc drawn wider and faint behind it — the outline itself never changes."""
    out = ""
    if glow:
        for d in ARCS:
            out += (f'    <path android:pathData="{d}" android:strokeWidth="{glow_width}" android:strokeLineCap="round" '
                    f'android:strokeColor="{glow}" android:fillColor="#00000000" />\n')
    for d, (x0, x1), stops in zip(ARCS, SPAN, arc_stops):
        out += (f'    <path android:pathData="{d}" android:strokeWidth="{STROKE}" android:strokeLineCap="round" '
                f'android:fillColor="#00000000">\n'
                + gradient("strokeColor", "linear", stops, startX=x0, startY=50, endX=x1, endY=50)
                + "    </path>\n")
    return out


def hairlines(color, step, y0=0, y1=108, width=0.35):
    return "".join(f'    <path android:pathData="M0,{y:.1f}H108" android:strokeWidth="{width}" android:strokeColor="{color}" />\n'
                   for y in [y0 + i * step for i in range(int((y1 - y0) / step) + 1)])


def stars(seed, count, color, area=(8, 8, 100, 46), rmin=0.35, rmax=0.8):
    rnd = random.Random(seed)
    out = ""
    for _ in range(count):
        x = rnd.uniform(area[0], area[2]); y = rnd.uniform(area[1], area[3]); r = rnd.uniform(rmin, rmax)
        out += circle(round(x, 2), round(y, 2), round(r, 2), color=color)
    return out


THEMES = {}

# Vice: neon dusk. A sunset sky (indigo to magenta to orange), a faint receding grid at the foot,
# and the arcs in cyan, sunset orange and hot pink with a soft neon glow.
THEMES["vice"] = dict(
    note="Vice icon: the Sonara mark recoloured in neon on a dusk sky. Original artwork; geometry unchanged.",
    bg=rect([(0, "#FF1B0B33"), (0.55, "#FF5A1259"), (0.85, "#FFC2306F"), (1, "#FFF06A45")], startX=54, startY=0, endX=54, endY=108)
    + "".join(f'    <path android:pathData="M0,{y}H108" android:strokeWidth="0.5" android:strokeColor="#22FF3EA5" />\n' for y in (84, 90, 98, 108))
    + "".join(f'    <path android:pathData="M54,80L{x},108" android:strokeWidth="0.5" android:strokeColor="#1A2DE2E6" />\n' for x in (-30, 6, 30, 54, 78, 102, 138)),
    fg=mark([
        [(0, "#FFA8FBFC"), (1, "#FF2DE2E6")],
        [(0, "#FFFFC371"), (1, "#FFFF8A3D")],
        [(0, "#FFFF7AC6"), (1, "#FFFF3EA5")],
    ]),
)

# Doom: forged iron. Gunmetal with brushed hairlines and an emerald glow at the heart, the arcs in
# emerald from pale to deep.
THEMES["doom"] = dict(
    note="Doom icon: the Sonara mark recoloured in emerald on forged gunmetal. Original artwork; geometry unchanged.",
    bg=rect([(0, "#FF333B42"), (0.5, "#FF161B1F"), (1, "#FF0B0E10")], startX=0, startY=0, endX=108, endY=108)
    + hairlines("#10FFFFFF", 2.4)
    + circle(54, 54, 40, items=[(0, "#552BE07F"), (0.55, "#162BE07F"), (1, "#002BE07F")]),
    fg=mark([
        [(0, "#FFD2FFE4"), (1, "#FF8CFFC0")],
        [(0, "#FF8CFFC0"), (1, "#FF2BE07F")],
        [(0, "#FF2BE07F"), (1, "#FF0FA45A")],
    ]),
)

# Winter, polar night: deep navy to black, a faint aurora band and a few stars; icy white to
# glacier-blue arcs.
THEMES["winter"] = dict(
    note="Winter icon (polar night): the Sonara mark in ice on a night sky with a faint aurora. Original artwork; geometry unchanged.",
    bg=rect([(0, "#FF0D2142"), (0.6, "#FF071229"), (1, "#FF03060F")], startX=54, startY=0, endX=54, endY=108)
    + rect([(0, "#0036F1B4"), (0.35, "#3336F1B4"), (0.65, "#2A3FB8E8"), (1, "#008B6CF2")], x0=0, y0=14, w=108, h=26,
           startX=0, startY=27, endX=108, endY=27)
    + stars(7, 14, "#CCFFFFFF", area=(10, 6, 98, 32))
    + stars(11, 6, "#88FFFFFF", area=(10, 80, 98, 100), rmin=0.3, rmax=0.55),
    fg=mark([
        [(0, "#FFFFFFFF"), (1, "#FFEAF7FF")],
        [(0, "#FFD8F0FF"), (1, "#FFA9DDFB")],
        [(0, "#FFA9DDFB"), (1, "#FF6FB8EE")],
    ]),
)

# Winter, day: snow white to pale glacier blue with a faint frost, the arcs from glacier blue to
# deep navy.
THEMES["winter_light"] = dict(
    note="Winter icon (day): the Sonara mark in glacier blues on snow. Original artwork; geometry unchanged.",
    bg=rect([(0, "#FFFFFFFF"), (0.6, "#FFEAF5FD"), (1, "#FFCFE7F8")], startX=54, startY=0, endX=54, endY=108)
    + "".join(
        f'    <path android:pathData="M{cx},{cy}m-{r},0l{2*r},0M{cx},{cy}m0,-{r}l0,{2*r}M{cx},{cy}m-{r*0.7:.2f},-{r*0.7:.2f}l{r*1.4:.2f},{r*1.4:.2f}M{cx},{cy}m{r*0.7:.2f},-{r*0.7:.2f}l-{r*1.4:.2f},{r*1.4:.2f}" '
        f'android:strokeWidth="0.45" android:strokeLineCap="round" android:strokeColor="#3D8FC7EA" />\n'
        for cx, cy, r in ((26, 24, 3.2), (84, 22, 2.4), (20, 86, 2.6), (88, 88, 3.4))),
    fg=mark([
        [(0, "#FF9BD3F5"), (1, "#FF6FB8EE")],
        [(0, "#FF5CA4E3"), (1, "#FF3C8BD9")],
        [(0, "#FF2D6FB8"), (1, "#FF1C4A86")],
    ]),
)


def ellipse(cx, cy, rx, ry, stroke, width):
    d = f"M{cx - rx},{cy}a{rx},{ry} 0 1,0 {2 * rx},0a{rx},{ry} 0 1,0 -{2 * rx},0"
    return f'    <path android:pathData="{d}" android:strokeWidth="{width}" android:strokeColor="{stroke}" android:fillColor="#00000000" />\n'


# Space: the true deep void, a few faint stars of mixed temperature, and a thin photon ring behind
# the mark — the black hole's edge, the one trace of it. The mark is starlight, warming to the pale
# white-gold of the disk's hot side, with a faint warm glow from within. Geometry unchanged.
THEMES["space"] = dict(
    note="Space icon: the Sonara mark in starlight and the disk's pale gold, with a faint warm glow, over the void and a thin photon ring. Original artwork; geometry unchanged.",
    bg=rect(fill_items=[(0, "#FF0B0D13"), (0.55, "#FF05070C"), (1, "#FF020306")], kind="radial",
            centerX=54, centerY=50, gradientRadius=78)
    + stars(23, 14, "#B3FFFFFF", area=(6, 6, 102, 102), rmin=0.22, rmax=0.5)
    + stars(29, 4, "#99BFD3FF", area=(6, 6, 102, 102), rmin=0.25, rmax=0.55)
    + stars(31, 3, "#99FFE6C8", area=(6, 6, 102, 102), rmin=0.25, rmax=0.5)
    + circle(54, 52, 33, items=[(0, "#00000000"), (0.80, "#00000000"), (0.93, "#1FF4E3C1"), (1, "#00F4E3C1")])
    + ellipse(54, 52, 30.5, 30.5, "#59F4E3C1", 0.55)
    # The warm glow from within: a soft radial light behind the mark (a wider stroke would read
    # as a hard outline, since a vector cannot blur).
    + circle(54, 50, 27, items=[(0, "#33F4E3C1"), (0.55, "#14F4E3C1"), (1, "#00F4E3C1")]),
    fg=mark([
        [(0, "#FFFFFFFF"), (1, "#FFF8EEDB")],
        [(0, "#FFFFFFFF"), (1, "#FFF6E8CC")],
        [(0, "#FFFAFBFF"), (1, "#FFF4E3C1")],
    ]),
)


def vec(note, body):
    return HEAD.format(note=note) + body + "</vector>\n"


for name, t in THEMES.items():
    open(f"{RES}/drawable/ic_theme_{name}_background.xml", "w").write(vec(t["note"] + " Background layer.", t["bg"]))
    open(f"{RES}/drawable/ic_theme_{name}_foreground.xml", "w").write(vec(t["note"] + " Foreground layer.", t["fg"]))
    open(f"{RES}/drawable/ic_theme_{name}_preview.xml", "w").write(
        vec(t["note"] + " Flattened for in-app previews (Compose cannot draw adaptive icons).", t["bg"] + t["fg"]))
    open(f"{RES}/mipmap-anydpi/ic_theme_{name}.xml", "w").write(f"""<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_theme_{name}_background" />
    <foreground android:drawable="@drawable/ic_theme_{name}_foreground" />
    <monochrome android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
""")
    print("wrote", name)
