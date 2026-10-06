"""Turns tides, currents, wind and light into per-spot scores every 30 minutes."""
import math
from bisect import bisect_right
from datetime import date, datetime, timedelta

from .config import CURRENT_STATIONS, DERBY, SPOTS, TZ
from .solar import sun_times

STEP = timedelta(minutes=30)
DAY_START_H, DAY_END_H = 4, 20  # inclusive range of slots shown per day


def _ang(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


def _in_sector(deg: float, sectors) -> bool:
    deg %= 360
    for lo, hi in sectors:
        if lo <= hi and lo <= deg <= hi:
            return True
        if lo > hi and (deg >= lo or deg <= hi):
            return True
    return False


COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def compass(deg: float | None) -> str:
    return "?" if deg is None else COMPASS[int((deg % 360) / 22.5 + 0.5) % 16]


def hm(t: datetime | None) -> str:
    if t is None:
        return "—"
    s = t.strftime("%-I:%M%p").lower()
    return s[:-1]


# ------------------------------------------------------------------ flow models
class CurrentModel:
    def __init__(self, events: list[dict], flood_set: float):
        self.events = events
        self.slacks = [e for e in events if e["type"] == "slack"]
        self.maxes = [e for e in events if e["type"] != "slack"]
        self.st = [e["t"] for e in self.slacks]
        self.peak = max((e["v"] for e in self.maxes), default=0) or None
        fd = next((e["flood_dir"] for e in self.maxes if e.get("flood_dir") is not None), None)
        ed = next((e["ebb_dir"] for e in self.maxes if e.get("ebb_dir") is not None), None)
        self.flood_dir = fd if fd is not None else flood_set
        self.ebb_dir = ed if ed is not None else (self.flood_dir + 180) % 360

    def state(self, t: datetime) -> dict | None:
        i = bisect_right(self.st, t)
        if i == 0 or i >= len(self.slacks):
            return None
        a, b = self.slacks[i - 1], self.slacks[i]
        phase = a.get("begins")
        frac = (t - a["t"]) / (b["t"] - a["t"])
        mx = next((m for m in self.maxes if a["t"] <= m["t"] <= b["t"]), None)
        if phase is None and mx:
            phase = mx["type"]
        rel = (mx["v"] / self.peak) if (mx and self.peak) else 1.0
        strength = math.sin(math.pi * frac) * (0.4 + 0.6 * rel)
        return {
            "phase": phase or "slack", "flow": max(0.0, strength), "frac": frac,
            "max_t": mx["t"] if mx else a["t"] + (b["t"] - a["t"]) / 2,
            "max_v": mx["v"] if mx else None, "next_slack": b["t"], "prev_slack": a["t"],
            "set": self.flood_dir if phase == "flood" else self.ebb_dir,
        }


class TideModel:
    def __init__(self, hilo: list[dict], lag_min: int, outflow_on: str):
        lag = timedelta(minutes=lag_min)
        self.ev = [{**e, "t": e["t"] + lag} for e in hilo]
        self.tt = [e["t"] for e in self.ev]
        self.outflow_on = outflow_on

    def state(self, t: datetime) -> dict | None:
        i = bisect_right(self.tt, t)
        if i == 0 or i >= len(self.ev):
            return None
        a, b = self.ev[i - 1], self.ev[i]
        phase = "falling" if a["type"] == "H" else "rising"
        frac = (t - a["t"]) / (b["t"] - a["t"])
        return {
            "phase": phase, "flow": math.sin(math.pi * frac), "frac": frac,
            "max_t": a["t"] + (b["t"] - a["t"]) / 2, "max_v": None,
            "next_slack": b["t"], "prev_slack": a["t"], "set": None,
            "outflow": phase == self.outflow_on,
        }


# ------------------------------------------------------------------ factors
def light_factor(t: datetime, sun: dict, mode: str) -> tuple[float, str | None]:
    rise, sset = sun["rise"], sun["set"]
    m_rise = (t - rise).total_seconds() / 60
    m_set = (sset - t).total_seconds() / 60
    if -45 <= m_rise <= 150:
        return 1.0, "Light: first light (prime bite)"
    if -20 <= m_set <= 120:
        return 0.85, "Light: last light (good bite)"
    if m_rise > 0 and m_set > 0:
        return 0.6, None
    return (0.15 if mode == "shore" else 0.05), "Light: dark"


def wind_factor(spot: dict, w: dict | None, cur: dict | None) -> tuple[float, list[str], list[str]]:
    if not w or w.get("kn") is None:
        return 1.0, [], []
    kn, d, gust = w["kn"], w["dir"], w.get("gust") or w["kn"]
    reasons, warn = [], []
    exposed = _in_sector(d, spot["exposed"])
    f = 1.0
    if spot["mode"] == "shore":
        if exposed and kn > 20:
            f = 0.3
            reasons.append(f"Wind: {compass(d)} {kn:.0f} kn blowing in — hard casting")
        elif exposed and kn > 14:
            f = 0.65
            reasons.append(f"Wind: {compass(d)} {kn:.0f} kn onshore")
        elif exposed and kn >= 6:
            reasons.append("Wind: light chop — helps")
        elif not exposed:
            if kn >= 10:
                reasons.append(f"Wind: sheltered from {compass(d)} {kn:.0f} kn (in the lee)")
            f = 1.0 if kn <= 20 else 0.85
    else:
        if gust >= 25 or kn >= 20:
            f = 0.35 if exposed else 0.6
            warn.append(f"{compass(d)} {kn:.0f} G{gust:.0f} kn — rough for the boat")
        elif kn >= 15 and exposed:
            f = 0.7
            reasons.append(f"Wind: {compass(d)} {kn:.0f} kn — sloppy")
        elif kn >= 6:
            reasons.append("Wind: some chop — fish less wary")
    if kn < 5 and (w.get("cloud") is not None and w["cloud"] < 30):
        f *= 0.9
        reasons.append("Conditions: glass calm and sunny — fish will be spooky")

    # wind against tide
    if cur and cur.get("set") is not None and cur["flow"] > 0.35 and spot.get("rip"):
        if _ang(d, cur["set"]) < 50:  # wind coming FROM where the current is heading
            if kn >= 16:
                f *= 0.5
                warn.append(f"wind against {cur['phase']} at {kn:.0f} kn — rip will be dangerous")
            elif kn >= 8:
                f *= 1.06
                reasons.append("Rip: wind against tide — rip standing up")
        dk = spot.get("danger_kn")
        if dk and kn >= dk:
            warn.append(f"{spot['name']}: >{dk} kn wind, settled conditions only")
    return f, [r for r in reasons if r], warn


# ------------------------------------------------------------------ main
def build_plan(*, tides: list[dict], currents: dict[str, list[dict]], wind: dict | None,
               days: list[date], sources: dict) -> dict:
    sun_by_day = {}
    for d in days:
        key = d.isoformat()
        if wind and key in wind.get("sun", {}):
            sun_by_day[key] = wind["sun"][key]
        else:
            sun_by_day[key] = sun_times(d, 41.39, -70.51)

    cmodels = {k: CurrentModel(ev, CURRENT_STATIONS[k]["flood_set"])
               for k, ev in currents.items() if ev}
    wind_hours = {}
    for h in (wind or {}).get("hours", []):
        wind_hours[h["t"].replace(minute=0)] = h

    def wind_at(t):
        return wind_hours.get(t.replace(minute=0, second=0, microsecond=0))

    def flow_for(spot, t):
        kind = spot["flow"][0]
        if kind == "current":
            m = cmodels.get(spot["flow"][1])
            return m.state(t) if m else None
        _, lag, outflow = spot["flow"]
        return TideModel(tides, lag, outflow).state(t) if tides else None

    tide_models = {}

    def flow_cached(spot, t):
        if spot["flow"][0] == "tide":
            key = spot["flow"][1:]
            if key not in tide_models:
                tide_models[key] = TideModel(tides, spot["flow"][1], spot["flow"][2]) if tides else None
            m = tide_models[key]
            return m.state(t) if m else None
        return flow_for(spot, t)

    out_days = []
    for d in days:
        key = d.isoformat()
        sun = sun_by_day[key]
        slots = []
        t = datetime(d.year, d.month, d.day, DAY_START_H, 0, tzinfo=TZ)
        end = datetime(d.year, d.month, d.day, DAY_END_H, 0, tzinfo=TZ)
        while t <= end:
            w = wind_at(t)
            cells = {}
            for spot in SPOTS:
                cur = flow_cached(spot, t)
                reasons, warn = [], []
                if cur is None:
                    cells[spot["id"]] = {"s": None, "r": ["Data: no tide/current data"], "w": []}
                    continue
                flow = cur["flow"]
                pref = spot["phase_pref"].get(cur["phase"], 0.8)
                lf, lr = light_factor(t, sun, spot["mode"])
                wf, wr, ww = wind_factor(spot, w, cur)
                score = 94 * (0.12 + 0.88 * flow ** 0.8) * pref * lf * wf
                if spot["flow"][0] == "tide":
                    drain = "draining out" if cur.get("outflow") else "pushing in"
                    reasons.append(f"Tide: {cur['phase']} (water {drain})")
                else:
                    reasons.append(f"Current: {cur['phase']}")
                reasons.append(f"Flow strength: {int(flow * 100)}% of max")
                if cur.get("max_v"):
                    reasons.append(f"Peak flow: {cur['max_v']:.1f} kn at {hm(cur['max_t'])}")
                else:
                    reasons.append(f"Peak flow: around {hm(cur['max_t'])}")
                if flow < 0.2:
                    reasons.append(f"Slack: water nearly still — turns at {hm(cur['next_slack'])}")
                if pref >= 1.0 and cur["phase"] in spot["phase_pref"] and len(spot["phase_pref"]) > 1 \
                        and min(spot["phase_pref"].values()) < 0.9:
                    reasons.append(f"Direction: {cur['phase']} is the best tide for this spot")
                if lr:
                    reasons.append(lr)
                reasons += wr
                warn += ww
                cells[spot["id"]] = {"s": int(round(min(100, score))), "r": reasons, "w": warn,
                                     "p": cur["phase"]}
            slots.append({"t": t.isoformat(), "wind": _wind_brief(w), "cells": cells})
            t += STEP
        out_days.append({
            "date": key, "label": d.strftime("%a %b %-d"),
            "sun": {"rise": sun["rise"].isoformat(), "set": sun["set"].isoformat()},
            "special": DERBY["specials"].get(key),
            "slots": slots,
            "windows": _windows(slots),
        })

    return {
        "generated": datetime.now(TZ).isoformat(),
        "days": out_days,
        "spots": [{k: v for k, v in s.items() if k not in ("flow",)}
                  | {"flow_ref": _flow_label(s)} for s in SPOTS],
        "stations": _station_tables(currents, days),
        "tides": [{"t": e["t"].isoformat(), "type": e["type"], "v": e["v"]}
                  for e in tides if e["t"].date() in days],
        "wind": [_wind_full(h) for h in (wind or {}).get("hours", []) if h["t"].date() in days],
        "sources": sources,
        "derby": DERBY,
    }


def _flow_label(spot):
    if spot["flow"][0] == "current":
        return CURRENT_STATIONS[spot["flow"][1]]["label"]
    lag = spot["flow"][1]
    return f"Edgartown tide +{lag} min"


def _wind_brief(w):
    if not w:
        return None
    return {"kn": round(w["kn"]), "g": round(w.get("gust") or w["kn"]), "d": round(w["dir"]),
            "c": compass(w["dir"])}


def _wind_full(h):
    return {"t": h["t"].isoformat(), "kn": round(h["kn"], 1), "gust": round(h["gust"] or 0, 1),
            "dir": round(h["dir"]), "c": compass(h["dir"]), "cloud": h.get("cloud"),
            "pop": h.get("pop"), "temp": h.get("temp")}


def _windows(slots, top=8):
    by_spot = {}
    best_day = max((c["s"] or 0 for s in slots for c in s["cells"].values()), default=0)
    thresh = max(55, best_day * 0.78)
    for spot in SPOTS:
        sid, run = spot["id"], []
        for s in slots + [None]:
            sc = s["cells"][sid]["s"] if s else None
            if sc is not None and sc >= thresh:
                run.append((s, sc))
            elif run:
                peak_s, peak = max(run, key=lambda x: x[1])
                by_spot.setdefault(sid, []).append({
                    "spot": sid, "start": run[0][0]["t"],
                    "end": (datetime.fromisoformat(run[-1][0]["t"]) + STEP).isoformat(),
                    "peak": peak, "peak_t": peak_s["t"],
                    "why": peak_s["cells"][sid]["r"], "warn": peak_s["cells"][sid]["w"],
                    "lure": _lure_hint(spot, peak_s),
                })
                run = []
    flow_src = {sp["id"]: (sp["flow"][0], sp["flow"][1]) for sp in SPOTS}
    per_spot = [max(ws, key=lambda w: w["peak"]) for ws in by_spot.values()]
    per_spot.sort(key=lambda w: -w["peak"])
    seen, out = {}, []
    for w in per_spot:
        k = flow_src[w["spot"]]
        if seen.get(k, 0) >= 2:
            continue
        seen[k] = seen.get(k, 0) + 1
        out.append(w)
    return out[:top]


def _lure_hint(spot, slot):
    t = datetime.fromisoformat(slot["t"])
    w = slot.get("wind") or {}
    reasons = " ".join(slot["cells"][spot["id"]]["r"])
    if "glass calm" in reasons:
        return "Albie Snax (pearl), 12 lb leader, long casts"
    if spot["mode"] == "boat":
        if (w.get("kn") or 0) >= 12:
            return "Hogy epoxy 1.25 oz / Deadly Dick — burn it; troll X-Rap Magnum 6–7 kn if blank"
        return "Epoxy on one rod, X-Rap 08 on the lightest rod, Snax rigged"
    if "first light" in reasons:
        return "X-Rap 08 Crystal Shad first; epoxy on 2nd rod; Snax ready"
    if (w.get("kn") or 0) >= 14:
        return "Kastmaster 3/4 oz or Hogy 1.25 oz to punch the wind"
    return "Epoxy / Kastmaster to find them, X-Rap or Snax when they're picky"


def _station_tables(currents, days):
    out = {}
    for key, ev in currents.items():
        rows = [{"t": e["t"].isoformat(), "type": e["type"], "v": e.get("v"),
                 "begins": e.get("begins")} for e in ev if e["t"].date() in days]
        out[key] = {"label": CURRENT_STATIONS[key]["label"], "events": rows}
    return out
