"""Slack-water and high/low times transcribed from the 2026 Derby tide chart (Oct 8–13).

Used only when NOAA is unreachable. Values are (a.m., p.m.) pairs; None = no event.
"""
from datetime import datetime

from .config import TZ

# station -> date -> (begin_ebb_am, begin_ebb_pm, begin_flood_am, begin_flood_pm)
SLACK = {
    "wasque": {
        "2026-10-08": ("8:53", "9:11", "2:05", "2:40"),
        "2026-10-09": ("9:41", "10:01", "3:00", "3:28"),
        "2026-10-10": ("10:25", "10:47", "3:49", "4:11"),
        "2026-10-11": ("11:07", "11:31", "4:33", "4:51"),
        "2026-10-12": ("11:47", None, "5:15", "5:30"),
        "2026-10-13": ("12:16", "12:26", "5:55", "6:08"),
    },
    "hedge_fence": {
        "2026-10-08": ("10:11", "10:29", "3:30", "4:05"),
        "2026-10-09": ("10:59", "11:19", "4:25", "4:53"),
        "2026-10-10": ("11:43", None, "5:14", "5:36"),
        "2026-10-11": ("12:05", "12:25", "5:58", "6:16"),
        "2026-10-12": ("12:49", "1:05", "6:40", "6:55"),
        "2026-10-13": ("1:33", "1:44", "7:20", "7:33"),
    },
    "east_chop": {
        "2026-10-08": ("10:03", "10:21", "3:15", "3:50"),
        "2026-10-09": ("10:51", "11:11", "4:10", "4:38"),
        "2026-10-10": ("11:35", "11:57", "4:59", "5:21"),
        "2026-10-11": (None, "12:17", "5:43", "6:01"),
        "2026-10-12": ("12:41", "12:57", "6:25", "6:40"),
        "2026-10-13": ("1:25", "1:36", "7:05", "7:18"),
    },
    "norton": {
        "2026-10-08": ("9:18", "9:36", "2:45", "3:20"),
        "2026-10-09": ("10:06", "10:26", "3:40", "4:08"),
        "2026-10-10": ("10:50", "11:12", "4:29", "4:51"),
        "2026-10-11": ("11:32", "11:56", "5:13", "5:31"),
        "2026-10-12": (None, "12:12", "5:55", "6:10"),
        "2026-10-13": ("12:40", "12:51", "6:35", "6:48"),
    },
    "gay_head": {
        "2026-10-08": ("8:53", "9:11", "2:20", "2:56"),
        "2026-10-09": ("9:41", "10:01", "3:15", "3:43"),
        "2026-10-10": ("10:25", "10:47", "4:04", "4:26"),
        "2026-10-11": ("11:07", "11:31", "4:48", "5:06"),
        "2026-10-12": ("11:47", None, "5:30", "5:45"),
        "2026-10-13": ("12:16", "12:26", "6:10", "6:23"),
    },
}

# Edgartown (high_am, high_pm, low_am, low_pm)
EDGARTOWN_HILO = {
    "2026-10-08": ("11:00", "11:22", "4:04", "4:26"),
    "2026-10-09": ("11:47", None, "4:53", "5:17"),
    "2026-10-10": ("12:11", "12:30", "5:38", "6:04"),
    "2026-10-11": ("12:57", "1:10", "6:20", "6:48"),
    "2026-10-12": ("1:41", "1:50", "7:01", "7:31"),
    "2026-10-13": ("2:24", "2:30", "7:41", "8:13"),
}


def _dt(day: str, hm: str | None, pm: bool) -> datetime | None:
    if not hm:
        return None
    h, m = (int(x) for x in hm.split(":"))
    if pm and h != 12:
        h += 12
    if not pm and h == 12:
        h = 0
    y, mo, d = (int(x) for x in day.split("-"))
    return datetime(y, mo, d, h, m, tzinfo=TZ)


def slack_events(station: str) -> list[dict]:
    """Slack events tagged with the phase that begins at that slack."""
    out = []
    for day, (ea, ep, fa, fp) in SLACK.get(station, {}).items():
        for t, phase in ((_dt(day, ea, False), "ebb"), (_dt(day, ep, True), "ebb"),
                         (_dt(day, fa, False), "flood"), (_dt(day, fp, True), "flood")):
            if t:
                out.append({"t": t, "type": "slack", "begins": phase, "v": 0.0})
    return sorted(out, key=lambda e: e["t"])


def hilo_events() -> list[dict]:
    out = []
    for day, (ha, hp, la, lp) in EDGARTOWN_HILO.items():
        for t, typ in ((_dt(day, ha, False), "H"), (_dt(day, hp, True), "H"),
                       (_dt(day, la, False), "L"), (_dt(day, lp, True), "L")):
            if t:
                out.append({"t": t, "type": typ, "v": None})
    return sorted(out, key=lambda e: e["t"])
