import json
from datetime import date, datetime
from pathlib import Path

import pytest

from app import derby_fallback, sources
from app.config import CURRENT_STATIONS, SPOTS, TZ
from app.engine import CurrentModel, TideModel, build_plan, light_factor, wind_factor

FX = Path(__file__).parent / "fixtures"
DAYS = [date(2026, 10, 9), date(2026, 10, 10), date(2026, 10, 11), date(2026, 10, 12)]


def _fx(name):
    return json.loads((FX / name).read_text())


def test_parse_tides_real_noaa_shape():
    ev = sources.parse_tides(_fx("tides.json"))
    oct9 = [e for e in ev if e["t"].date() == date(2026, 10, 9)]
    assert [e["type"] for e in oct9] == ["L", "H", "L", "H"]
    assert oct9[1]["t"] == datetime(2026, 10, 9, 11, 14, tzinfo=TZ)


def test_parse_currents_tags_phase_after_slack():
    ev = sources.parse_currents(_fx("currents_east_chop.json"))
    sat = [e for e in ev if e["t"].date() == date(2026, 10, 10) and e["type"] == "slack"]
    # Derby: East Chop Sat flood begins 4:59a, ebb begins 11:35a
    first = sat[0]
    assert first["t"].strftime("%H:%M") == "04:59" and first["begins"] == "flood"
    assert any(e["t"].strftime("%H:%M") == "11:35" and e["begins"] == "ebb" for e in sat)
    assert all(e["flood_dir"] == 82 for e in ev if e["type"] != "slack")


def test_parse_currents_tolerates_lowercase_and_bare_list():
    rows = [{"time": "2026-10-10 05:00", "type": "Slack", "velocity_major": 0},
            {"time": "2026-10-10 08:00", "type": "Flood", "velocity_major": 1.4},
            {"time": "2026-10-10 11:00", "type": "Slack", "velocity_major": 0}]
    ev = sources.parse_currents({"current_predictions": {"cp": rows}})
    assert ev[0]["begins"] == "flood" and ev[1]["v"] == 1.4


def test_current_model_peaks_midway():
    m = CurrentModel(sources.parse_currents(_fx("currents_east_chop.json")), 90)
    s = m.state(datetime(2026, 10, 10, 8, 15, tzinfo=TZ))  # mid-flood 4:59–11:35
    assert s["phase"] == "flood" and s["flow"] > 0.9
    near_slack = m.state(datetime(2026, 10, 10, 11, 30, tzinfo=TZ))
    assert near_slack["flow"] < 0.1


def test_tide_model_lag_and_outflow():
    hilo = sources.parse_tides(_fx("tides.json"))
    m = TideModel(hilo, 60, "falling")
    s = m.state(datetime(2026, 10, 9, 12, 0, tzinfo=TZ))  # high 11:14 + 60 = 12:14 -> still rising
    assert s["phase"] == "rising" and not s["outflow"]
    s2 = m.state(datetime(2026, 10, 9, 14, 30, tzinfo=TZ))
    assert s2["phase"] == "falling" and s2["outflow"]


def test_fallback_slack_am_pm():
    ev = derby_fallback.slack_events("hedge_fence")
    mon = [e for e in ev if e["t"].date() == date(2026, 10, 12)]
    assert [e["t"].strftime("%H:%M") for e in mon] == ["00:49", "06:40", "13:05", "18:55"]


def test_resolve_stations_picks_nearest_in_region():
    cat = [
        {"id": "ACT0396", "name": "The Reach, Norton Point", "lat": 44.03, "lng": -68.84, "currbin": 1},
        {"id": "ACT9001", "name": "Norton Point, 0.5 mile north of", "lat": 41.458, "lng": -70.655, "currbin": 1},
        {"id": "ACT9002", "name": "East Chop, 1 mile north of", "lat": 41.485, "lng": -70.567, "currbin": 2},
        {"id": "ACT9003", "name": "East Chop-Squash Meadow, between", "lat": 41.47, "lng": -70.54, "currbin": 1},
    ]
    r = sources.resolve_stations(cat)
    assert r["norton"]["id"] == "ACT9001"  # Maine namesake excluded by bbox
    assert r["east_chop"]["id"] == "ACT9002"  # specific pattern wins
    assert "wasque" not in r


