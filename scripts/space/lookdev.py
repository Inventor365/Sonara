#!/usr/bin/env python3
"""Look-dev for the Space theme: shades traced black-hole LUTs into stills and loops.

    python3 scripts/space/lookdev.py <sources_dir> <out_dir> [hero|home|player|all]

<sources_dir> holds the downloaded observatory images (see assets/licenses/SPACE-CREDITS.txt).
This is the reference the phone's shader must match: the shading here only *looks things up*
in the traced tables (trace_blackhole.py) and a disk texture, exactly as the runtime does.
"""
import math
import os
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trace_blackhole as tb  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
SRC = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2] if len(sys.argv) > 2 else "."

# The disk turns slowly for the UI: the inner edge (r = 6) once in 40 s, the outer edge in ~4 min.
INNER_PERIOD_S = 40.0


def omega_ui(r):
    return (2 * math.pi / INNER_PERIOD_S) * (r / tb.R_IN) ** -1.5


# ---------------------------------------------------------------- disk texture

def disk_texture(nr=256, nphi=2048, seed=5):
    """Turbulent plasma in (r, phi), periodic in phi: filaments drawn out along the orbit."""
    rng = np.random.default_rng(seed)

    def aniso(sr, sp, amp):
        noise = rng.standard_normal((nr, nphi))
        F = np.fft.fft2(noise)
        kr = np.fft.fftfreq(nr)[:, None]
        kp = np.fft.fftfreq(nphi)[None, :]
        H = np.exp(-(kr / sr) ** 2 - (kp / sp) ** 2)
        f = np.real(np.fft.ifft2(F * H))
        return amp * (f - f.mean()) / (f.std() + 1e-9)

    big = aniso(0.020, 0.0020, 1.0)          # broad lanes
    fil = aniso(0.120, 0.0060, 0.55)         # fine filaments, long along phi
    t = 0.60 + 0.24 * big + 0.16 * fil
    # Gaps: a few darker rings, like structure in a real disk.
    rr = np.linspace(0, 1, nr)[:, None]
    t *= 1 - 0.25 * np.exp(-((rr - 0.42) / 0.03) ** 2) - 0.18 * np.exp(-((rr - 0.71) / 0.025) ** 2)
    return np.clip(t, 0.05, 1.6)


def sample_disk(tex, r, phi):
    nr, nphi = tex.shape
    ri = (r - tb.R_IN) / (tb.R_OUT - tb.R_IN) * (nr - 1)
    pi = np.mod(phi, 2 * np.pi) / (2 * np.pi) * nphi
    return map_coordinates(tex, [ri, pi], order=1, mode="grid-wrap")


def temperature(r):
    """Hot at the inner edge, cooling outward (a thin-disk profile, kept bright at the ISCO)."""
    T = (r / tb.R_IN) ** -0.75 * (1 - 0.55 * np.sqrt(tb.R_IN / np.maximum(r, tb.R_IN))) ** 0.25
    return T / T_MAX


# The profile's peak over the disk (the phone's shader divides by the same constant).
_rs = np.linspace(tb.R_IN, tb.R_OUT, 20001)
T_MAX = float(((_rs / tb.R_IN) ** -0.75 * (1 - 0.55 * np.sqrt(tb.R_IN / _rs)) ** 0.25).max())


def ramp(t):
    """Observed temperature (0..~1.4) -> colour: deep red, amber, warm white, white, blue-white."""
    stops = [(0.00, (0.25, 0.015, 0.00)), (0.30, (0.80, 0.14, 0.015)), (0.55, (1.00, 0.42, 0.07)),
             (0.78, (1.00, 0.74, 0.40)), (0.98, (1.00, 0.93, 0.82)), (1.18, (0.94, 0.96, 1.00)),
             (1.45, (0.76, 0.85, 1.00))]
    xs = np.array([s[0] for s in stops])
    out = np.zeros(t.shape + (3,))
    for c in range(3):
        out[..., c] = np.interp(t, xs, [s[1][c] for s in stops])
    return out


# ---------------------------------------------------------------- sky

