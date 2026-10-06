import asyncio
import contextlib
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import REFRESH_MINUTES
from .refresh import Store, refresh

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("mvderby")
STATIC = Path(__file__).parent / "static"
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


@app.get("/sw.js")
async def sw():
    return FileResponse(STATIC / "sw.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=STATIC), name="static")
