"""Offline sanity check for the live-sweep value picker / equivalence logic.

Runs through every registry SettingDef, asks pick_candidate() for a value,
asserts the value is distinct, in-range / in-enum / well-typed, and that
the values_equivalent() comparison treats the candidate as a match for itself.
Catches picker bugs before they cost a live run.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hyprgui.settings_registry import SETTINGS, SettingType  # noqa: E402
from tests.sweep_live_registry import (  # noqa: E402
    SKIP_KEYS,
    pick_candidate,
    values_equivalent,
)


def test_picker_produces_valid_distinct_candidates():
    failures = []
    no_candidate = []
    for sdef in SETTINGS:
        if sdef.key in SKIP_KEYS:
            continue
        # Use the registry default as the "original".
        original = sdef.default
        cand = pick_candidate(sdef, original)
        if cand is None:
            no_candidate.append(sdef.key)
            continue
        # Must be distinct.
        if cand == original:
            failures.append(f"{sdef.key}: candidate equals original ({cand!r})")
            continue
        # Must be in range / valid for the type.
        st = sdef.setting_type
        if st == SettingType.INT:
            if not (int(sdef.min_val) <= int(cand) <= int(sdef.max_val)):  # type: ignore[arg-type]
                failures.append(f"{sdef.key}: INT candidate {cand} out of [{sdef.min_val}, {sdef.max_val}]")
        elif st == SettingType.FLOAT:
            if not (sdef.min_val <= float(cand) <= sdef.max_val):  # type: ignore[arg-type]
                failures.append(f"{sdef.key}: FLOAT candidate {cand} out of [{sdef.min_val}, {sdef.max_val}]")
        elif st == SettingType.ENUM and sdef.enum_options:
            if cand not in sdef.enum_options:
                failures.append(f"{sdef.key}: ENUM candidate {cand!r} not in {sdef.enum_options}")
        elif st == SettingType.COLOR:
            if not (isinstance(cand, str) and len(cand) == 8):
                failures.append(f"{sdef.key}: COLOR candidate is not 8-hex-digit RRGGBBAA: {cand!r}")
        # Equivalence is reflexive.
        if not values_equivalent(sdef, cand, cand):
            failures.append(f"{sdef.key}: values_equivalent({cand!r}, {cand!r}) is False")

    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  {f}")
    assert not failures, f"{len(failures)} picker problems"
    print(f"OK — picker produced valid distinct candidates for "
          f"{len(SETTINGS) - len(no_candidate)} settings; "
          f"{len(no_candidate)} had no valid distinct candidate "
          f"(usually FLOAT/INT with no room around default)")


def test_equivalence_float_tolerance():
    # FLOAT compares with tolerance = step/2.
    from hyprgui.settings_registry import SettingDef
    s = SettingDef(key="x", label="x", setting_type=SettingType.FLOAT,
                   page="p", group="g", min_val=0.0, max_val=1.0, step=0.05)
    assert values_equivalent(s, 0.55, 0.5501)
    assert values_equivalent(s, 0.55, 0.55 + 0.024)
    assert not values_equivalent(s, 0.55, 0.6)


def test_equivalence_color_case_insensitive():
    from hyprgui.settings_registry import SettingDef
    s = SettingDef(key="x", label="x", setting_type=SettingType.COLOR, page="p", group="g")
    assert values_equivalent(s, "AABBCCDD", "aabbccdd")


def _run_all() -> int:
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {name}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