class Sky:
    """The ESO Milky Way panorama (CC BY 4.0, ESO/S. Brunier), regraded to a neutral deep black,
    plus a fine procedural star layer defined on directions — both sampled through the lens."""

    def __init__(self, lon_deg=-40.0, lat_deg=24.0, roll_deg=-32.0, gain=0.55, star_density=0.06):
        lin = self._glow()
        # Neutral blacks: no blue-grey lift; pull the floor to zero, keep star colour, calm the haze.
        lum = lin.mean(-1, keepdims=True)
        lin = np.clip(lin - 0.004, 0, None)
        lin = lum * 0.30 + lin * 0.70
        self.pano = lin * gain
        self.density = star_density
        # Camera frame in galactic coordinates: forward = (lon, lat), rolled about it.
        lo, la, ro = (math.radians(a) for a in (lon_deg, lat_deg, roll_deg))
        f = np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)])
        up0 = np.array([0.0, 0.0, 1.0])
        right = np.cross(f, up0); right /= np.linalg.norm(right)
        up = np.cross(right, f)
        right, up = right * math.cos(ro) + up * math.sin(ro), -right * math.sin(ro) + up * math.cos(ro)
        self.basis = (right, up, f)

    @staticmethod
    def _glow():
        """The panorama's diffuse light only (Milky Way, dust lanes): its stars are filtered out, because
        at this field of view they would be soft 3x-magnified blobs. Point stars come from stars()."""
        cache = os.path.join(OUT, "eso0932a_glow.npy")
        if os.path.exists(cache):
            return np.load(cache)
        from scipy.ndimage import median_filter
        im = np.asarray(Image.open(os.path.join(SRC, "eso0932a.jpg")).convert("RGB")).astype(np.float32) / 255
        glow = np.stack([median_filter(im[..., c], size=7, mode="wrap") for c in range(3)], -1)
        glow = gaussian_filter(glow, (1.2, 1.2, 0)) ** 2.2
        np.save(cache, glow)
        return glow

    def dirs_to_lonlat(self, dx, dy, dz):
        right, up, f = self.basis
        # Camera looks along -z: image x -> right, y -> up, -z -> forward.
        gx = dx * right[0] + dy * up[0] - dz * f[0]
        gy = dx * right[1] + dy * up[1] - dz * f[1]
        gz = dx * right[2] + dy * up[2] - dz * f[2]
        return np.arctan2(gy, gx), np.arcsin(np.clip(gz, -1, 1))

    def sample(self, dx, dy, dz, px_angle):
        lon, lat = self.dirs_to_lonlat(dx, dy, dz)
        H, W = self.pano.shape[:2]
        u = (0.5 - lon / (2 * math.pi)) % 1.0 * (W - 1)
        v = np.clip(0.5 - lat / math.pi, 0, 1) * (H - 1)
        col = np.stack([map_coordinates(self.pano[..., c], [v, u], order=1, mode="grid-wrap") for c in range(3)], -1)
        return col + self.stars(lon, lat, px_angle)

    def stars(self, lon, lat, px_angle, cell_deg=0.11):
        """Stars in direction cells: each cell has one star or none, at a hashed position, with a
        hashed magnitude and colour temperature. Point-like, so lensing stretches them into arcs."""
        cell = math.radians(cell_deg)
        gx, gy = lon / cell, lat / cell
        out = np.zeros(lon.shape + (3,))
        temps = np.array([[0.70, 0.80, 1.00], [0.85, 0.90, 1.00], [1.00, 1.00, 1.00], [1.00, 0.93, 0.80], [1.00, 0.80, 0.58]])
        for ox in (0, 1):
            for oy in (0, 1):
                cx = np.floor(gx) + ox - 0.5
                cy = np.floor(gy) + oy - 0.5
                h = np.sin(cx * 127.1 + cy * 311.7) * 43758.5453
                h = h - np.floor(h)
                h2 = np.sin(cx * 269.5 + cy * 183.3) * 43758.5453
                h2 = h2 - np.floor(h2)
                h3 = np.sin(cx * 419.2 + cy * 371.9) * 43758.5453
                h3 = h3 - np.floor(h3)
                present = h < self.density
                sx, sy = cx + 0.2 + 0.6 * h2, cy + 0.2 + 0.6 * h3
                d2 = (((gx - sx) * np.cos(lat)) ** 2 + (gy - sy) ** 2) * cell * cell
                sigma = px_angle * 0.65
                mag = (h2 * 13.7 + h3 * 7.1) % 1.0
                bright = np.where(present, 2.512 ** (-mag ** 0.5 * 7.0) * 3.0, 0)
                core = np.exp(-d2 / (2 * sigma * sigma)) * bright
                tcol = temps[np.clip((h3 * 5).astype(int), 0, 4)]
                out += core[..., None] * tcol
        return out


