import asyncio
import contextlib
import hashlib
import logging
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import REFRESH_MINUTES
from . import tiles
from .refresh import Store, refresh

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("mvderby")
STATIC = Path(__file__).parent / "static"


def _asset_version() -> str:
    """Content hash of the static files, stamped onto CSS/JS URLs so every deploy gets
    URLs no browser or Cloudflare edge has cached before."""
    h = hashlib.sha1()
    for f in sorted(STATIC.rglob("*")):
        if f.is_file() and f.name != "chart.pdf":
            h.update(f.relative_to(STATIC).as_posix().encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:10]


ASSET_V = _asset_version()
INDEX_HTML = re.sub(r'((?:href|src)="/[^"?]+\.(?:css|js))"', rf'\1?v={ASSET_V}"',
                    (STATIC / "index.html").read_text())


class Static(StaticFiles):
    """Revalidate everything (ETag makes that a cheap 304) so Cloudflare and browsers
    never serve a stale build; only the versioned vendor libraries are immutable."""

    async def get_response(self, path, scope):
        r = await super().get_response(path, scope)
        r.headers["Cache-Control"] = ("public, max-age=31536000, immutable" if path.startswith("vendor/")
                                      else "no-cache")
        return r

store = Store()
_lock = asyncio.Lock()


async def _do_refresh():
    async with _lock:
        try:
            await refresh(store)
            log.info("plan refreshed")
        except Exception:
            log.exception("refresh failed")


async def _loop():
    while True:
        await _do_refresh()
        await asyncio.sleep(REFRESH_MINUTES * 60)


@contextlib.asynccontextmanager
async def lifespan(_app):
    task = asyncio.create_task(_loop())
    yield
    task.cancel()


app = FastAPI(title="MV Derby planner", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "has_plan": store.plan is not None}


@app.get("/api/plan")
async def plan():
    if store.plan is None:
        raise HTTPException(503, "first refresh still running")
    return JSONResponse(store.plan, headers={"Cache-Control": "no-cache"})


@app.post("/api/refresh")
async def force_refresh():
    await _do_refresh()
    return {"ok": store.plan is not None, "generated": (store.plan or {}).get("generated")}


@app.get("/api/stations")
async def stations():
    """Debug: which NOAA stations were matched, and the regional catalogue to pick from."""
    return {"resolved": store.stations, "regional": store.catalogue}


@app.get("/tiles/{z}/{x}/{y}.png")
async def tile(z: int, x: int, y: int):
    if not tiles.in_region(z, x, y):
        raise HTTPException(404, "outside the Vineyard chart area")
    try:
        path = await tiles.get_tile(z, x, y)
    except Exception as e:  # noqa: BLE001 — NOAA down; the app falls back to the static chart
        log.warning("tile %s/%s/%s failed: %s", z, x, y, e)
        raise HTTPException(502, "NOAA chart service unavailable") from e
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=2592000"})


@app.get("/api/tiles")
async def tile_list(max_z: int = 14):
    """Every tile in the chart area up to max_z, for the app's 'Save for offline'."""
    out = []
    for z in range(tiles.MIN_Z, min(max_z, tiles.MAX_Z) + 1):
        xs, ys = tiles.tile_range(z, tiles.SAVE_BOUNDS)
        out += [f"/tiles/{z}/{x}/{y}.png" for x in xs for y in ys]
    return {"tiles": out, "bounds": [[tiles.SOUTH, tiles.WEST], [tiles.NORTH, tiles.EAST]],
            "min_z": tiles.MIN_Z, "max_z": tiles.MAX_Z}


@app.get("/sw.js")
async def sw():
    return FileResponse(STATIC / "sw.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.api_route("/", methods=["GET", "HEAD"])
async def index():
    return HTMLResponse(INDEX_HTML, headers={"Cache-Control": "no-cache"})


app.mount("/", Static(directory=STATIC), name="static")
