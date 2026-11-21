#!/usr/bin/env python3
"""Bakes the Space theme's runtime assets from the offline ray tracer and the observatory sources.

    python3 -I scripts/space/bake_space_assets.py <sources_dir> <cache_dir>

<sources_dir> holds the downloaded originals (credits: app/src/main/assets/licenses/SPACE-CREDITS.txt):
    eso0932a.jpg  (ESO full-sky Milky Way panorama)     heic0506a.jpg (M51, Hubble)
    heic0406a.jpg (Hubble Ultra Deep Field)              weic2205a.jpg (Cosmic Cliffs, Webb)

What the app does with them (sharedUi .../ui/theme/SpaceScene.kt): every lensing calculation is done
here. A plate holds the lensed sky, the pure-black shadow, the photon ring and the disk's glow; a
small lookup table (LUT) holds, for each texel where light came from the disk, the radius, azimuth
and redshift g where the ray crossed it (and its anti-aliased coverage). The phone's shader only
looks these up and turns the disk texture (Keplerian rotation), so the motion costs a few texture
reads per pixel of the disk, and matter falling in lenses exactly as the disk does.

LUT encoding (opaque RGB PNG, read by exact texel; RGB because Android premultiplies alpha):
    A = (phi hi, phi lo, r8)         phi = u16 / 65535 * 2 pi;   r = 6 + (r8 - 1) / 254 * 14   (r8 > 0)
    B = (g8, coverage8, far8)        g = 0.2 + g8 / 255 * 1.6;   far8 = 255 for light from the far
                                     side (lensed over the top or under: a little dimmer)
"""
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1]
CACHE = sys.argv[2]
sys.argv = [sys.argv[0], SRC, CACHE]  # lookdev reads its sources and cache from argv
sys.path.insert(0, HERE)
import lookdev as ld  # noqa: E402
import lookdev_board as board  # noqa: E402
import trace_blackhole as tb  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "../.."))
RES = os.path.join(REPO, "sharedUi/src/commonMain/composeResources/drawable")
VOID = np.array([0x04, 0x06, 0x0B]) / 255.0          # the page floor under every plate

# The scenes, in M (the hole's mass) with y DOWN the screen, and how finely each is baked.
# Home: anchored to the width; the hole sits at (0.8767 W, 0.7431 W), 26 px per M at 1152 wide.
HOME = dict(plate_w=1152, plate_h=1500, cx=1010.0, cy=856.0, ppm=26.0,
            lut=(-21.0, 5.4, -12.0, 11.0), lut_ppm=14.0, sky=dict())
# Player: anchored to the album art (13 M across); the art covers the shadow.
PLAYER = dict(region=(-11.0, 11.0, -14.0, 14.0), ppm=52.0, lut=(-11.0, 11.0, -12.0, 9.0), lut_ppm=24.0,
              sky=dict(lon_deg=60.0, lat_deg=-30.0, roll_deg=20.0, gain=0.30, star_density=0.07))


def cached(name, fn):
    path = os.path.join(CACHE, name + ".npz")
    if os.path.exists(path):
        return dict(np.load(path))
    out = fn()
    np.savez_compressed(path, **out)
    return out


def trace_grid(xs, ys_down):
    """Traces image-plane points (M, y down) through the camera used everywhere: 80 M away, 8 deg above the disk."""
    X, Yd = np.meshgrid(xs, ys_down)
    L = tb.trace(tb.Camera(80, 8.0), X, -Yd, log=lambda s: None)
    L["X"], L["Y"] = X, -Yd
    return L


def filmic(x):
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    return np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0, 1)


# Lensing of the sky is kept to the hole's surroundings: within LENS_NEAR M it is exact; it fades
# out by LENS_NEAR + LENS_FADE. At this camera distance the lens would otherwise shear stars all
# across the frame into streaks; the look wants arcs and doubled stars near the hole, round stars
# elsewhere. The app's moving stars use the same fade (SpaceScene, LENS_NEAR / LENS_FADE).
LENS_NEAR = 10.0
LENS_FADE = 14.0


