"""Run the app locally with upstream APIs replaced by tests/fixtures (for dev without network)."""
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATA_DIR", str(ROOT / ".devdata"))
from app import sources
FX = ROOT / "tests" / "fixtures"
async def tides(*a): return sources.parse_tides(json.loads((FX / "tides.json").read_text()))
async def wind(*a): return sources.parse_wind(json.loads((FX / "wind.json").read_text()))
async def marine(): return {"anz232": {"label": "Nantucket Sound", **sources.parse_marine_text((FX / "anz232.txt").read_text())}}
async def cat(): raise RuntimeError("offline dev: using Derby fallback for stations")
sources.fetch_tides, sources.fetch_wind, sources.fetch_marine_text, sources.fetch_station_catalogue = tides, wind, marine, cat
import uvicorn
uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.getenv("PORT", "8088")))
