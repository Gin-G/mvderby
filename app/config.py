"""Static configuration: trip window, NOAA stations, fishing spots."""
import os
from datetime import date
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")

TRIP_START = date.fromisoformat(os.getenv("TRIP_START", "2026-10-09"))
TRIP_END = date.fromisoformat(os.getenv("TRIP_END", "2026-10-12"))
DATA_DIR = os.getenv("DATA_DIR", "/data")
REFRESH_MINUTES = int(os.getenv("REFRESH_MINUTES", "20"))
NOAA_APP = "mvderby_nickknows"

# NOAA tide prediction station (high/low).
TIDE_STATION = os.getenv("TIDE_STATION", "8448558")  # Edgartown

# NWS coastal waters zones (raw text products).
NWS_ZONES = {
    "anz232": "Nantucket Sound",
    "anz233": "Vineyard Sound",
}

# Current-prediction stations. NOAA IDs are discovered at runtime by name + proximity
# (override any with env CURRENT_<KEY>=<id>[:<bin>]). `derby` keys map to the
# Derby PDF slack table used when NOAA is unreachable.
CURRENT_STATIONS = {
    "east_chop": {
        "label": "East Chop (1 mi N)",
        "match": ["east chop, 1 mile north", "east chop"],
        "lat": 41.4847, "lon": -70.5675,
        "flood_set": 90,
    },
    "hedge_fence": {
        "label": "Hedge Fence (Gong 22)",
        "match": ["hedge fence"],
        "lat": 41.4929, "lon": -70.5303,
        "flood_set": 90,
    },
    "wasque": {
        "label": "Muskeget Ch. (W end, off Wasque)",
        "match": ["wasque", "muskeget channel"],
        "lat": 41.3483, "lon": -70.42,
        "flood_set": 70,
    },
    "norton": {
        "label": "Norton Pt / Tashmoo (0.5 mi N)",
        "match": ["norton point"],
        "lat": 41.457, "lon": -70.6553,
        "flood_set": 60,
    },
    "gay_head": {
        "label": "Gay Head (1.5 mi NW)",
        "match": ["gay head", "aquinnah"],
        "lat": 41.364, "lon": -70.857,
        "flood_set": 60,
    },
}

# Region used to filter NOAA's station catalogue before name matching.
REGION_BBOX = (41.25, -71.0, 41.62, -70.25)  # south, west, north, east