def test_marine_text():
    m = sources.parse_marine_text((FX / "anz232.txt").read_text())
    assert m["advisories"] == ["SMALL CRAFT ADVISORY IN EFFECT UNTIL 8 PM EDT THIS EVENING"]
    assert m["periods"][1]["name"] == "Sat" and "N winds 10 to 15 kt" in m["periods"][1]["text"]
    assert "Seas are reported" not in " ".join(p["text"] for p in m["periods"])


@pytest.fixture(scope="module")
def plan():
    currents = {k: derby_fallback.slack_events(k) for k in CURRENT_STATIONS}
    currents["east_chop"] = sources.parse_currents(_fx("currents_east_chop.json"))
    return build_plan(tides=sources.parse_tides(_fx("tides.json")), currents=currents,
                      wind=sources.parse_wind(_fx("wind.json")), days=DAYS, sources={})


def test_plan_shape(plan):
    assert [d["date"] for d in plan["days"]] == [d.isoformat() for d in DAYS]
    sat = plan["days"][1]
    assert sat["special"].startswith("BONITO SUPER SATURDAY")
    assert len(sat["slots"]) == 48  # full day, 30-min steps
    assert sat["slots"][0]["t"][11:16] == "00:00" and sat["slots"][-1]["t"][11:16] == "23:30"
    assert all(c["s"] is None or 0 <= c["s"] <= 100 for s in sat["slots"] for c in s["cells"].values())
    json.dumps(plan)


def _cell(p, day, hhmm, spot):
    slot = next(s for s in p["days"][day]["slots"] if s["t"][11:16] == hhmm)
    return slot["cells"][spot]


def test_saturday_dawn_flood_ranks_east_chop_high_without_wind():
    currents = {"east_chop": sources.parse_currents(_fx("currents_east_chop.json"))}
    calm = build_plan(tides=sources.parse_tides(_fx("tides.json")), currents=currents,
                      wind=None, days=DAYS, sources={})
    ec = _cell(calm, 1, "07:30", "east_chop")
    assert ec["p"] == "flood" and ec["s"] >= 80, ec
    assert any("first light" in r for r in ec["r"])


def test_onshore_wind_docks_east_chop_at_dawn(plan):
    ec = _cell(plan, 1, "07:30", "east_chop")  # fixture: NE ~18 kn at 07:00 Sat
    assert ec["s"] < 70 and any("onshore" in r for r in ec["r"]), ec


def test_onshore_wind_penalises_exposed_shore(plan):
    sat = plan["days"][1]
    slot = next(s for s in sat["slots"] if s["t"].startswith("2026-10-10T12:00"))
    # NE ~18 kn: Big Bridge faces NE/E, Menemsha (NW-facing) is in the lee
    assert any("onshore" in r or "blowing in" in r for r in slot["cells"]["big_bridge"]["r"])
    assert any("lee" in r for r in slot["cells"]["menemsha"]["r"])


def test_windows_exist_and_have_lures(plan):
    for d in plan["days"]:
        assert d["windows"], d["date"]
        assert all(w["lure"] and w["start"] < w["end"] for w in d["windows"])


def _spot(sid):
    return next(s for s in SPOTS if s["id"] == sid)


def test_night_penalty_depends_on_target_species():
    sun = {"rise": datetime(2026, 10, 10, 6, 55, tzinfo=TZ), "set": datetime(2026, 10, 10, 18, 15, tzinfo=TZ)}
    night = datetime(2026, 10, 10, 22, 0, tzinfo=TZ)
    blues, _ = light_factor(night, sun, _spot("wasque"))         # targets blues
    albies, _ = light_factor(night, sun, _spot("ferry_dock"))    # albies/bonito only
    assert blues >= 0.75 and albies <= 0.2


def test_nw_wind_pushes_bait_onto_wasque():
    nw = {"kn": 12, "dir": 315, "gust": 16, "cloud": 80}
    f, reasons, _ = wind_factor(_spot("wasque_shoals"), nw, None)
    assert f > 1.0 and any(r.startswith("Bait push:") for r in reasons)
    f_ne, reasons_ne, _ = wind_factor(_spot("wasque_shoals"), {**nw, "dir": 45}, None)
    assert f_ne <= 1.0 and not any(r.startswith("Bait push:") for r in reasons_ne)
