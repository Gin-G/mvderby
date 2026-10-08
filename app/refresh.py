"""Fetch everything, fall back per-source, build the plan, persist to DATA_DIR."""
import asyncio
import json
import logging
import pickle
from datetime import date, datetime, timedelta
from pathlib import Path

from . import derby_fallback, sources
from .config import CURRENT_STATIONS, DATA_DIR, TRIP_END, TRIP_START, TZ
from .engine import build_plan

log = logging.getLogger("mvderby.refresh")


def trip_days(today: date | None = None) -> list[date]:
    """The trip window; outside it, show today + 3 days so the app is useful year-round."""
    today = today or datetime.now(TZ).date()
    if today <= TRIP_END:
        start = TRIP_START
        end = TRIP_END
    else:
        start, end = today, today + timedelta(days=3)
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


class Store:
    """Last-good cache per source, persisted so a pod restart offline still serves data."""

    def __init__(self, root: str = DATA_DIR):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lastgood = self._load("lastgood.pkl", {})
        self.plan = self._load_json("plan.json")
        self.stations = self._load_json("stations.json") or {}
        self.catalogue = self._load_json("catalogue.json") or []

    def _load(self, name, default):
        try:
            return pickle.loads((self.root / name).read_bytes())
        except Exception:
            return default

    def _load_json(self, name):
        try:
            return json.loads((self.root / name).read_text())
        except Exception:
            return None

    def save(self):
        (self.root / "lastgood.pkl").write_bytes(pickle.dumps(self.lastgood))
        (self.root / "plan.json").write_text(json.dumps(self.plan))
        (self.root / "stations.json").write_text(json.dumps(self.stations))
        (self.root / "catalogue.json").write_text(json.dumps(self.catalogue))


async def _guard(store: Store, key: str, coro, status: dict, label: str):
    try:
        val = await coro
        store.lastgood[key] = {"at": datetime.now(TZ), "val": val}
        status[key] = {"ok": True, "source": label, "at": datetime.now(TZ).isoformat()}
        return val
    except Exception as e:  # noqa: BLE001 — any upstream failure falls back
        log.warning("%s failed: %s", key, e)
        lg = store.lastgood.get(key)
        if lg:
            status[key] = {"ok": False, "source": f"{label} (cached)",
                           "at": lg["at"].isoformat(), "error": str(e)[:200]}
            return lg["val"]
        status[key] = {"ok": False, "source": None, "error": str(e)[:200]}
        return None


async def refresh(store: Store) -> dict:
    days = trip_days()
    start, end = sources.window(days[0], days[-1])
    status: dict = {}

    # Station discovery (cached; re-run if any station is missing)
    if not store.stations or set(store.stations) != set(CURRENT_STATIONS):
        try:
            cat = await sources.fetch_station_catalogue()
            store.catalogue = sources.regional_catalogue(cat)
            store.stations = sources.resolve_stations(cat)
            log.info("resolved stations: %s", store.stations)
        except Exception as e:  # noqa: BLE001
            log.warning("station discovery failed: %s", e)

    tides_t = _guard(store, "tides", sources.fetch_tides(start, end), status, "NOAA 8448558")
    wind_t = _guard(store, "wind", sources.fetch_wind(41.40, -70.50, days[0], days[-1]),
                    status, "Open-Meteo")
    marine_t = _guard(store, "marine", sources.fetch_marine_text(), status, "NWS BOX")
    cur_tasks = {}
    for key in CURRENT_STATIONS:
        st = store.stations.get(key)
        if st:
            cur_tasks[key] = _guard(store, f"cur_{key}", sources.fetch_currents(st, start, end),
                                    status, f"NOAA {st['id']}")

    tides, wind, marine, *cur_vals = await asyncio.gather(
        tides_t, wind_t, marine_t, *cur_tasks.values())
    currents = dict(zip(cur_tasks.keys(), cur_vals))

    if not tides:
        tides = derby_fallback.hilo_events()
        status["tides"] = {**status.get("tides", {}), "source": "Derby PDF (fallback)"}
    for key in CURRENT_STATIONS:
        if not currents.get(key):
            fb = derby_fallback.slack_events(CURRENT_STATIONS[key].get("derby", key))
            if fb:
                currents[key] = fb
                status[f"cur_{key}"] = {**status.get(f"cur_{key}", {}),
                                        "source": "Derby PDF (fallback)"}

    plan = build_plan(tides=tides, currents=currents, wind=wind, days=days, sources=status)
    plan["marine"] = marine
    plan["station_ids"] = store.stations
    store.plan = plan
    store.save()
    return plan
