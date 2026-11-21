#!/usr/bin/env python3
"""Offline null-geodesic tracer for Sonara's Space theme (Schwarzschild, G = c = M = 1).

Every pixel is a light ray traced backwards from a pinhole camera through curved spacetime. The
spatial path of a photon around a Schwarzschild mass obeys, exactly,

    d2x/dl2 = -3 M h^2 x / r^5,        h = |x cross dx/dl| (conserved),

the Binet equation u'' + u = 3 M u^2 in Cartesian form (M = 1 here; references that set the
Schwarzschild radius to 1 have M = 1/2 and write the coefficient as 3/2). It is integrated with RK4 at a step that
shrinks near the hole, until the ray

  - crosses the equatorial plane of a thin accretion disk between R_IN (the ISCO, r = 6) and R_OUT:
    a disk hit. We keep its radius r, azimuth phi, the image ORDER (how many times the ray had
    already crossed the plane outside the disk: 0 is the direct image, 1 the lensed band over
    the top of the shadow and the thin ring under it, 2+ the photon ring), and the redshift
        g = sqrt(1 - 3/r) / (1 - Omega * lambda),   Omega = r^(-3/2),
    lambda the photon's angular momentum about the disk axis (gravitational x Doppler; g > 1 on
    the approaching side);
  - falls through r = 2: captured, part of the shadow (drawn pure black, nothing inside it);
  - escapes past R_ESC: we keep its final direction, which the sky texture is sampled through —
    stars and the Milky Way smear into arcs and are duplicated near the hole.

We also keep the closest approach r_min, which marks the photon ring (r_min -> 3).

Nothing here runs on the phone: the app only looks these tables up (see SpaceScene).
"""
import math

import numpy as np

R_IN = 6.0       # innermost stable circular orbit
R_OUT = 20.0
R_ESC = 400.0
R_CAPTURE = 2.0


class Camera:
    """A pinhole camera at distance D from the hole, INCL degrees above the disk plane, looking at it.

    Image-plane coordinates (x right, y up) are in units of M at the hole's distance, so a pixel
    grid in M maps straight onto the scene. The disk normal is tilted toward the camera by
    90 - INCL degrees, so the camera sees the disk's top face, nearly edge-on.
    """

    def __init__(self, distance=80.0, elevation_deg=8.0):
        self.D = distance
        e = math.radians(elevation_deg)
        # Camera on +z; disk normal leans toward it by the elevation.
        self.normal = np.array([0.0, math.cos(e), math.sin(e)])
        self.e1 = np.array([1.0, 0.0, 0.0])
        self.e2 = np.cross(self.normal, self.e1)

    def rays(self, X, Y):
        """Ray origins and unit directions for image-plane points X, Y (in M at the hole's distance)."""
        n = X.size
        o = np.tile([0.0, 0.0, self.D], (n, 1))
        d = np.stack([X.ravel(), Y.ravel(), np.full(n, -self.D)], axis=1)
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        return o, d


def _acc(p, h2):
    r2 = np.einsum("ij,ij->i", p, p)
    return (-3.0 * h2 / (r2 * r2 * np.sqrt(r2)))[:, None] * p


def trace(cam, X, Y, max_steps=6000, log=print):
    """Traces the rays through image-plane points X, Y (2-D arrays). Returns a dict of 2-D arrays."""
    shape = X.shape
    x, v = cam.rays(X, Y)
    N = x.shape[0]
    h2 = np.einsum("ij,ij->i", np.cross(x, v), np.cross(x, v))
    lam = -(np.cross(x, v) @ cam.normal)          # forward photon's angular momentum about the disk axis
    nrm = cam.normal

    status = np.zeros(N, np.int8)                 # 0 active, 1 disk, 2 captured, 3 escaped
    order = np.zeros(N, np.int8)                  # plane crossings outside the disk so far
    hit_r = np.zeros(N)
    hit_phi = np.zeros(N)
    rmin = np.full(N, 1e9)
    side = x @ nrm

    active = np.arange(N)
    for step in range(max_steps):
        if active.size == 0:
            break
        p, q, hh = x[active], v[active], h2[active]
        r = np.linalg.norm(p, axis=1)
        rmin[active] = np.minimum(rmin[active], r)
        # Step: fine near the photon sphere and the disk, coarse far away.
        dt = np.clip(0.035 * r * np.clip((r - 2.0) / 4.0, 0.25, 1.0), 0.004, 4.0)[:, None]
        k1x, k1v = q, _acc(p, hh)
        k2x, k2v = q + 0.5 * dt * k1v, _acc(p + 0.5 * dt * k1x, hh)
        k3x, k3v = q + 0.5 * dt * k2v, _acc(p + 0.5 * dt * k2x, hh)
        k4x, k4v = q + dt * k3v, _acc(p + dt * k3x, hh)
        np_ = p + dt / 6 * (k1x + 2 * k2x + 2 * k3x + k4x)
        nq = q + dt / 6 * (k1v + 2 * k2v + 2 * k3v + k4v)

        s0 = side[active]
        s1 = np_ @ nrm
        crossed = np.sign(s0) != np.sign(s1)
        if crossed.any():
            ci = np.nonzero(crossed)[0]
            f = (s0[ci] / (s0[ci] - s1[ci]))[:, None]
            pc = p[ci] + f * (np_[ci] - p[ci])
            rc = np.linalg.norm(pc, axis=1)
            in_disk = (rc >= R_IN) & (rc <= R_OUT)
            gi = active[ci[in_disk]]
            status[gi] = 1
            hit_r[gi] = rc[in_disk]
            hit_phi[gi] = np.mod(np.arctan2(pc[in_disk] @ cam.e2, pc[in_disk] @ cam.e1), 2 * np.pi)
            order[active[ci[~in_disk]]] += 1

        x[active], v[active], side[active] = np_, nq, s1
        rn = np.linalg.norm(np_, axis=1)
        cap = (rn < R_CAPTURE) & (status[active] == 0)
        esc = (rn > R_ESC) & (np.einsum("ij,ij->i", np_, nq) > 0) & (status[active] == 0)
        status[active[cap]] = 2
        status[active[esc]] = 3
        active = active[status[active] == 0]
        if step % 500 == 0:
            log(f"  step {step}: {active.size} rays still travelling")
    status[active] = 2  # anything that never got out is treated as captured (deep in the well)

    g = np.zeros(N)
    disk = status == 1
    r = hit_r[disk]
    g[disk] = np.sqrt(1 - 3 / r) / (1 - r ** -1.5 * lam[disk])
    d = v / np.linalg.norm(v, axis=1, keepdims=True)
    out = dict(status=status, order=order, r=hit_r, phi=hit_phi, g=g, rmin=rmin, dx=d[:, 0], dy=d[:, 1], dz=d[:, 2])
    return {k: a.reshape(shape) for k, a in out.items()}
