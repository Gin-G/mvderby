import asyncio
import json
from pathlib import Path

from app import refresh as rf
from app import sources

FX = Path(__file__).parent / "fixtures"


async def _boom(*a, **k):
    raise RuntimeError("network down")


def _patch_all_down(monkeypatch):
    for name in ("fetch_tides", "fetch_wind", "fetch_marine_text", "fetch_station_catalogue",
                 "fetch_currents"):
        monkeypatch.setattr(sources, name, _boom)


def test_cold_start_offline_uses_derby_fallback(tmp_path, monkeypatch):
    _patch_all_down(monkeypatch)
    plan = asyncio.run(rf.refresh(rf.Store(tmp_path)))
    assert plan["sources"]["tides"]["source"] == "Derby PDF (fallback)"
    assert plan["sources"]["cur_wasque"]["source"] == "Derby PDF (fallback)"
    assert all(d["windows"] for d in plan["days"])
    assert (tmp_path / "plan.json").exists()


def test_last_good_survives_outage_and_restart(tmp_path, monkeypatch):
    async def tides(*a):
        return sources.parse_tides(json.loads((FX / "tides.json").read_text()))

    _patch_all_down(monkeypatch)
    monkeypatch.setattr(sources, "fetch_tides", tides)
    asyncio.run(rf.refresh(rf.Store(tmp_path)))

    monkeypatch.setattr(sources, "fetch_tides", _boom)
    plan = asyncio.run(rf.refresh(rf.Store(tmp_path)))  # fresh Store = pod restart
    assert plan["sources"]["tides"]["source"] == "NOAA 8448558 (cached)"
    assert plan["sources"]["tides"]["ok"] is False