# ---------------------------------------------------------------- shading

def shade(L, sky, t, px_angle, tint=None, energy=0.0, events=None):
    """One frame: disk, shadow, photon ring and lensed sky, in linear light (not tonemapped)."""
    st, r, phi, g, rmin = L["status"], L["r"], L["phi"], L["g"], L["rmin"]
    img = sky.sample(L["dx"], L["dy"], L["dz"], px_angle)
    img[st == 2] = 0.0                                                   # the shadow: pure black

    disk = st == 1
    if disk.any():
        rd, pd, gd = r[disk], phi[disk], g[disk]
        tex = sample_disk(DISK_TEX, rd, pd - omega_ui(rd) * t)           # Keplerian, differential
        T = temperature(rd)
        tobs = np.clip(T * gd * 1.05, 0, 1.6)
        col = ramp(tobs)
        if tint is not None:
            col = col * (1 - 0.18) + col * np.asarray(tint)[None, :] * 0.18 * 1.6
        edge = np.clip((tb.R_OUT - rd) / 9.0, 0, 1) ** 2.2 * np.clip((rd - tb.R_IN) / 0.35, 0, 1)
        inten = gd ** 4 * T ** 2.6 * tex * edge * (2.6 + 0.6 * energy)
        # Light from the far side, lensed over and under: a touch dimmer with each extra wrap.
        inten = inten * np.where(L["order"][disk] >= 1, 0.85, 1.0)
        img[disk] = img[disk] * (1 - np.clip(inten * 1.5, 0, 1))[:, None] + col * inten[:, None]

    # The photon ring: light that skimmed the photon sphere (r_min -> 3) on its way out.
    ring = np.exp(-((rmin - 3.03) / 0.05) ** 2) * (st != 2)
    if disk.any():
        side = np.sign(np.nanmean(np.where(disk & (L["X"] < 0), g, np.nan)) - np.nanmean(np.where(disk & (L["X"] > 0), g, np.nan)))
    else:
        side = 1
    beam = 1 + 0.55 * np.clip(-side * L["X"] / 6.0, -1, 1)
    img += ring[..., None] * beam[..., None] * np.array([1.0, 0.88, 0.70]) * 2.2
    if events:
        ev = events_light(L, t, events)
        img += ev[..., None] * np.array([1.0, 0.86, 0.66])
    return img


def meteor(img, t, t0, start, end, dur=0.6, width=1.6):
    """A shooting star in screen space: a thin bright head, a tapered fading tail. Linear light, in place."""
    u = (t - t0) / dur
    if u <= 0 or u >= 1.25:
        return
    H, W = img.shape[:2]
    sx, sy = start
    ex, ey = end
    hx, hy = sx + (ex - sx) * min(u, 1), sy + (ey - sy) * min(u, 1)
    L = math.hypot(ex - sx, ey - sy)
    dx, dy = (ex - sx) / L, (ey - sy) / L
    tail = L * 0.45 * min(1, u * 2.2)
    x0, x1 = int(max(0, min(hx, hx - dx * tail) - 8)), int(min(W, max(hx, hx - dx * tail) + 8))
    y0, y1 = int(max(0, min(hy, hy - dy * tail) - 8)), int(min(H, max(hy, hy - dy * tail) + 8))
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float64)
    along = (hx - xx) * dx + (hy - yy) * dy                 # distance behind the head
    perp = np.abs((xx - hx) * dy - (yy - hy) * dx)
    k = np.clip(along / max(1, tail), 0, 1)
    fade = 1.0 if u < 1 else max(0.0, 1 - (u - 1) / 0.25)
    w = np.exp(-(perp / (width * (1 - 0.7 * k))) ** 2) * (1 - k) ** 2 * (along >= -1) * (along <= tail) * fade
    head = np.exp(-((xx - hx) ** 2 + (yy - hy) ** 2) / (2 * width ** 2)) * 3.0 * fade
    img[y0:y1, x0:x1] += (w * 1.4 + head)[..., None] * np.array([0.92, 0.95, 1.0])


# ---------------------------------------------------------------- matter falling in, and a tidal flare

def _wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