def near_lens(L):
    """The escaping rays' directions, blended toward the straight-through direction away from the hole."""
    X, Y = L["X"], L["Y"]
    w = np.clip((np.hypot(X, Y) - LENS_NEAR) / LENS_FADE, 0, 1)
    w = w * w * (3 - 2 * w)
    d0 = np.stack([X, Y, np.full(X.shape, -80.0)], -1)
    d0 /= np.linalg.norm(d0, axis=-1, keepdims=True)
    d = np.stack([L["dx"], L["dy"], L["dz"]], -1)
    out = d * (1 - w)[..., None] + d0 * w[..., None]
    out /= np.linalg.norm(out, axis=-1, keepdims=True)
    return out[..., 0], out[..., 1], out[..., 2]


def plate_from(L, sky, px_angle, bloom_scale):
    """The sky through the lens, the shadow, the photon ring and the disk's time-averaged glow — no disk."""
    st = L["status"]
    dx, dy, dz = near_lens(L)
    sky_lin = sky.sample(dx, dy, dz, px_angle)
    sky_lin[st == 2] = 0.0
    # Photon ring, exactly as the look-dev shades it.
    ring = np.exp(-((L["rmin"] - 3.03) / 0.05) ** 2) * (st != 2)
    beam = 1 + 0.55 * np.clip(L["X"] / 6.0, -1, 1) * -1
    sky_lin += ring[..., None] * beam[..., None] * np.array([1.0, 0.88, 0.70]) * 2.2
    # The disk with its texture averaged round each orbit: only for the glow it casts.
    mean_tex = ld.DISK_TEX.mean(axis=1)
    disk = st == 1
    full = sky_lin.copy()
    if disk.any():
        rd, gd = L["r"][disk], L["g"][disk]
        T = ld.temperature(rd)
        col = ld.ramp(np.clip(T * gd * 1.05, 0, 1.6))
        edge = np.clip((tb.R_OUT - rd) / 9.0, 0, 1) ** 2.2 * np.clip((rd - tb.R_IN) / 0.35, 0, 1)
        tex = np.interp((rd - tb.R_IN) / (tb.R_OUT - tb.R_IN), np.linspace(0, 1, mean_tex.size), mean_tex)
        inten = gd ** 4 * T ** 2.6 * tex * edge * 2.6 * np.where(L["order"][disk] >= 1, 0.85, 1.0)
        full[disk] = full[disk] * (1 - np.clip(inten * 1.5, 0, 1))[:, None] + col * inten[:, None]
    lum = full.max(-1)
    bright = np.clip(full - 0.85, 0, None) * (lum > 0.85)[..., None]
    from scipy.ndimage import gaussian_filter
    bloom = sum(w * np.stack([gaussian_filter(bright[..., c], s * bloom_scale) for c in range(3)], -1)
                for s, w in ((3, 0.45), (14, 0.30), (48, 0.22)))
    return sky_lin + bloom


def to_srgb8(lin, seed=0, grain=0.010):
    y = filmic(lin) ** (1 / 2.2)
    rng = np.random.default_rng(seed)
    y = y + (rng.random(y.shape[:2])[..., None] - 0.5) * grain
    return np.clip(y, 0, 1)


def fade_to_void(srgb, start, end):
    """Into the page floor between rows start and end (a smoothstep), dithered."""
    h = srgb.shape[0]
    t = np.clip((np.arange(h) - start) / max(1, end - start), 0, 1)
    t = (t * t * (3 - 2 * t))[:, None, None]
    out = srgb * (1 - t) + VOID[None, None, :] * t
    rng = np.random.default_rng(7)
    return np.clip(out + (rng.random(out.shape[:2])[..., None] - 0.5) / 255 * 1.5, 0, 1)


