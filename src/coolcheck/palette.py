"""Colour checks for the dashboards: a Python port of the dataviz skill's scripts/validate_palette.js (window A ran the
same check for the live page, since node is not installed).

Delta E is the Euclidean distance in OKLab x 100. Colour-vision deficiency is simulated with Machado, Oliveira and
Fernandes (2009) at severity 1.0 in linear RGB, the model the validator's thresholds are calibrated to. The categorical
gate the user set: the worst pair at least 8 under each of protan, deutan and tritan (pairs "all" for maps, where any two
colours can touch), and the validator's normal-vision floor of 15. Ordinal ramps (ordered classes, such as vulnerability
thirds) take the validator's ordinal checks instead: monotone lightness, adjacent delta L >= 0.06, a light end at
least 2:1 against the surface, one hue (spread <= 40 degrees).
"""
import math
from itertools import combinations

CVD_TARGET, NORMAL_FLOOR = 8.0, 15.0
ORDINAL_MIN_DL, ORDINAL_LIGHT_FLOOR, ORDINAL_HUE_SPREAD = 0.06, 2.0, 40.0
MACHADO = {
    "protan": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "tritan": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}


def _srgb(h):
    h = h.strip().lstrip("#")
    if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
        raise ValueError(f"not a #rrggbb colour: {h!r}")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def _lin(h):
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in _srgb(h)]


def _oklab(rgb):
    r, g, b = rgb
    l = math.copysign(abs(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3), 1)
    m = math.copysign(abs(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3), 1)
    s = math.copysign(abs(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3), 1)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def _simulate(h, kind):
    r, g, b = _lin(h)
    return [max(0.0, min(1.0, row[0] * r + row[1] * g + row[2] * b)) for row in MACHADO[kind]]


def oklch(h):
    """(L, C, hue in degrees) in OKLCH."""
    L, a, b = _oklab(_lin(h))
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def delta_e(h1, h2, kind=None):
    """OKLab Delta E x 100 between two colours, under a simulated deficiency or (kind None) normal vision."""
    a = _oklab(_simulate(h1, kind) if kind else _lin(h1))
    b = _oklab(_simulate(h2, kind) if kind else _lin(h2))
    return 100 * math.dist(a, b)


def contrast(a, b):
    """WCAG contrast ratio."""
    def lum(h):
        r, g, b_ = _lin(h)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b_
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def worst_pairs(palette, pairs="all"):
    """{kind: (Delta E, colour, colour)} for the worst pair under protan, deutan, tritan and normal vision."""
    pl = list(combinations(range(len(palette)), 2)) if pairs == "all" else [(i, i + 1) for i in range(len(palette) - 1)]
    out = {}
    for kind in ("protan", "deutan", "tritan", None):
        d, i, j = min((delta_e(palette[i], palette[j], kind), i, j) for i, j in pl)
        out[kind or "normal"] = (d, palette[i], palette[j])
    return out


def categorical_ok(palette, pairs="all"):
    """True when the worst pair is >= 8 under each deficiency and >= 15 under normal vision."""
    w = worst_pairs(palette, pairs)
    return all(w[k][0] >= CVD_TARGET for k in ("protan", "deutan", "tritan")) and w["normal"][0] >= NORMAL_FLOOR


def ordinal_checks(ramp, surface="#fcfcfb"):
    """The validator's ordinal checks: {check: (passed, detail)} for a ramp listed light to dark (or dark to light)."""
    Ls = [oklch(c)[0] for c in ramp]
    order = sorted(range(len(Ls)), key=Ls.__getitem__)
    mono = order == list(range(len(Ls))) or order == list(range(len(Ls)))[::-1]
    gaps = [abs(Ls[i + 1] - Ls[i]) for i in range(len(Ls) - 1)]
    lightest = max(ramp, key=lambda c: oklch(c)[0])
    hues = [oklch(c)[2] for c in ramp]
    spread = max(hues) - min(hues)
    spread = 360 - spread if spread > 180 else spread
    return {"monotone lightness": (mono, [round(x, 3) for x in Ls]),
            "adjacent delta L": (min(gaps) >= ORDINAL_MIN_DL, round(min(gaps), 3)),
            "light-end contrast": (contrast(lightest, surface) >= ORDINAL_LIGHT_FLOOR, round(contrast(lightest, surface), 2)),
            "single hue": (spread <= ORDINAL_HUE_SPREAD, round(spread, 1))}
