"""
Tests for backend/emergency_contacts_service.py.

Run: pytest tests/test_emergency_contacts.py   OR   python3 tests/test_emergency_contacts.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import emergency_contacts_service as ecs


def test_default_region_is_india_tamil_nadu_demo():
    contacts = ecs.get_contacts()
    assert contacts["region_code"] == "IN-TN"
    numbers = {c["number"] for c in contacts["general"]}
    assert "112" in numbers
    assert "108" in numbers


def test_unknown_region_falls_back_to_default_without_error():
    contacts = ecs.get_contacts("not-a-real-region")
    assert contacts["region_code"] == ecs.DEFAULT_REGION


def test_region_lookup_is_case_insensitive():
    a = ecs.get_contacts("us")
    b = ecs.get_contacts("US")
    assert a == b


def test_every_region_has_a_label():
    for code, region in ecs.REGIONS.items():
        assert region.get("label"), f"{code} missing a label"


def test_mental_health_contacts_available_for_india():
    mh = ecs.get_mental_health_contacts("IN-TN")
    assert len(mh) >= 1
    assert any("14416" in c["number"] for c in mh)


if __name__ == "__main__":
    import traceback
    tests = [(name, fn) for name, fn in list(globals().items()) if name.startswith("test_") and callable(fn)]
    passed, failed = 0, 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except Exception:
            print(f"FAIL  {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
