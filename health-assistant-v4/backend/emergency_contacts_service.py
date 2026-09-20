"""
Emergency contacts -- thin loader over emergency_contacts.json.

Kept intentionally trivial: this is configuration, not logic. Adding a new
region means editing the JSON file, not this module. See the file's `_meta`
note about keeping numbers current.
"""

import json
from pathlib import Path

CONTACTS_PATH = Path(__file__).parent / "emergency_contacts.json"

with open(CONTACTS_PATH, "r", encoding="utf-8") as f:
    _DATA = json.load(f)

DEFAULT_REGION = _DATA["default_region"]
REGIONS = _DATA["regions"]


def list_regions() -> list:
    return [{"code": code, "label": r["label"]} for code, r in REGIONS.items()]


def get_contacts(region_code: str = None) -> dict:
    """Returns the contacts block for a region, falling back to the default
    region if the code isn't recognized (never raises for an unknown code --
    an unfamiliar region string from a client shouldn't break the emergency
    page, it should just show the default/demo configuration)."""
    region_code = region_code or DEFAULT_REGION
    region = REGIONS.get(region_code.upper(), REGIONS[DEFAULT_REGION])
    return {"region_code": region_code.upper() if region_code.upper() in REGIONS else DEFAULT_REGION, **region}


def get_mental_health_contacts(region_code: str = None) -> list:
    return get_contacts(region_code).get("mental_health_crisis", [])