def encode_lut(name, xs_lo, ys_lo, ss=2):
    """Bakes the disk LUT for texel centres (xs_lo, ys_lo in M, y down), supersampled ss x ss."""
    dx = (xs_lo[1] - xs_lo[0]) / ss
    dy = (ys_lo[1] - ys_lo[0]) / ss
    off = (np.arange(ss) - (ss - 1) / 2)
    xs = (xs_lo[:, None] + off[None, :] * dx).ravel()
    ys = (ys_lo[:, None] + off[None, :] * dy).ravel()
    L = cached(name + "_trace", lambda: trace_grid(xs, ys))
    H, W = ys_lo.size, xs_lo.size
    st = L["status"].reshape(H, ss, W, ss)
    hit = st == 1
    cov = hit.mean(axis=(1, 3))
    n = np.maximum(hit.sum(axis=(1, 3)), 1)
    r = (L["r"].reshape(H, ss, W, ss) * hit).sum(axis=(1, 3)) / n
    g = (L["g"].reshape(H, ss, W, ss) * hit).sum(axis=(1, 3)) / n
    ph = L["phi"].reshape(H, ss, W, ss)
    phi = np.mod(np.arctan2((np.sin(ph) * hit).sum(axis=(1, 3)), (np.cos(ph) * hit).sum(axis=(1, 3))), 2 * np.pi)
    far = ((L["order"].reshape(H, ss, W, ss) >= 1) & hit).sum(axis=(1, 3)) * 2 > hit.sum(axis=(1, 3))
    any_hit = cov > 0
    p16 = (np.round(phi / (2 * np.pi) * 65535).astype(np.int64) % 65536)
    r8 = np.where(any_hit, np.clip(np.round((r - tb.R_IN) / (tb.R_OUT - tb.R_IN) * 254) + 1, 1, 255), 0).astype(np.uint8)
    g8 = np.where(any_hit, np.clip(np.round((g - 0.2) / 1.6 * 255), 0, 255), 0).astype(np.uint8)
    A = np.stack([(p16 >> 8).astype(np.uint8), (p16 & 255).astype(np.uint8), r8], -1)
    B = np.stack([g8, np.round(cov * 255).astype(np.uint8), np.where(far & any_hit, 255, 0).astype(np.uint8)], -1)
    A[~any_hit] = 0
    Image.fromarray(A, "RGB").save(os.path.join(RES, name + "_a.png"), optimize=True)
    Image.fromarray(B, "RGB").save(os.path.join(RES, name + "_b.png"), optimize=True)
    print(f"{name}: {W} x {H} texels, disk in {cov.mean() * 100:.1f}%")


