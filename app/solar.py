"""NOAA sunrise/sunset approximation (±2 min). Used when Open-Meteo is unavailable."""
import math
from datetime import date, datetime, timedelta, timezone

from .config import TZ


def sun_times(d: date, lat: float, lon: float) -> dict:
    n = d.timetuple().tm_yday
    gamma = 2 * math.pi / 365 * (n - 1)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                    - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    lat_r = math.radians(lat)
    ha = math.degrees(math.acos(math.cos(math.radians(90.833)) / (math.cos(lat_r) * math.cos(decl))
                                - math.tan(lat_r) * math.tan(decl)))
    base = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    rise = base + timedelta(minutes=720 - 4 * (lon + ha) - eqt)
    sset = base + timedelta(minutes=720 - 4 * (lon - ha) - eqt)
    return {"rise": rise.astimezone(TZ), "set": sset.astimezone(TZ)}
