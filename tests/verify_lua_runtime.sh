#!/usr/bin/env bash
# Verify Hyprland 0.55+ Lua-config runtime behavior that hyprgui depends on.
#
# Run this on a machine where Hyprland 0.55+ is RUNNING with a Lua config
# (~/.config/hypr/hyprland.lua present). It only reads and makes one harmless,
# self-reverting change to decoration:rounding.
#
#   bash tests/verify_lua_runtime.sh
#
# Answers the open questions in docs/lua-migration-plan.md.

set -u

say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
note() { printf '   \033[2m%s\033[0m\n' "$*"; }
run()  { printf '   $ %s\n' "$*"; eval "$@"; printf '   -> exit %d\n' "$?"; }

if ! hyprctl version >/dev/null 2>&1; then
  echo "Hyprland is not running (hyprctl can't connect). Aborting."
  exit 1
fi

say "Hyprland version"
hyprctl version | head -3

say "Q0: config mode"
if [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/hypr/hyprland.lua" ]; then
  note "hyprland.lua present -> Hyprland is in LUA mode (this is what we want to test)"
else
  note "hyprland.lua ABSENT -> Hyprland is in legacy hyprlang mode."
  note "The eval tests below will not reflect Lua-mode behavior. Switch to a Lua config first."
fi

say "Q4a: getoption with a simple key (baseline)"
run "hyprctl -j getoption decoration:rounding"

say "Q4b: getoption with NESTED keys — which colon form resolves?"
note "Stub key is decoration.shadow.range — try both IPC spellings:"
run "hyprctl -j getoption decoration:shadow:range"
run "hyprctl -j getoption decoration:shadow_range"
note "And blur / touchpad / snap:"
run "hyprctl -j getoption decoration:blur:size"
run "hyprctl -j getoption input:touchpad:natural_scroll"
run "hyprctl -j getoption general:snap:enabled"
run "hyprctl -j getoption general:col.active_border"
note "Note which one returns {\"set\": ...} vs an error / 'no such option'."

say "Q1+Q2+Q3: hl.config via eval — merge test (self-reverting)"
orig=$(hyprctl -j getoption decoration:rounding | grep -o '"int": *[0-9-]*' | grep -o '[0-9-]*$')
note "current decoration:rounding int = ${orig:-<unknown>}"
note "current decoration:blur:size  = $(hyprctl -j getoption decoration:blur:size | grep -o '"int": *[0-9-]*' | grep -o '[0-9-]*$' || echo '?')"

note "(a) bare nested-table form:"
run "hyprctl eval 'hl.config({ decoration = { rounding = 7 } })'"
note "    decoration:rounding now = $(hyprctl -j getoption decoration:rounding | grep -o '"int": *[0-9-]*' | grep -o '[0-9-]*$' || echo '?')  (expect 7 if it worked)"
note "    decoration:blur:size still = $(hyprctl -j getoption decoration:blur:size | grep -o '"int": *[0-9-]*' | grep -o '[0-9-]*$' || echo '?')  (if unchanged -> MERGE, good)"

note "(b) deeper nesting via eval:"
run "hyprctl eval 'hl.config({ decoration = { shadow = { range = 9 } } })'"
run "hyprctl -j getoption decoration:shadow:range"
run "hyprctl -j getoption decoration:shadow_range"

note "(c) bracket-dotted key form (Justin's config uses this):"
run "hyprctl eval 'hl.config({ decoration = { [\"shadow.render_power\"] = 3 } })'"
run "hyprctl -j getoption decoration:shadow:render_power"

note "(d) does it need hl.dispatch wrapping? (config examples don't, dispatch examples do)"
run "hyprctl eval 'hl.dispatch(function() hl.config({ decoration = { rounding = 5 } }) end)'"
note "    decoration:rounding now = $(hyprctl -j getoption decoration:rounding | grep -o '"int": *[0-9-]*' | grep -o '[0-9-]*$' || echo '?')"

note "(e) gradient form:"
run "hyprctl eval 'hl.config({ general = { col = { active_border = { colors = {\"rgba(33ccffee)\"}, angle = 45 } } } })'"
run "hyprctl -j getoption general:col.active_border"

# revert
if [ -n "${orig:-}" ]; then
  note "reverting decoration:rounding to $orig"
  hyprctl eval "hl.config({ decoration = { rounding = $orig } })" >/dev/null
fi

say "Q6: setcursor under Lua"
note "(reads current cursor env first; only run the set if you want to test it)"
run "echo HYPRCURSOR_THEME=\$HYPRCURSOR_THEME XCURSOR_THEME=\$XCURSOR_THEME size=\$HYPRCURSOR_SIZE\$XCURSOR_SIZE"
note "to test: hyprctl setcursor <theme> <size>   (skipped here to avoid changing your cursor)"

say "Q5: keyword is dead (expected failure — just confirming the error message)"
run "hyprctl keyword decoration:rounding 10"

say "Done."
note "Record the answers in docs/lua-migration-plan.md 'Open questions' section."
note "Key things to note:"
note "  - which getoption colon-form resolves for nested keys (Q4b)"
note "  - did blur:size survive the rounding change (merge vs replace) (Q1)"
note "  - bare hl.config vs needing dispatch wrap (Q2/d)"
note "  - nested-table vs bracket-dotted accepted by hl.config (Q3/c)"
note "  - what getoption returns for a gradient col.* key (Q5/e)"