def save_webp(name, srgb, quality=90, alpha=None):
    a = (np.clip(srgb, 0, 1) * 255 + 0.5).astype(np.uint8)
    if alpha is not None:
        im = Image.fromarray(np.dstack([a, (np.clip(alpha, 0, 1) * 255 + 0.5).astype(np.uint8)]), "RGBA")
    else:
        im = Image.fromarray(a, "RGB")
    im.save(os.path.join(RES, name + ".webp"), quality=quality, method=6)
    print("wrote", name, im.size, os.path.getsize(os.path.join(RES, name + ".webp")) // 1024, "KB")


def bake_home():
    h = HOME
    ppm = h["ppm"]
    xs = (np.arange(h["plate_w"]) + 0.5 - h["cx"]) / ppm
    ys = (np.arange(h["plate_h"]) + 0.5 - h["cy"]) / ppm
    L = cached("home_plate_trace", lambda: trace_grid(xs, ys))
    sky = ld.Sky(gain=0.35, star_density=0.07)
    lin = plate_from(L, sky, math.atan(1 / ppm / 80), 0.9)
    srgb = to_srgb8(lin)
    # The greeting's side darker and cleaner, as on the board.
    yy, xx = np.mgrid[0:h["plate_h"], 0:h["plate_w"]].astype(np.float32)
    left = np.clip(1 - xx / (h["plate_w"] * 0.55), 0, 1) ** 1.6 * np.clip(1 - np.abs(yy - 576) / 520, 0, 1)
    srgb = srgb * (1 - 0.55 * left[..., None])
    srgb = fade_to_void(srgb, 1180, 1490)
    save_webp("space_home", srgb, 88)
    x0, x1, y0, y1 = h["lut"]
    lp = h["lut_ppm"]
    encode_lut("space_home_lut", np.arange(x0, x1, 1 / lp) + 0.5 / lp, np.arange(y0, y1, 1 / lp) + 0.5 / lp)
    # A still with the disk in, for the theme picker and the welcome screen.
    near = dict(L)
    near["dx"], near["dy"], near["dz"] = near_lens(L)
    full = ld.shade(near, sky, 12.0, math.atan(1 / ppm / 80))
    still = ld.finish(full, 0.9)
    still = still * (1 - 0.55 * left[..., None])
    still = fade_to_void(still, 1180, 1490)
    im = Image.fromarray((still * 255 + 0.5).astype(np.uint8)).resize((576, 750), Image.LANCZOS)
    im.save(os.path.join(RES, "space_home_still.webp"), quality=86, method=6)
    print("wrote space_home_still", os.path.getsize(os.path.join(RES, "space_home_still.webp")) // 1024, "KB")


def bake_player():
    p = PLAYER
    x0, x1, y0, y1 = p["region"]
    ppm = p["ppm"]
    xs = np.arange(x0, x1, 1 / ppm) + 0.5 / ppm
    ys = np.arange(y0, y1, 1 / ppm) + 0.5 / ppm
    L = cached("player_plate_trace", lambda: trace_grid(xs, ys))
    sky = ld.Sky(**p["sky"])
    lin = plate_from(L, sky, math.atan(1 / ppm / 80), ppm / 60 * 1.4)
    srgb = to_srgb8(lin, seed=3)
    H, W = srgb.shape[:2]
    # Soft edges into the void, for screens wider or taller than the plate.
    xe = np.clip(np.minimum(np.arange(W), W - 1 - np.arange(W)) / (0.6 * ppm), 0, 1)
    srgb = srgb * xe[None, :, None] + VOID * (1 - xe[None, :, None])
    srgb = fade_to_void(srgb, int((10.0 - y0) * ppm), H - 2)
    top = np.clip(np.arange(H) / (0.8 * ppm), 0, 1)[:, None, None]
    srgb = srgb * top + VOID * (1 - top)
    save_webp("space_player", srgb, 88)
    lx0, lx1, ly0, ly1 = p["lut"]
    lp = p["lut_ppm"]
    encode_lut("space_player_lut", np.arange(lx0, lx1, 1 / lp) + 0.5 / lp, np.arange(ly0, ly1, 1 / lp) + 0.5 / lp)


def bake_disk_texture():
    """The plasma in (r, phi): rows run from the ISCO (top) to the outer edge, columns once round."""
    rng = np.random.default_rng(5)
    nr, nphi = 160, 1024

    def aniso(lr, lp, amp):
        """Smooth noise with features ~lr rows by ~lp columns, periodic in both."""
        noise = rng.standard_normal((nr, nphi))
        kr = np.fft.fftfreq(nr)[:, None]
        kp = np.fft.fftfreq(nphi)[None, :]
        f = np.real(np.fft.ifft2(np.fft.fft2(noise) * np.exp(-(kr * lr) ** 2 - (kp * lp) ** 2)))
        return amp * (f - f.mean()) / (f.std() + 1e-9)

    big = aniso(31.0, 250.0, 1.0)            # broad lanes
    fil = aniso(5.0, 80.0, 0.55)             # fine filaments, long along the orbit
    t = 0.60 + 0.24 * big + 0.16 * fil
    rr = np.linspace(0, 1, nr)[:, None]
    t *= 1 - 0.25 * np.exp(-((rr - 0.42) / 0.03) ** 2) - 0.18 * np.exp(-((rr - 0.71) / 0.025) ** 2)
    t = np.clip(t, 0.05, 1.6) / 1.6
    g = (t * 255 + 0.5).astype(np.uint8)
    Image.fromarray(np.dstack([g, g, g]), "RGB").save(os.path.join(RES, "space_disk.webp"), quality=94, method=6)
    print("wrote space_disk", os.path.getsize(os.path.join(RES, "space_disk.webp")) // 1024, "KB")


def bake_library():
    """Library: the M51 sprite, and a planet's dark limb in front of it (its own layer). Its sky of
    faint stars is drawn by the app (a plate of near-black and dither costs more than it shows)."""
    g = board.regrade("heic0506a.jpg", crop=(0.18, 0.12, 0.78, 0.82), size=(640, 640), black=0.04, sat=0.62, gain=1.05)
    g = g * board.soft_vignette(640, 640, 1.4)[..., None]
    # Opaque, vignetted to black: drawn with a plain blend (a screen blend in its own layer looked
    # the same and cost more to draw). Alpha would triple the file: WebP keeps alpha lossless.
    save_webp("space_galaxy_m51", board.to_srgb(g), 88)
    # The limb: as on the board, a vast dark world rimmed by a thin cool atmosphere. RGBA.
    W, Hh = 1152, 700
    yy, xx = np.mgrid[0:Hh, 0:W].astype(np.float32)
    R = 3400.0
    cx, cy = W * 0.30, 300 + R                     # the limb's top at row 300 of this layer
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) - R
    planet = d < 0
    lit = np.clip((xx - W * 0.1) / W, 0, 1)
    rim = np.exp(-np.maximum(d, 0) / 10.0) * np.exp(-np.maximum(-d, 0) / 3.0) * 0.55 * (0.4 + lit)
    glow = np.exp(-np.maximum(d, 0) / 90.0) * 0.10 * (0.3 + lit)
    light = rim[..., None] * np.array([0.55, 0.74, 0.95]) + glow[..., None] * np.array([0.25, 0.45, 0.70])
    body = np.array([0.0012, 0.0016, 0.0024]) + np.exp(d / 260.0)[..., None] * np.array([0.004, 0.006, 0.010])
    rgb_lin = np.where(planet[..., None], body + light, light / np.maximum(light.max(-1, keepdims=True), 1e-6))
    alpha = np.where(planet, 1.0, np.clip(light.max(-1), 0, 1))
    rgb = board.to_srgb(rgb_lin)
    # Below the limb's top band, into the page floor (the layer is drawn over the page's top).
    t = np.clip((yy - 520) / 170, 0, 1)
    rgb = rgb * (1 - t[..., None]) + VOID * t[..., None]
    save_webp("space_library_limb", rgb, 88, alpha=alpha)


def bake_explore():
    base = board.void(1350, seed=21, stars=240) ** 2.2
    n = board.regrade("weic2205a.jpg", crop=(0.0, 0.08, 1.0, 0.92), size=(2100, 1400), black=0.01, sat=1.0, gain=1.0)
    lum = (n @ np.array([0.2126, 0.7152, 0.0722])) ** 0.8
    lum = np.clip((lum - 0.03) / 0.97, 0, 1) ** 1.05
    graded = board.gradient_map(lum, [(0.0, (0, 0, 0)), (0.12, (0.002, 0.016, 0.020)), (0.30, (0.010, 0.060, 0.075)),
                                      (0.50, (0.060, 0.030, 0.140)), (0.72, (0.24, 0.09, 0.20)), (0.90, (0.62, 0.46, 0.54)), (1.0, (1.0, 0.97, 0.95))])
    graded *= board.soft_vignette(graded.shape[1], graded.shape[0], 0.45)[..., None] * 1.15
    W = 1300
    graded = graded[:, (graded.shape[1] - W) // 2:(graded.shape[1] - W) // 2 + W]
    canvas = np.zeros((1350, W, 3))
    canvas[:, :1152] = base[:, :1152]
    canvas[:, 1152:] = base[:, :W - 1152]
    board.add_screen(canvas, graded, 0, -120, 1.0)
    save_webp("space_explore", fade_to_void(board.to_srgb(canvas), 880, 1340), 86)


def bake_search():
    base = board.void(1000, seed=31, stars=180) ** 2.2
    base = np.concatenate([base, base[:, :48]], 1)          # 1200 wide, for a few px of drift
    f = board.regrade("heic0406a.jpg", crop=(0.05, 0.55, 0.65, 0.93), size=(1200, 760), black=0.004, sat=0.7, gain=0.6)
    f *= board.soft_vignette(f.shape[1], f.shape[0], 0.5)[..., None]
    board.add_screen(base, f, 0, 30, 1.0)
    save_webp("space_search", fade_to_void(board.to_srgb(base), 560, 990), 86)


if __name__ == "__main__":
    os.makedirs(CACHE, exist_ok=True)
    print("T_MAX (the shader divides by it):", ld.T_MAX)
    bake_disk_texture()
    bake_library()
    bake_explore()
    bake_search()
    bake_home()
    bake_player()