# Fishing spots. `flow` = how the moving-water signal is derived:
#   ("current", station_key)                 -> NOAA current predictions
#   ("tide", lag_minutes, "outflow_on")      -> Edgartown hi/lo, shifted by lag;
#                                               outflow_on = "falling" means water
#                                               dumps out of the pond/harbor on the drop
# `phase_pref` weights each phase (1.0 = best).
# `exposed` = wind-from sectors (deg) that blow onto the spot (bad when strong).
# `push` = wind-from sectors that drive bait onto the spot (bonus at moderate speed).
SPOTS = [
    {
        "id": "lighthouse", "short": "Lighthouse", "name": "Edgartown Lighthouse Beach", "mode": "shore",
        "lat": 41.3893, "lon": -70.5031,
        "flow": ("tide", 20, "falling"),
        "phase_pref": {"falling": 1.0, "rising": 0.75},
        "exposed": [(0, 90)],
        "targets": ["bonito", "albie"],
        "notes": "Point drops from 2 ft to 25 ft. Ebb: fish the outflow seam. "
                 "Flood: fish swim past into the harbor — work toward the ferry dock.",
    },
    {
        "id": "ferry_dock", "short": "Ferry dock", "name": "Chappy Ferry / Memorial Wharf", "mode": "shore",
        "lat": 41.3887, "lon": -70.5113,
        "flow": ("tide", 20, "falling"),
        "phase_pref": {"rising": 1.0, "falling": 0.6},
        "exposed": [(20, 70)],
        "targets": ["albie", "bonito"],
        "notes": "Inside harbor. Flood pins bait against pilings. An albie came off here last trip.",
    },
    {
        "id": "big_bridge", "short": "Big Bridge", "name": "Big Bridge (Jaws)", "mode": "shore",
        "lat": 41.4161, "lon": -70.5487,
        "flow": ("tide", 60, "falling"),
        "phase_pref": {"falling": 1.0, "rising": 0.5},
        "exposed": [(30, 140)],
        "targets": ["bonito", "albie", "blues"],
        "notes": "Sengekontacket dumps on the drop. Fish the outflow on either side. Kid friendly.",
    },
    {
        "id": "gut_shore", "short": "Gut", "name": "Cape Poge Gut (shore)", "mode": "shore",
        "lat": 41.4130, "lon": -70.4570,
        "flow": ("tide", 45, "falling"),
        "phase_pref": {"falling": 1.0, "rising": 0.95},
        "exposed": [(330, 360), (0, 80)],
        "targets": ["albie", "bonito", "blues"],
        "notes": "Fishes both ways. Flood pushes bait through the throat into the bay. "
                 "Current lags posted tide — bay keeps draining past low.",
    },
    {
        "id": "leland", "short": "Leland", "name": "Leland Beach (East Beach)", "mode": "shore",
        "lat": 41.3900, "lon": -70.4470,
        "flow": ("current", "wasque"),
        "phase_pref": {"flood": 1.0, "ebb": 0.9},
        "exposed": [(30, 170)],
        "targets": ["albie", "bonito", "blues"],
        "notes": "Park at Dike Bridge, walk on. No OSV permit needed. Same water as Wasque/Gut.",
    },
    {
        "id": "wasque", "short": "Wasque", "name": "Wasque Point", "mode": "shore",
        "lat": 41.3525, "lon": -70.4530,
        "flow": ("current", "wasque"),
        "phase_pref": {"flood": 1.0, "ebb": 1.0},
        "exposed": [(30, 220)],
        "push": [(290, 345)],
        "targets": ["blues", "albie", "bonito"],
        "notes": "Rip runs to 6 kn. Call Trustees for access status. Cast into the rip line.",
    },
    {
        "id": "east_chop", "short": "E. Chop", "name": "East Chop Bluff", "mode": "shore",
        "lat": 41.4703, "lon": -70.5675,
        "flow": ("current", "east_chop"),
        "phase_pref": {"flood": 1.0, "ebb": 0.9},
        "exposed": [(320, 360), (0, 70)],
        "targets": ["bonito", "albie"],
        "notes": "Deep water close in. Good place to spot busting fish before committing.",
    },
    {
        "id": "menemsha", "short": "Menemsha", "name": "Menemsha Jetty", "mode": "shore",
        "lat": 41.3550, "lon": -70.7669,
        "flow": ("current", "gay_head"),
        "phase_pref": {"flood": 1.0, "ebb": 0.9},
        "exposed": [(250, 360)],
        "targets": ["bonito", "albie"],
        "notes": "45 min from Edgartown. Best as an evening session + dinner.",
    },
    {
        "id": "hedge_fence", "short": "Hedge F.", "name": "Hedge Fence", "mode": "boat",
        "lat": 41.4929, "lon": -70.5303,
        "flow": ("current", "hedge_fence"),
        "phase_pref": {"flood": 1.0, "ebb": 1.0},
        "exposed": [(0, 360)],
        "rip": True,
        "targets": ["bonito", "albie", "blues"],
        "notes": "On the Falmouth crossing line. Fish the down-current edge of the color line.",
    },
    {
        "id": "squash_meadow", "short": "Squash M.", "name": "Squash Meadow", "mode": "boat",
        "lat": 41.4673, "lon": -70.5267,
        "flow": ("current", "east_chop"),
        "phase_pref": {"flood": 1.0, "ebb": 1.0},
        "exposed": [(0, 360)],
        "rip": True,
        "targets": ["bonito", "albie"],
        "notes": "Between East Chop and Hedge Fence — one continuous run on the flood.",
    },
    {
        "id": "elbow", "short": "Elbow", "name": "Cape Poge Elbow", "mode": "boat",
        "lat": 41.4130, "lon": -70.4455,
        "flow": ("current", "wasque"),
        "phase_pref": {"flood": 1.0, "ebb": 1.0},
        "exposed": [(0, 180)],
        "rip": True,
        "targets": ["albie", "bonito", "blues"],
        "notes": "Rip on the NE corner of Chappy, drops into the Sound.",
    },
    {
        "id": "wasque_rip", "short": "Wasque rip", "name": "Wasque Rip / Muskeget", "mode": "boat",
        "lat": 41.3420, "lon": -70.4300,
        "flow": ("current", "wasque"),
        "phase_pref": {"flood": 1.0, "ebb": 1.0},
        "exposed": [(20, 260)],  # W through N blows off Chappy/MV
        "push": [(290, 345)],
        "rip": True,
        "danger_kn": 14,
        "targets": ["blues", "albie"],
        "notes": "Heaviest water on the island. Settled conditions only.",
    },
    {
        "id": "mutton_shoal", "short": "Mutton Sh.", "name": "Mutton Shoal (SE of Wasque)", "mode": "boat",
        "lat": 41.3250, "lon": -70.4000,
        "flow": ("current", "wasque"),
        "phase_pref": {"flood": 1.0, "ebb": 1.0},
        "exposed": [(20, 260)],
        "push": [(290, 345)],
        "rip": True,
        "danger_kn": 14,
        "targets": ["blues", "albie", "bonito"],
        "notes": "West edge of Mutton Shoal by bell \"2\", where the Muskeget Channel current "
                 "(3.5 kn) piles up. A NW wind lays the sea down and pushes bait onto the shoal.",
    },
    {
        "id": "middle_ground", "short": "Mid Ground", "name": "Middle Ground", "mode": "boat",
        "lat": 41.4657, "lon": -70.6846,
        "flow": ("current", "norton"),
        "phase_pref": {"flood": 1.0, "ebb": 1.0},
        "exposed": [(0, 360)],
        "rip": True,
        "targets": ["bonito", "blues", "sea bass"],
        "notes": "Long shoal in Vineyard Sound. Also the sea bass / scup fallback.",
    },
]

DERBY = {
    "start": "2026-09-13", "end": "2026-10-17",
    "weigh_in": "8–10am & 7–9pm, Edgartown Jr. Yacht Club",
    "minimums": {"bluefish": 22, "bonito": 21, "albie": 25},
    "specials": {"2026-10-10": "BONITO SUPER SATURDAY — $500/$300/$200 overall, shore & boat"},
}
