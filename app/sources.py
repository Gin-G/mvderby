"""External data fetchers. Every fetcher returns parsed data or raises; caching and
fallback are handled by the caller (refresh.py)."""
import logging
import math
import os
from datetime import date, datetime, timedelta

import httpx

from .config import (CURRENT_STATIONS, NOAA_APP, NWS_ZONES, REGION_BBOX, TIDE_STATION, TZ)

log = logging.getLogger("mvderby.sources")

NOAA_DATA = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NOAA_META = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
NWS_TEXT = "https://tgftp.nws.noaa.gov/data/forecasts/marine/coastal/an/{zone}.txt"

HEADERS = {"User-Agent": "mvderby.nickknows.net (personal fishing planner)"}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30, headers=HEADERS, follow_redirects=True)


def _parse_noaa_time(s: str) -> datetime:
    return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=TZ)


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


# ---------------------------------------------------------------- tides
async def fetch_tides(start: date, end: date) -> list[dict]:
    params = {
        "begin_date": _ymd(start), "end_date": _ymd(end), "station": TIDE_STATION,
        "product": "predictions", "datum": "MLLW", "interval": "hilo",
        "time_zone": "lst_ldt", "units": "english", "format": "json", "application": NOAA_APP,
    }
    async with _client() as c:
        r = await c.get(NOAA_DATA, params=params)
        r.raise_for_status()
        body = r.json()
    if "error" in body:
        raise RuntimeError(body["error"].get("message", body["error"]))
    return parse_tides(body)


def parse_tides(body: dict) -> list[dict]:
    return [{"t": _parse_noaa_time(p["t"]), "type": p["type"], "v": float(p["v"])}
            for p in body["predictions"]]


# ---------------------------------------------------------------- current station discovery
def _dist_km(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    return 6371 * math.hypot(dlat, dlon)


def resolve_stations(catalogue: list[dict]) -> dict[str, dict]:
    """Pick a NOAA current-prediction station + bin for each configured key."""
    s, w, n, e = REGION_BBOX
    local = [st for st in catalogue
             if st.get("lat") is not None and s <= float(st["lat"]) <= n
             and w <= float(st["lng"]) <= e]
    resolved = {}
    for key, cfg in CURRENT_STATIONS.items():
        override = os.getenv(f"CURRENT_{key.upper()}")
        if override:
            sid, _, b = override.partition(":")
            resolved[key] = {"id": sid, "bin": int(b) if b else None, "name": "env override",
                             "km": None}
            continue
        best = None
        for pat in cfg["match"]:
            cands = [st for st in local if pat in st.get("name", "").lower()]
            if not cands:
                continue
            for st in cands:
                km = _dist_km(cfg["lat"], cfg["lon"], float(st["lat"]), float(st["lng"]))
                b = st.get("currbin") or 1
                score = (round(km, 1), b)  # nearest, then shallowest bin
                if km <= 8 and (best is None or score < best[0]):
                    best = (score, st, km, b)
            if best:
                break
        if best:
            _, st, km, b = best
            resolved[key] = {"id": st["id"], "bin": b, "name": st["name"], "km": round(km, 2)}
    return resolved


async def fetch_station_catalogue() -> list[dict]:
    async with _client() as c:
        r = await c.get(NOAA_META, params={"type": "currentpredictions"})
        r.raise_for_status()
        return r.json()["stations"]


def regional_catalogue(catalogue: list[dict]) -> list[dict]:
    s, w, n, e = REGION_BBOX
    return sorted(({"id": st["id"], "bin": st.get("currbin"), "name": st["name"],
                    "lat": st["lat"], "lon": st["lng"], "depth": st.get("depth")}
                   for st in catalogue
                   if st.get("lat") is not None and s <= float(st["lat"]) <= n
                   and w <= float(st["lng"]) <= e), key=lambda x: x["name"])


# ---------------------------------------------------------------- currents
async def fetch_currents(station: dict, start: date, end: date) -> list[dict]:
    params = {
        "begin_date": _ymd(start), "end_date": _ymd(end), "station": station["id"],
        "product": "currents_predictions", "interval": "MAX_SLACK",
        "time_zone": "lst_ldt", "units": "english", "format": "json", "application": NOAA_APP,
    }
    if station.get("bin"):
        params["bin"] = station["bin"]
    async with _client() as c:
        r = await c.get(NOAA_DATA, params=params)
        if r.status_code >= 400:
            raise RuntimeError(f"NOAA {r.status_code}: {r.text[:200]}")
        body = r.json()
    if "error" in body:
        raise RuntimeError(body["error"].get("message", body["error"]))
    return parse_currents(body)


def _get(d: dict, *names, default=None):
    lower = {k.lower(): v for k, v in d.items()}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return default


def parse_currents(body: dict) -> list[dict]:
    """Normalise NOAA MAX_SLACK output into [{t, type, v, flood_dir, ebb_dir}].

    type is 'slack', 'flood' or 'ebb'. For slack events, `begins` is set to the
    phase that follows."""
    cp = _get(body, "current_predictions", default=body)
    rows = _get(cp, "cp", default=[]) if isinstance(cp, dict) else cp
    events = []
    for row in rows:
        typ = str(_get(row, "Type", "type", default="")).strip().lower()
        if typ.startswith("slack"):
            typ = "slack"
        elif typ.startswith("flood"):
            typ = "flood"
        elif typ.startswith("ebb"):
            typ = "ebb"
        else:
            continue
        v = _get(row, "Velocity_Major", "velocity_major", "Speed", default=0) or 0
        events.append({
            "t": _parse_noaa_time(_get(row, "Time", "t")),
            "type": typ,
            "v": abs(float(v)),
            "flood_dir": _maybe_float(_get(row, "meanFloodDir", "mean_flood_dir")),
            "ebb_dir": _maybe_float(_get(row, "meanEbbDir", "mean_ebb_dir")),
        })
    events.sort(key=lambda e: e["t"])
    for i, ev in enumerate(events):
        if ev["type"] == "slack":
            nxt = next((x for x in events[i + 1:] if x["type"] != "slack"), None)
            ev["begins"] = nxt["type"] if nxt else None
    return events


def _maybe_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- wind
async def fetch_wind(lat: float, lon: float, start: date, end: date) -> dict:
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "wind_speed_10m,wind_direction_10m,wind_gusts_10m,cloud_cover,"
                  "precipitation_probability,temperature_2m",
        "daily": "sunrise,sunset",
        "wind_speed_unit": "kn", "temperature_unit": "fahrenheit",
        "timezone": "America/New_York",
        "start_date": start.isoformat(), "end_date": end.isoformat(),
    }
    async with _client() as c:
        r = await c.get(OPEN_METEO, params=params)
        r.raise_for_status()
        return parse_wind(r.json())


