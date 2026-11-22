"""FDM parameter validation, B-rep clearance assertions, and layer printability scan.

    from forge.validate import assert_clearance, assert_fdm_params, print_scan
    assert_fdm_params(wall=2.0, floor=1.6, bed_chamfer=0.4)
    assert_clearance(body, lid, min_mm=0.15, label="lid fit")
    scan = print_scan(body, "body")
    assert scan.ok, str(scan)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from build123d import Shape
from scipy import ndimage

from forge import fdm
from forge.check import INTERFERENCE_TOL


def assert_fdm_params(
    *,
    wall: float | None = None,
    load_wall: float | None = None,
    floor: float | None = None,
    feature: float | None = None,
    bed_chamfer: float | None = None,
    overhang_deg: float | None = None,
    bridge: float | None = None,
    text_stroke: float | None = None,
    text_depth: float | None = None,
) -> None:
    """Validate numeric design parameters against active FDM rules before building geometry."""
    prof = fdm.current()
    errors: list[str] = []
    if wall is not None and wall < prof.wall_min - 1e-9:
        errors.append(f"wall {wall} < FDM min {prof.wall_min} mm")
    if load_wall is not None and load_wall < prof.wall_load - 1e-9:
        errors.append(f"load_wall {load_wall} < FDM min {prof.wall_load} mm")
    if floor is not None and floor < prof.floor_min - 1e-9:
        errors.append(f"floor {floor} < FDM min {prof.floor_min} mm")
    if feature is not None and feature < prof.feature_min - 1e-9:
        errors.append(f"feature {feature} < FDM min {prof.feature_min} mm")
    if bed_chamfer is not None and not (
        prof.bed_chamfer_min - 1e-9 <= bed_chamfer <= prof.bed_chamfer_max + 1e-9
    ):
        errors.append(
            f"bed_chamfer {bed_chamfer} outside [{prof.bed_chamfer_min}, {prof.bed_chamfer_max}] mm"
        )
    if overhang_deg is not None and overhang_deg > prof.overhang_max_deg + 1e-9:
        errors.append(f"overhang_deg {overhang_deg}° > FDM max {prof.overhang_max_deg:g}°")
    if bridge is not None and bridge > prof.bridge_max + 1e-9:
        errors.append(f"bridge {bridge} > FDM max {prof.bridge_max:g} mm")
    if text_stroke is not None and text_stroke < prof.text_stroke_min - 1e-9:
        errors.append(f"text_stroke {text_stroke} < FDM min {prof.text_stroke_min} mm")
    if text_depth is not None and text_depth < prof.text_depth_min - 1e-9:
        errors.append(f"text_depth {text_depth} < FDM min {prof.text_depth_min} mm")
    if errors:
        raise AssertionError("FDM parameter check failed: " + "; ".join(errors))


def assert_clearance(a: Shape, b: Shape, min_mm: float = 0.0, label: str = "") -> float:
    """Assert two shapes do not intersect and stay at least `min_mm` apart. Returns distance."""
    tag = f" ({label})" if label else ""
    common = a & b
    vol = common.volume if common is not None else 0.0
    if vol > INTERFERENCE_TOL:
        raise AssertionError(f"interference{tag}: overlap volume {vol:.3f} mm³ > {INTERFERENCE_TOL}")
    if min_mm <= 0.0:
        return 0.0
    dist = float(a.distance(b))
    if dist < min_mm - 1e-4:
        raise AssertionError(f"clearance{tag}: {dist:.3f} mm < required {min_mm:.3f} mm")
    return dist


@dataclass
class ScanResult:
    name: str
    islands: int = 0
    overhangs: int = 0
    steep_faces: int = 0
    thin_regions: int = 0
    longest_bridge_mm: float = 0.0
    messages: list[str] = field(default_factory=list)

    @property
    def total_problems(self) -> int:
        return self.islands + self.overhangs + self.steep_faces + self.thin_regions

    @property
    def ok(self) -> bool:
        return self.total_problems == 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "islands": self.islands,
            "overhangs": self.overhangs,
            "steep_faces": self.steep_faces,
            "thin_regions": self.thin_regions,
            "longest_bridge_mm": round(self.longest_bridge_mm, 2),
            "messages": list(self.messages),
        }

    def __str__(self) -> str:
        head = (
            f"PRINT SCAN {self.name}: islands={self.islands}, "
            f"overhangs={self.overhangs + self.steep_faces}, "
            f"thin={self.thin_regions}, longest_bridge={self.longest_bridge_mm:.1f} mm "
            f"(max {fdm.current().bridge_max:g})"
        )
        return "\n".join([head, *(f"  {m}" for m in self.messages)])


def _slice_mask(
    V: np.ndarray,
    T: np.ndarray,
    z: float,
    x0: float,
    y0: float,
    nx: int,
    ny: int,
    px: float,
) -> np.ndarray:
    """Even-odd raster of the horizontal section at height z."""
    tri = V[T]
    d = tri[:, :, 2] - z
    d[np.abs(d) < 1e-7] = 1e-7
    s = d > 0
    cross = s.sum(1)
    sel = (cross == 1) | (cross == 2)
    tri, d, s = tri[sel], d[sel], s[sel]
    pts = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        idx = np.where(s[:, a] != s[:, b])[0]
        if len(idx):
            ta = d[idx, a] / (d[idx, a] - d[idx, b])
            p = tri[idx, a, :2] + (tri[idx, b, :2] - tri[idx, a, :2]) * ta[:, None]
            pts.append((idx, p))
    seg = np.zeros((len(tri), 2, 2))
    cnt = np.zeros(len(tri), dtype=int)
    for idx, p in pts:
        seg[idx, cnt[idx]] = p
        cnt[idx] += 1
    seg = seg[cnt == 2]
    mask = np.zeros((ny, nx + 1), dtype=np.int32)
    if len(seg):
        ya, yb = seg[:, 0, 1], seg[:, 1, 1]
        xa, xb = seg[:, 0, 0], seg[:, 1, 0]
        lo, hi = np.minimum(ya, yb), np.maximum(ya, yb)
        r0 = np.ceil((lo - y0) / px - 0.5).astype(int)
        r1 = np.ceil((hi - y0) / px - 0.5).astype(int)
        for k in np.where(r1 > r0)[0]:
            rows = np.arange(max(r0[k], 0), min(r1[k], ny))
            if not len(rows):
                continue
            yc = y0 + (rows + 0.5) * px
            x = xa[k] + (xb[k] - xa[k]) * (yc - ya[k]) / (yb[k] - ya[k])
            col = np.clip(np.ceil((x - x0) / px - 0.5).astype(int), 0, nx)
            np.add.at(mask, (rows, col), 1)
    return (np.cumsum(mask, axis=1)[:, :nx] % 2).astype(bool)


def _bridged(m: np.ndarray, held: np.ndarray, px: float, bridge_max: float) -> tuple[np.ndarray, np.ndarray]:
    """Pixels of `m` on an X or Y straight bridge between supported pixels within `bridge_max`."""
    best = np.full(m.shape, np.inf)
    for arr_m, arr_h, tr in ((m, held, False), (m.T, held.T, True)):
        n = arr_m.shape[1]
        col = np.broadcast_to(np.arange(n), arr_m.shape)
        lh = np.maximum.accumulate(np.where(arr_h, col, -1), axis=1)
        lg = np.maximum.accumulate(np.where(~arr_m, col, -1), axis=1)
        rh = n - 1 - np.maximum.accumulate(np.where(arr_h[:, ::-1], col, -1), axis=1)[:, ::-1]
        rg = n - 1 - np.maximum.accumulate(np.where(~arr_m[:, ::-1], col, -1), axis=1)[:, ::-1]
        ok = (lh >= 0) & (lh > lg) & (rh <= n - 1) & (rh < rg) & arr_m
        sp = np.where(ok, (rh - lh) * px, np.inf)
        best = np.minimum(best, sp.T if tr else sp)
    return best <= bridge_max, np.where(np.isfinite(best), best, 0.0)


def _disk(r_px: float) -> np.ndarray:
    r = max(1, int(math.ceil(r_px)))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return (xx ** 2 + yy ** 2) <= r_px ** 2 + 1e-9


def print_scan(
    part: Shape,
    name: str = "part",
    *,
    layer_h: float | None = None,
    pixel_mm: float = 0.1,
    skip_thin_below: float = 0.0,
    check_thin: bool = True,
    check_overhangs: bool = True,
    max_messages: int = 8,
) -> ScanResult:
    """Scan a part in its print orientation (Z up, resting on min.Z) for FDM issues.

    Detects mid-air islands, unsupported overhangs steeper than `overhang_max_deg` that are
    not valid bridges (<= `bridge_max`), and thin features narrower than `feature_min`.
    """
    prof = fdm.current()
    step_z = layer_h if layer_h is not None else prof.layer
    res = ScanResult(name=name)
    bb = part.bounding_box()

    if check_overhangs:
        steep = []
        cos_lim = -math.cos(math.radians(prof.overhang_max_deg)) - 0.02
        for f in part.faces():
            fbb = f.bounding_box()
            if fbb.max.Z - bb.min.Z < 0.05:
                continue
            nz = []
            for u in (0.1, 0.5, 0.9):
                for v in (0.1, 0.5, 0.9):
                    try:
                        nz.append(f.normal_at(u, v).Z)
                    except Exception:
                        pass
            if not nz:
                continue
            worst = min(nz)
            if cos_lim > worst > -0.999 and f.area > 0.05:
                steep.append((round(math.degrees(math.asin(-worst)), 1), round(fbb.min.Z - bb.min.Z, 2), f.area))
        res.steep_faces = len(steep)
        for ang, z_rel, area in sorted(steep, reverse=True)[:max_messages]:
            res.messages.append(f"steep face {ang}° from vertical at z={z_rel} mm (area {area:.2f} mm²)")

    verts, tris = part.tessellate(min(pixel_mm / 2, 0.05), 0.2)
    V = np.array([(p.X, p.Y, p.Z) for p in verts])
    T = np.array(tris, dtype=int)
    x0, y0 = bb.min.X - 1.0, bb.min.Y - 1.0
    nx = int((bb.size.X + 2.0) / pixel_mm) + 1
    ny = int((bb.size.Y + 2.0) / pixel_mm) + 1
    sup_r = _disk(step_z * math.tan(math.radians(prof.overhang_max_deg)) / pixel_mm + 1.0)
    thin_k = _disk(max((prof.feature_min - 0.1) / 2.0 / pixel_mm, 0.5))
    conn = np.ones((3, 3))

    prev = None
    z = step_z / 2.0
    while z < bb.size.Z:
        m = _slice_mask(V, T, bb.min.Z + z, x0, y0, nx, ny, pixel_mm)
        if prev is not None and m.any():
            lab, n = ndimage.label(m, structure=conn)
            for i in range(1, n + 1):
                comp = lab == i
                area = comp.sum() * pixel_mm * pixel_mm
                if not (comp & prev).any() and area > 0.04:
                    res.islands += 1
                    if len(res.messages) < max_messages * 3:
                        ys, xs = np.where(comp)
                        res.messages.append(
                            f"ISLAND at z={z:.1f} near ({x0 + xs.mean() * pixel_mm:.1f}, "
                            f"{y0 + ys.mean() * pixel_mm:.1f}) ({area:.2f} mm²)"
                        )
            if check_overhangs:
                supp = ndimage.binary_dilation(prev, structure=sup_r)
                un = m & ~supp
                if un.any():
                    held = m & supp
                    br, span = _bridged(m, held, pixel_mm, prof.bridge_max)
                    if (un & br).any():
                        res.longest_bridge_mm = max(res.longest_bridge_mm, float(span[un & br].max()))
                    rest = un & ~br
                    if rest.any():
                        dist = ndimage.distance_transform_edt(~held) * pixel_mm
                        ul, un_n = ndimage.label(rest, structure=conn)
                        for i in range(1, un_n + 1):
                            reg = ul == i
                            dmax = float(dist[reg].max())
                            if dmax <= 2.0 * pixel_mm:
                                continue
                            res.overhangs += 1
                            if res.overhangs <= max_messages:
                                ys, xs = np.where(reg)
                                res.messages.append(
                                    f"OVERHANG at z={z:.1f} near ({x0 + xs.mean() * pixel_mm:.1f}, "
                                    f"{y0 + ys.mean() * pixel_mm:.1f}): reaches {dmax:.2f} mm unsupported"
                                )
        if check_thin and z > skip_thin_below and m.any():
            opened = ndimage.binary_dilation(ndimage.binary_erosion(m, structure=thin_k), structure=thin_k)
            thin = m & ~opened
            if thin.any():
                necks = np.zeros_like(m)
                if opened.any():
                    ol, _ = ndimage.label(opened, structure=conn)
                    rl, rn = ndimage.label(thin, structure=conn)
                    for i in range(1, rn + 1):
                        reg = rl == i
                        if reg.sum() * pixel_mm * pixel_mm <= 0.15:
                            continue
                        near = ol[ndimage.binary_dilation(reg, iterations=2)]
                        if len(np.unique(near[near > 0])) >= 2:
                            necks |= reg
                    thin &= ndimage.distance_transform_edt(~opened) * pixel_mm > prof.nozzle + 1e-6
                thin |= necks
                tl, tn = ndimage.label(thin, structure=conn)
                if tn:
                    sizes = ndimage.sum(thin, tl, range(1, tn + 1)) * pixel_mm * pixel_mm
                    for i in np.where(sizes > 0.15)[0]:
                        res.thin_regions += 1
                        if res.thin_regions <= max_messages:
                            ys, xs = np.where(tl == i + 1)
                            res.messages.append(
                                f"THIN (< {prof.feature_min}) at z={z:.1f} near "
                                f"({x0 + xs.mean() * pixel_mm:.1f}, {y0 + ys.mean() * pixel_mm:.1f}): "
                                f"{sizes[i]:.2f} mm²"
                            )
        prev = m
        z += step_z

    return res
