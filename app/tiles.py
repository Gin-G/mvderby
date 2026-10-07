"""Live NOAA chart tiles: Web Mercator XYZ tiles rendered from NOAA's ENC chart display
WMS, cached on DATA_DIR so each tile is fetched from NOAA at most once."""
import asyncio
import math
from pathlib import Path

from .config import DATA_DIR
from .sources import _client

ENC_WMS = ("https://gis.charttools.noaa.gov/arcgis/rest/services/MCS/NOAAChartDisplay/"
           "MapServer/exts/MaritimeChartService/WMSServer")
# 1-7: features, depths/currents, seabed, routes, special areas, aids to nav, services.
# Skips the display banner (0) and the data-quality / overscale hatching (8-12).
LAYERS = "1,2,3,4,5,6,7"
MIN_Z, MAX_Z = 9, 15
# Only the waters around the Vineyard, so this isn't an open proxy for the whole coast.
SOUTH, WEST, NORTH, EAST = 41.15, -71.30, 41.70, -69.95
# What "Save for offline" downloads: the fishing area the static chart covers.
SAVE_BOUNDS = (41.25, -70.89, 41.585, -70.28)

ORIGIN = 20037508.342789244  # half the Web Mercator world width, metres
_ROOT = Path(DATA_DIR) / "tiles"
_locks: dict[tuple, asyncio.Lock] = {}


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def tile_range(z: int, bounds=(SOUTH, WEST, NORTH, EAST)) -> tuple[range, range]:
    south, west, north, east = bounds
    x0, y0 = lonlat_to_tile(west, north, z)
    x1, y1 = lonlat_to_tile(east, south, z)
    return range(x0, x1 + 1), range(y0, y1 + 1)


def in_region(z: int, x: int, y: int) -> bool:
    if not MIN_Z <= z <= MAX_Z:
        return False
    xs, ys = tile_range(z)
    return x in xs and y in ys


def tile_bbox(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    size = 2 * ORIGIN / 2 ** z
    minx = -ORIGIN + x * size
    maxy = ORIGIN - y * size
    return minx, maxy - size, minx + size, maxy


async def get_tile(z: int, x: int, y: int) -> Path:
    """Path to the cached PNG, fetching it from NOAA first if needed."""
    path = _ROOT / str(z) / str(x) / f"{y}.png"
    if path.exists():
        return path
    lock = _locks.setdefault((z, x, y), asyncio.Lock())
    async with lock:
        if not path.exists():
            minx, miny, maxx, maxy = tile_bbox(z, x, y)
            params = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": LAYERS,
                      "STYLES": "", "CRS": "EPSG:3857", "BBOX": f"{minx},{miny},{maxx},{maxy}",
                      "WIDTH": 256, "HEIGHT": 256, "FORMAT": "image/png"}
            async with _client() as c:
                r = await c.get(ENC_WMS, params=params)
                r.raise_for_status()
                if not r.headers.get("content-type", "").startswith("image/"):
                    raise RuntimeError(f"NOAA returned {r.headers.get('content-type')}")
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(r.content)
            tmp.replace(path)
    _locks.pop((z, x, y), None)
    return path