class Clump:
    """A small glowing clump spiralling in over `dur` seconds, from r0 to the ISCO. It lives in the
    disk plane, so it is drawn through the same LUT as the disk and lenses exactly as the disk does
    (its light shows in the band over the top and the ring underneath too)."""

    def __init__(self, t0, dur, r0, phi0, size=1.0):
        self.t0, self.dur, self.r0, self.phi0, self.size = t0, dur, r0, phi0, size
        ts = np.linspace(0, 1, 400)
        rs = self.radius(ts)
        self._phi = phi0 + np.concatenate([[0], np.cumsum(omega_ui(rs[:-1]) * np.diff(ts) * dur)])

    def radius(self, u):
        return self.r0 - (self.r0 - (tb.R_IN + 0.15)) * np.asarray(u) ** 1.7

    def at(self, t):
        u = (t - self.t0) / self.dur
        if u <= 0 or u >= 1:
            return None
        return float(self.radius(u)), float(np.interp(u, np.linspace(0, 1, 400), self._phi)), u

    def light(self, r, phi, t):
        p = self.at(t)
        if p is None:
            return 0.0
        rc, pc, u = p
        env = np.clip(u / 0.12, 0, 1) * np.clip((1 - u) / 0.25, 0, 1) ** 1.3
        sr = 0.22 * self.size
        ss = (0.35 + 2.6 * u ** 1.5) * self.size          # tidally stretched along the orbit as it nears
        d = np.exp(-((r - rc) / sr) ** 2 - (r * _wrap(phi - pc) / ss) ** 2)
        redden = np.sqrt(max(0.0, 1 - 3 / rc)) / np.sqrt(1 - 3 / self.r0)
        return d * env * 3.2 * redden


class TidalStream:
    """A star torn apart: a faint ribbon of debris wraps along the disk, brightens, then fades."""

    def __init__(self, t0, dur, r0, phi0):
        self.t0, self.dur, self.r0, self.phi0 = t0, dur, r0, phi0

    def light(self, r, phi, t):
        u = (t - self.t0) / self.dur
        if u <= 0 or u >= 1:
            return 0.0
        head = self.phi0 + omega_ui(self.r0) * (t - self.t0) * 1.4
        length = 0.4 + 3.6 * u ** 0.7                       # radians of arc the debris spans
        a = np.mod(head - phi, 2 * np.pi)                   # how far behind the head this pixel is
        inside = a < length
        rs = self.r0 - 2.2 * (a / 3.6) - 0.9 * u            # the trailing debris sits a little further in
        w = np.exp(-((r - rs) / (0.40 + 0.40 * a)) ** 2) * np.exp(-a / max(0.3, length) * 2.2) * inside
        env = np.sin(np.pi * u) ** 1.6
        return w * env * 0.75


def events_light(L, t, events):
    st = L["status"]
    disk = st == 1
    out = np.zeros(st.shape)
    if not events or not disk.any():
        return out
    r, phi = L["r"][disk], L["phi"][disk]
    acc = np.zeros(r.shape)
    for e in events:
        acc = acc + e.light(r, phi - 0.0, t)
    out[disk] = acc * L["g"][disk] ** 3
    return out


def finish(img, px_scale=1.0, seed=0, grain=0.010):
    """Bloom on the bright side, a filmic curve, gamma, and fine film grain."""
    lum = img.max(-1)
    bright = np.clip(img - 0.85, 0, None) * (lum > 0.85)[..., None]
    bloom = sum(w * np.stack([gaussian_filter(bright[..., c], s * px_scale) for c in range(3)], -1)
                for s, w in ((3, 0.45), (14, 0.30), (48, 0.22)))
    x = img + bloom
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    y = np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0, 1)
    y = y ** (1 / 2.2)
    rng = np.random.default_rng(seed)
    y = y + (rng.random(y.shape[:2])[..., None] - 0.5) * grain
    return np.clip(y, 0, 1)


def trace_view(cam, W, H, cx, cy, px_per_m, log=print):
    """Traces every pixel of a W x H view whose hole sits at pixel (cx, cy), px_per_m pixels per M."""
    xs = (np.arange(W) + 0.5 - cx) / px_per_m
    ys = -(np.arange(H) + 0.5 - cy) / px_per_m
    X, Y = np.meshgrid(xs, ys)
    L = tb.trace(cam, X, Y, log=log)
    L["X"], L["Y"] = X, Y
    return L


def save(name, img):
    Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, name))
    print("wrote", name)


DISK_TEX = disk_texture()


