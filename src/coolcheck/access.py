"""Cooling access (R1 and R2, decided 23 Oct 2026): refuge and park layers, straight-line distances and 400 m shares.

All geometry is in SVY21 (EPSG:3414, metres), projected from WGS84 lon/lat with pyproj. A distance between two points is
the straight line sqrt(dx^2 + dy^2) in SVY21; that is the rule the what_if_add_refuge function must use when it
recomputes distances in SQL from the stored x_svy21 / y_svy21 columns. A distance to a park is to the nearest edge of
the merged park layer, 0 for a point inside it. No street network is walked.

Layer rules (applied by scripts/static/refuge_park_access.py, reported in docs/checks/refuge_park_access.md):
- Community Clubs: People's Association rows with DESCRIPTION = 'CC' (the PAssion WaVe outlets are out). A name marked
  (U/C) is under construction and in no set; (Temp Office) is open and flagged temp_office.
- Active Ageing Centres: Go-To-Points rows whose name matches AAC_RX, a partial layer (93 of about 223 AACs).
- Senior Activity Centres: names matching SAC_RX, in the Go-To-Points file and the 2016 Eldercare file; Silver ACE is out.
- Duplicates by postal code within each set: the first row is kept by layer (club, AAC, Go-To-Points SAC, 2016 SAC),
  then open before temp_office, then a club's own row before a 'CO' row housed in it, then name.
- Parks: each layer is merged (overlaps counted once) and pieces under SLIVER_M2 are dropped as slivers.
"""
import re

import numpy as np
import shapely
from pyproj import Transformer
from shapely import STRtree
from shapely.ops import unary_union

WALK_M = 400.0
SLIVER_M2 = 100.0
AREA_TOLERANCE_M = 25.0
_TO_SVY21 = Transformer.from_crs("EPSG:4326", "EPSG:3414", always_xy=True)

AAC_RX = re.compile(r"active ageing (centre|hub|center)|\bAAC\b|\bAAH\b", re.I)
SAC_RX = re.compile(r"senior activity|\bSAC\b", re.I)
SILVER_ACE_RX = re.compile(r"silver|\bace\b", re.I)
POSSIBLE_AAC_RX = re.compile(r"\bsenior centre\b|\bactive care centre\b", re.I)
CO_RX = re.compile(r"\bCO\b")
LAYERS = ("community_club", "aac_partial", "gtp_sac", "eldercare_sac_2016")
REFUGE_SETS = {"main": ("community_club", "aac_partial"), "clubs_only": ("community_club",), "with_sac_2016": LAYERS}
STATUS_ORDER = {"open": 0, "temp_office": 1}


# --- projection and geometry -------------------------------------------------------------------------------------

def to_svy21(lon, lat):
    """(x, y) in EPSG:3414 metres for WGS84 lon/lat (scalars or arrays)."""
    return _TO_SVY21.transform(lon, lat)


def geom_to_svy21(geom):
    """The geometry in EPSG:3414, 2-D (a Z coordinate is dropped)."""
    return shapely.transform(geom, lambda c: np.column_stack(_TO_SVY21.transform(c[:, 0], c[:, 1])))


def polygonal(geom):
    """A valid Polygon or MultiPolygon: invalid input is repaired and any line or point left by the repair is dropped."""
    if geom.is_valid:
        return geom
    fixed = shapely.make_valid(geom)
    if fixed.geom_type in ("Polygon", "MultiPolygon"):
        return fixed
    return unary_union([g for g in getattr(fixed, "geoms", [fixed]) if g.geom_type in ("Polygon", "MultiPolygon")])


def nearest_points(px, py, qx, qy):
    """For each point p, the straight-line distance to the nearest point q and q's index (every pair is compared)."""
    px, py, qx, qy = (np.asarray(a, dtype=float) for a in (px, py, qx, qy))
    d = np.sqrt((px[:, None] - qx[None, :]) ** 2 + (py[:, None] - qy[None, :]) ** 2)
    i = d.argmin(axis=1)
    return d[np.arange(len(px)), i], i


def merge_layer(polygons, min_piece_m2=SLIVER_M2):
    """The union of the polygons split into its pieces: (pieces kept, pieces under min_piece_m2 dropped)."""
    u = unary_union(polygons)
    parts = [p for p in getattr(u, "geoms", [u]) if not p.is_empty]
    return [p for p in parts if p.area >= min_piece_m2], [p for p in parts if p.area < min_piece_m2]


def nearest_polygons(px, py, polygons):
    """For each point, the distance to the nearest polygon (0 inside one) and that polygon's index."""
    tree = STRtree(polygons)
    (src, hit), dist = tree.query_nearest(shapely.points(px, py), return_distance=True, all_matches=False)
    d, i = np.full(len(src), np.nan), np.zeros(len(src), dtype=int)
    d[src], i[src] = dist, hit
    return d, i


