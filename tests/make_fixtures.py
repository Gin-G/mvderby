"""Build NOAA/Open-Meteo-shaped fixtures for offline tests (sandbox can't reach the APIs)."""
import json, math, sys
from datetime import timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import derby_fallback as fb

out = Path(__file__).parent / "fixtures"
# Real NOAA response for Edgartown 2026-10-09 (fetched 2026-10-05) + Derby values for other days
tides = {"predictions": [
    {"t": "2026-10-09 04:22", "v": "0.202", "type": "L"}, {"t": "2026-10-09 11:14", "v": "2.593", "type": "H"},
    {"t": "2026-10-09 16:53", "v": "0.055", "type": "L"}, {"t": "2026-10-09 23:49", "v": "2.308", "type": "H"}]}
for e in fb.hilo_events():
    if e["t"].strftime("%Y-%m-%d") != "2026-10-09":
        tides["predictions"].append({"t": e["t"].strftime("%Y-%m-%d %H:%M"), "v": "1.0", "type": e["type"]})
tides["predictions"].sort(key=lambda p: p["t"])
(out / "tides.json").write_text(json.dumps(tides))

# currents_predictions MAX_SLACK shape, synthesised from the Derby slack table
sl = fb.slack_events("east_chop")
cp = []
for a, b in zip(sl, sl[1:]):
    cp.append({"Time": a["t"].strftime("%Y-%m-%d %H:%M"), "Type": "slack", "Velocity_Major": 0,
               "meanFloodDir": 82, "meanEbbDir": 262, "Bin": "1", "Depth": "11"})
    mid = a["t"] + (b["t"] - a["t"]) / 2
    v = 1.9 if a["begins"] == "flood" else -2.1
    cp.append({"Time": mid.strftime("%Y-%m-%d %H:%M"), "Type": a["begins"], "Velocity_Major": v,
               "meanFloodDir": 82, "meanEbbDir": 262, "Bin": "1", "Depth": "11"})
(out / "currents_east_chop.json").write_text(json.dumps({"current_predictions": {"units": "knots", "cp": cp}}))

# Open-Meteo shape: NE 12 kn dawn building to 18 midday Sat, light W otherwise
hours, kn, dr, gu, cc = [], [], [], [], []
from datetime import datetime
t = datetime(2026, 10, 9, 0, 0)
while t < datetime(2026, 10, 13, 0, 0):
    hours.append(t.strftime("%Y-%m-%dT%H:%M"))
    sat = t.day == 10
    k = (10 + 8 * math.sin(math.pi * min(t.hour, 16) / 16)) if sat else 6 + 3 * math.sin(t.hour / 4)
    kn.append(round(k, 1)); dr.append(45 if sat else 250); gu.append(round(k * 1.35, 1))
    cc.append(70 if sat else 10)
    t += timedelta(hours=1)
wind = {"hourly": {"time": hours, "wind_speed_10m": kn, "wind_direction_10m": dr, "wind_gusts_10m": gu,
                   "cloud_cover": cc, "precipitation_probability": [10] * len(hours),
                   "temperature_2m": [58] * len(hours)},
        "daily": {"time": ["2026-10-09", "2026-10-10", "2026-10-11", "2026-10-12"],
                  "sunrise": ["2026-10-09T06:56", "2026-10-10T06:57", "2026-10-11T06:58", "2026-10-12T06:59"],
                  "sunset": ["2026-10-09T18:13", "2026-10-10T18:11", "2026-10-11T18:10", "2026-10-12T18:08"]}}
(out / "wind.json").write_text(json.dumps(wind))
print("fixtures written")