def hero(size=1600, half_m=24.0):
    cam = tb.Camera(80, 8)
    path = os.path.join(OUT, "lut_hero.npz")
    if os.path.exists(path):
        L = dict(np.load(path))
    else:
        L = trace_view(cam, size, size, size / 2, size / 2, size / (2 * half_m))
        np.savez_compressed(path, **L)
    sky = Sky()
    pxa = math.atan(1 / (size / (2 * half_m)) / 80)
    save("01_hero_blackhole.png", finish(shade(L, sky, 12.0, pxa), size / 1600))
    return L


HERO_EVENTS = [
    Clump(-14.0, 44.0, 17.0, 0.6), Clump(-2.0, 38.0, 15.0, 3.4, 0.8), Clump(-30.0, 52.0, 19.0, 5.1, 1.1),
    TidalStream(7.0, 15.0, 15.5, 1.2),
]
LOOP_LEN, LOOP_XFADE, LOOP_FPS = 24.0, 2.0, 24


def _loop_frame(i):
    L, sky, pxa = _LOOP_STATE
    t = 4.0 + i / LOOP_FPS
    img = shade(L, sky, t, pxa, events=HERO_EVENTS)
    meteor(img, t, 9.0, (130, 120), (560, 330), dur=0.55)
    out = finish(img, 1.0, seed=i)
    small = Image.fromarray((out * 255 + 0.5).astype(np.uint8)).resize((800, 800), Image.LANCZOS)
    return np.asarray(small).astype(np.float32)


def hero_loop():
    """A seamless loop of the hero: real speed (inner edge once in 40 s), the last LOOP_XFADE seconds
    dissolved into the first. Events are bunched into the clip to show them; in the app they are rare."""
    global _LOOP_STATE
    from multiprocessing import Pool
    import subprocess
    import tempfile
    L = dict(np.load(os.path.join(OUT, "lut_hero.npz")))
    sky = Sky()
    _LOOP_STATE = (L, sky, math.atan(1 / (1600 / 48.0) / 80))
    n = int(LOOP_LEN * LOOP_FPS)
    nx = int(LOOP_XFADE * LOOP_FPS)
    with Pool(64) as pool:
        frames = pool.map(_loop_frame, range(n + nx), chunksize=2)
    tmp = tempfile.mkdtemp(dir=OUT)
    for i in range(n):
        f = frames[i]
        if i < nx:
            a = (i + 0.5) / nx
            f = frames[n + i] * (1 - a) + f * a
        Image.fromarray(np.clip(f, 0, 255).astype(np.uint8)).save(os.path.join(tmp, f"f{i:04d}.png"))
    Image.fromarray(frames[int(9.3 * LOOP_FPS) - int(4 * LOOP_FPS)].astype(np.uint8)).save(os.path.join(OUT, "01b_hero_meteor_frame.png"))
    Image.fromarray(frames[int(15 * LOOP_FPS) - int(4 * LOOP_FPS)].astype(np.uint8)).save(os.path.join(OUT, "01c_hero_tidal_frame.png"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(LOOP_FPS), "-i", os.path.join(tmp, "f%04d.png"),
                    "-c:v", "libx264", "-preset", "slow", "-crf", "15", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    os.path.join(OUT, "10_hero_loop.mp4")], check=True)
    subprocess.run(["rm", "-rf", tmp])
    print("wrote 10_hero_loop.mp4")


# Phone layouts (1152 x 2560): where the hole sits and how many pixels one M spans.
VIEWS = {
    # Home: large, partly off the right edge, below the toolbar, clear of the greeting.
    "home": dict(cx=1010.0, cy=800.0, px_per_m=26.0, elevation=8.0),
    # Player: the art covers the shadow; the lensed band and the ring under it frame the art.
    "player": dict(cx=576.0, cy=860.0, px_per_m=60.0, elevation=8.0),
}


def traced(view, W=1152, H=2560):
    path = os.path.join(OUT, f"lut_{view}.npz")
    if os.path.exists(path):
        return dict(np.load(path))
    v = VIEWS[view]
    L = trace_view(tb.Camera(80, v["elevation"]), W, H, v["cx"], v["cy"], v["px_per_m"])
    np.savez_compressed(path, **L)
    return L


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    what = sys.argv[3] if len(sys.argv) > 3 else "hero"
    if what in ("hero", "all"):
        hero()
    if what == "loop":
        hero_loop()
    if what.startswith("trace_"):
        traced(what[len("trace_"):])