def parse_wind(body: dict) -> dict:
    h = body["hourly"]
    hours = []
    for i, ts in enumerate(h["time"]):
        hours.append({
            "t": datetime.fromisoformat(ts).replace(tzinfo=TZ),
            "kn": h["wind_speed_10m"][i], "dir": h["wind_direction_10m"][i],
            "gust": h["wind_gusts_10m"][i], "cloud": h.get("cloud_cover", [None] * 999)[i],
            "pop": h.get("precipitation_probability", [None] * 999)[i],
            "temp": h.get("temperature_2m", [None] * 999)[i],
        })
    sun = {}
    d = body.get("daily", {})
    for i, day in enumerate(d.get("time", [])):
        sun[day] = {"rise": datetime.fromisoformat(d["sunrise"][i]).replace(tzinfo=TZ),
                    "set": datetime.fromisoformat(d["sunset"][i]).replace(tzinfo=TZ)}
    return {"hours": hours, "sun": sun}


# ---------------------------------------------------------------- NWS marine text
async def fetch_marine_text() -> dict[str, dict]:
    out = {}
    async with _client() as c:
        for zone, label in NWS_ZONES.items():
            r = await c.get(NWS_TEXT.format(zone=zone))
            r.raise_for_status()
            out[zone] = {"label": label, **parse_marine_text(r.text)}
    return out


def parse_marine_text(text: str) -> dict:
    lines = text.splitlines()
    issued, periods, advisories, cur = None, [], [], None
    for ln in lines:
        s = ln.strip()
        if issued is None and (" EDT " in s or " EST " in s) and any(ch.isdigit() for ch in s):
            issued = s
        if s.startswith("...") and s.endswith("...") and len(s) > 6:
            advisories.append(s.strip("."))
        elif s.startswith(".") and "..." in s:
            name, _, rest = s[1:].partition("...")
            cur = {"name": name.title(), "text": rest.strip()}
            periods.append(cur)
        elif cur is not None and s and not s.startswith("$$") and not s.startswith("Seas are"):
            cur["text"] += " " + s
        elif s.startswith("$$") or s.startswith("Seas are"):
            cur = None
    return {"issued": issued, "advisories": advisories, "periods": periods}


def window(start: date, end: date) -> tuple[date, date]:
    """Fetch window padded by a day either side so phases near midnight resolve."""
    return start - timedelta(days=1), end + timedelta(days=1)
