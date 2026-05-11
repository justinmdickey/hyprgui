"""Live end-to-end sweep of every registry setting against a running Hyprland.

For each ``SettingDef``:
1. Read its current value via ``hyprctl getoption`` and our parser.
2. Pick a *different* but valid candidate value (in-range, in-enum, etc).
3. Apply it via ``apply_setting`` (which uses ``hyprctl eval 'hl.config{}'`` in Lua mode).
4. Re-read and compare. PASS iff Hyprland actually changed to the candidate value
   (type-aware comparison).
5. Restore the original — always, even on failure or Ctrl-C.

What this exercises that the offline tests don't:
- The exact ``hl.config(...)`` snippet our generator emits is something
  Hyprland's Lua parser accepts (``ok``, not silently swallowed).
- The dotted path resolves to a real config key (catches schema drift like the
  pre-fix ``misc:vfr`` → ``debug:vfr`` rename).
- ``getoption`` returns a shape our reader handles for every type, including
  any keys that newly emit ``"gradient"`` / new fields in 0.55+.
- The numeric-vs-quoted ENUM choice matches what Hyprland expects per key.

Requires:
- Hyprland 0.55+ running.
- Lua mode (``~/.config/hypr/hyprland.lua`` present). Refuses to run otherwise
  to keep legacy-mode users safe.

Usage:
    python tests/sweep_live_registry.py            # run the full sweep
    python tests/sweep_live_registry.py --dry-run  # print plan, no writes

Originals are dumped to ``/tmp/hyprgui-sweep-<pid>.json`` before the first write
so you can restore manually if the script dies in a way the ``finally`` block
can't catch (kill -9, power loss, etc.).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hyprgui import hyprctl, lua_format  # noqa: E402
from hyprgui.config_mode import ConfigMode, detect_mode  # noqa: E402
from hyprgui.settings_registry import SETTINGS, SettingDef, SettingType  # noqa: E402

# Settings the sweep cannot meaningfully exercise.
# (We don't have any *content* skips yet — all 66 entries are sweepable —
# but keep this here so we have a place to park edge cases if the sweep
# surfaces any.)
SKIP_KEYS: set[str] = set()


# ---------------------------------------------------------------------------
# value pickers
# ---------------------------------------------------------------------------

def pick_candidate(sdef: SettingDef, original: object) -> object | None:
    """Pick a value distinct from ``original`` and valid for this setting.

    Returns ``None`` if we can't pick anything different (e.g. an ENUM with
    one option, or a numeric range with no room).
    """
    st = sdef.setting_type
    if st == SettingType.BOOL:
        return not bool(original)

    if st == SettingType.INT:
        base = int(original) if isinstance(original, (int, float)) else int(sdef.default or 0)
        step = max(1, int(sdef.step or 1))
        cand = base + step
        if cand > int(sdef.max_val):
            cand = base - step
        if cand < int(sdef.min_val):
            return None  # range too tight
        if cand == base:
            return None
        return cand

    if st == SettingType.FLOAT:
        base = float(original) if isinstance(original, (int, float)) else float(sdef.default or 0.0)
        step = float(sdef.step or 0.1)
        cand = round(base + step, 4)
        if cand > sdef.max_val:
            cand = round(base - step, 4)
        if cand < sdef.min_val:
            return None
        if abs(cand - base) < 1e-9:
            return None
        return cand

    if st == SettingType.ENUM:
        opts = list(sdef.enum_options)
        if len(opts) <= 1:
            return None
        cur = str(original)
        for o in opts:
            if o != cur:
                return o
        return None

    if st == SettingType.STRING:
        cur = str(original or "")
        # Pick something deterministic; for kb_layout etc. ``us``/``gb`` are
        # both reliably present in libxkbcommon.
        if sdef.key == "input:kb_layout":
            return "gb" if cur != "gb" else "us"
        if sdef.key == "misc:font_family":
            return "Monospace" if cur != "Monospace" else "Sans"
        # Generic: append a sentinel.
        return f"{cur}-sweep" if not cur.endswith("-sweep") else cur[:-len("-sweep")]

    if st == SettingType.COLOR:
        cur = str(original or sdef.default or "ffffffff").lower()
        # Flip the alpha byte: ...ff <-> ...80. Keeps rrggbb the same so the
        # visible disturbance is minimal (mostly transparency).
        if len(cur) == 8:
            new_alpha = "80" if cur.endswith("ff") else "ff"
            return cur[:6] + new_alpha
        return "33ccffee" if cur != "33ccffee" else "ff8800ff"

    return None


# ---------------------------------------------------------------------------
# equivalence
# ---------------------------------------------------------------------------

def values_equivalent(sdef: SettingDef, wrote: object, read: object) -> bool:
    st = sdef.setting_type
    if st == SettingType.BOOL:
        return bool(wrote) == bool(read)
    if st == SettingType.INT:
        try:
            return int(wrote) == int(read)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
    if st == SettingType.FLOAT:
        try:
            tol = max(float(sdef.step or 0.01) / 2, 1e-3)
            return abs(float(wrote) - float(read)) < tol  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
    if st == SettingType.COLOR:
        return str(wrote).lower() == str(read).lower()
    # STRING, ENUM
    return str(wrote) == str(read)


# ---------------------------------------------------------------------------
# main loop
# ---------------------------------------------------------------------------

@dataclass
class Result:
    sdef: SettingDef
    original: object
    candidate: object | None
    readback: object
    status: str  # "pass" | "fail-apply" | "fail-mismatch" | "skip-no-candidate" | "skip-config" | "fail-readnone"
    detail: str = ""


def _short_repr(v: object) -> str:
    s = repr(v)
    return s if len(s) <= 32 else s[:29] + "..."


def sweep(dry_run: bool = False) -> int:
    if detect_mode() is not ConfigMode.LUA:
        print("ERROR: this sweep is for Lua mode (Hyprland 0.55+ with hyprland.lua).")
        print("       Detected legacy hyprlang mode; refusing to run.")
        return 2

    # Capture every original up front so we have a backup file before any writes.
    originals: dict[str, object] = {}
    raw_data: dict[str, object] = {}
    for sdef in SETTINGS:
        if sdef.key in SKIP_KEYS:
            continue
        data = hyprctl.getoption(sdef.key)
        if data is None:
            originals[sdef.key] = None
            raw_data[sdef.key] = None
            continue
        originals[sdef.key] = hyprctl.parse_option_value(sdef, data)
        raw_data[sdef.key] = data

    backup_path = Path(f"/tmp/hyprgui-sweep-{os.getpid()}.json")
    if not dry_run:
        backup = {k: {"value": v, "raw": raw_data.get(k)} for k, v in originals.items()}
        backup_path.write_text(json.dumps(backup, indent=2, default=str))
        print(f"Backup of originals written to {backup_path}\n")

    results: list[Result] = []
    total = len([s for s in SETTINGS if s.key not in SKIP_KEYS])

    try:
        for i, sdef in enumerate(SETTINGS, 1):
            if sdef.key in SKIP_KEYS:
                continue
            original = originals[sdef.key]
            raw = raw_data[sdef.key]
            if raw is None:
                print(f"[{i:2d}/{total}] {sdef.key:42s}  {sdef.setting_type.name:6s} "
                      f"-- getoption returned None (no such option?)")
                results.append(Result(sdef, original, None, None, "fail-readnone",
                                      "getoption returned None"))
                continue

            cand = pick_candidate(sdef, original)
            if cand is None:
                print(f"[{i:2d}/{total}] {sdef.key:42s}  {sdef.setting_type.name:6s} "
                      f"  {_short_repr(original)}  → (no distinct candidate, skip)")
                results.append(Result(sdef, original, None, original, "skip-no-candidate"))
                continue

            snippet = lua_format.eval_snippet_for(sdef, cand)

            if dry_run:
                print(f"[{i:2d}/{total}] {sdef.key:42s}  {sdef.setting_type.name:6s} "
                      f"  {_short_repr(original)} → {_short_repr(cand)}")
                print(f"             snippet: {snippet}")
                continue

            applied = hyprctl.apply_setting(sdef, cand)
            if not applied:
                print(f"[{i:2d}/{total}] {sdef.key:42s}  {sdef.setting_type.name:6s} "
                      f"  {_short_repr(original)} → {_short_repr(cand)}  ✗ apply failed")
                results.append(Result(sdef, original, cand, None, "fail-apply",
                                      f"eval snippet: {snippet}"))
                continue

            # Tiny delay so Hyprland has propagated the change before we read.
            time.sleep(0.01)
            new_data = hyprctl.getoption(sdef.key)
            readback = hyprctl.parse_option_value(sdef, new_data) if new_data is not None else None

            if readback is None:
                print(f"[{i:2d}/{total}] {sdef.key:42s}  {sdef.setting_type.name:6s} "
                      f"  {_short_repr(original)} → {_short_repr(cand)}  ✗ read returned None")
                results.append(Result(sdef, original, cand, None, "fail-readnone",
                                      "getoption after apply returned None"))
            elif values_equivalent(sdef, cand, readback):
                print(f"[{i:2d}/{total}] {sdef.key:42s}  {sdef.setting_type.name:6s} "
                      f"  {_short_repr(original)} → {_short_repr(cand)}  ✓")
                results.append(Result(sdef, original, cand, readback, "pass"))
            else:
                print(f"[{i:2d}/{total}] {sdef.key:42s}  {sdef.setting_type.name:6s} "
                      f"  {_short_repr(original)} → {_short_repr(cand)}  ✗ readback={_short_repr(readback)}")
                results.append(Result(sdef, original, cand, readback, "fail-mismatch",
                                      f"wrote={cand!r} read={readback!r} raw={new_data!r}"))

    finally:
        # Restore every original we wrote, even on Ctrl-C.
        if not dry_run:
            print("\nRestoring originals...")
            restored = 0
            failed = []
            for r in results:
                if r.status == "pass" or r.status == "fail-mismatch":
                    if r.original is None:
                        continue
                    ok = hyprctl.apply_setting(r.sdef, r.original)
                    if ok:
                        restored += 1
                    else:
                        failed.append(r.sdef.key)
            print(f"Restored {restored} settings.")
            if failed:
                print(f"WARN: failed to restore {len(failed)}: {failed}")
                print(f"      Manual restore from {backup_path}")
            else:
                # Successful run with everything restored — remove backup.
                try:
                    backup_path.unlink()
                except OSError:
                    pass

    if dry_run:
        return 0

    # Summary
    by_status: dict[str, list[Result]] = {}
    for r in results:
        by_status.setdefault(r.status, []).append(r)
    print("\n" + "=" * 72)
    print(f"SUMMARY  {len(by_status.get('pass', []))} pass · "
          f"{len(by_status.get('fail-apply', [])) + len(by_status.get('fail-mismatch', [])) + len(by_status.get('fail-readnone', []))} fail · "
          f"{len(by_status.get('skip-no-candidate', []))} skip")
    print("=" * 72)
    for status in ("fail-apply", "fail-mismatch", "fail-readnone"):
        for r in by_status.get(status, []):
            print(f"  {status:16s} {r.sdef.key:42s}  {r.detail}")
    for r in by_status.get("skip-no-candidate", []):
        print(f"  skip             {r.sdef.key:42s}  (no distinct candidate)")

    return 0 if not any(r.status.startswith("fail") for r in results) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the apply plan, don't write anything.")
    args = ap.parse_args()
    raise SystemExit(sweep(dry_run=args.dry_run))