def share_within(distances, weights, limit_m=WALK_M):
    """Weighted share of points at most limit_m away (400 m counts as within); None when the weights sum to 0."""
    total = float(sum(weights))
    if total == 0:
        return None
    return float(sum(w for d, w in zip(distances, weights) if d <= limit_m)) / total


def area_share(pieces, area_polygon):
    """(park area inside the planning area in m2, its share of the area) for non-overlapping merged pieces."""
    tree = STRtree(pieces)
    inside = sum(pieces[j].intersection(area_polygon).area for j in tree.query(area_polygon, predicate="intersects"))
    return inside, (inside / area_polygon.area if area_polygon.area else None)


def assign_areas(xs, ys, areas, tolerance_m=AREA_TOLERANCE_M):
    """For each point, (planning area, metres outside it): the polygon containing it; else the nearest polygon within
    tolerance_m; else (None, distance to the nearest). areas is a list of (name, SVY21 polygon)."""
    out = []
    for x, y in zip(xs, ys):
        p = shapely.Point(x, y)
        inside = [n for n, g in areas if g.covers(p)]
        if inside:
            out.append((inside[0], 0.0))
            continue
        d, n = min((g.distance(p), n) for n, g in areas)
        out.append((n if d <= tolerance_m else None, d))
    return out


def rank_worst_first(values):
    """{key: rank} with 1 for the lowest value (worst access); ties share their mean rank; None values are left out."""
    items = sorted((v, k) for k, v in values.items() if v is not None)
    ranks, i = {}, 0
    while i < len(items):
        j = i
        while j + 1 < len(items) and items[j + 1][0] == items[i][0]:
            j += 1
        for _, k in items[i:j + 1]:
            ranks[k] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(a, b):
    """Spearman's rho of two {key: value} maps over the keys both have a value for (Pearson on mean ranks)."""
    keys = sorted(k for k in a if k in b and a[k] is not None and b[k] is not None)
    ra = rank_worst_first({k: a[k] for k in keys})
    rb = rank_worst_first({k: b[k] for k in keys})
    x, y = np.array([ra[k] for k in keys]), np.array([rb[k] for k in keys])
    if len(keys) < 2 or x.std() == 0 or y.std() == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


# --- layer rules -------------------------------------------------------------------------------------------------

def clean_name(raw):
    """The source name with U+FFFD (a broken character in the source file) replaced by a space; spaces collapsed."""
    return re.sub(r"\s+", " ", (raw or "").replace("�", " ")).strip()


def pad_postal(value):
    """A postal code as 6-digit text; a numeric field that lost its leading zero (58284) is padded back (058284)."""
    s = "" if value is None else str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(6) if s.isdigit() and len(s) < 6 else s


def club_status(name):
    """under_construction for a name marked (U/C), temp_office for (Temp Office), otherwise open."""
    if re.search(r"\(U/C\)", name, re.I):
        return "under_construction"
    if re.search(r"\(temp office\)", name, re.I):
        return "temp_office"
    return "open"


def gtp_kind(name):
    """aac, sac, possible_aac (a centre name the AAC pattern does not match, listed but not used) or None."""
    if AAC_RX.search(name):
        return "aac"
    if SAC_RX.search(name):
        return "sac"
    if POSSIBLE_AAC_RX.search(name):
        return "possible_aac"
    return None


def eldercare_kind(name):
    """aac, sac, silver_ace or other for a 2016 Eldercare Services name."""
    if re.search(r"active ageing|\bAAC\b", name, re.I):
        return "aac"
    if SAC_RX.search(name):
        return "sac"
    if SILVER_ACE_RX.search(name):
        return "silver_ace"
    return "other"


def dedupe(rows):
    """Set duplicate_of and in_<set> for every refuge set on each row (dicts with refuge_id, layer, status, name and
    postal_code). A row under construction is in no set and is never the row kept. The sets are nested in layer order,
    so a row's duplicate_of is the same in every set it belongs to; a ValueError is raised if that ever fails."""
    def order(r):
        return LAYERS.index(r["layer"]), STATUS_ORDER[r["status"]], bool(CO_RX.search(r["name"])), r["name"], r["refuge_id"]

    seen = {}
    for name, layers in REFUGE_SETS.items():
        kept = {}
        for r in rows:
            r[f"in_{name}"] = False
        for r in sorted((r for r in rows if r["layer"] in layers and r["status"] != "under_construction"), key=order):
            k = kept.setdefault(r["postal_code"] or r["refuge_id"], r["refuge_id"])
            dup = "" if k == r["refuge_id"] else k
            if seen.setdefault(r["refuge_id"], dup) != dup:
                raise ValueError(f"{r['refuge_id']} is a duplicate of different rows in different sets")
            r[f"in_{name}"] = not dup
    for r in rows:
        r["duplicate_of"] = seen.get(r["refuge_id"], "")
    return rows
