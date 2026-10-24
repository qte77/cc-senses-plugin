#!/usr/bin/env bash
# Fail if the roadmap's "Tracked" list holds a closed issue, or its
# "Recently shipped" table references an issue/PR that is still open.
# Usage: check-roadmap-drift.sh docs/roadmap/v0.5.x.md   (needs GH_TOKEN for gh)
set -euo pipefail

roadmap="${1:?usage: $0 <roadmap.md>}"
errors=0

# Print the #NN references of one H2 section.
# mode=tracked: only bullet heads "- **#NN**" (skips upstream refs in prose)
# mode=shipped: every #NN inside table rows
refs() {
  awk -v want="$1" -v mode="$2" '
    /^## / { insec = (index($0, want) == 4); next }
    !insec { next }
    mode == "tracked" && match($0, /^- \*\*#[0-9]+\*\*/) {
      print substr($0, RSTART + 5, RLENGTH - 7); next
    }
    mode == "shipped" && /^\|/ {
      line = $0
      while (match(line, /#[0-9]+/)) {
        print substr(line, RSTART + 1, RLENGTH - 1)
        line = substr(line, RSTART + RLENGTH)
      }
    }
  ' "$roadmap" | sort -un
}

state_of() {
  gh issue view "$1" --json state --jq .state
}

for n in $(refs "Tracked in GitHub issues" tracked); do
  if [ "$(state_of "$n")" != "OPEN" ]; then
    echo "::error file=${roadmap}::#${n} is closed but still listed under 'Tracked in GitHub issues'"
    errors=$((errors + 1))
  fi
done

for n in $(refs "Recently shipped" shipped); do
  if [ "$(state_of "$n")" = "OPEN" ]; then
    echo "::error file=${roadmap}::#${n} is open but listed under 'Recently shipped'"
    errors=$((errors + 1))
  fi
done

if [ "$errors" -gt 0 ]; then
  echo "Roadmap drift: ${errors} mismatch(es). Move the entries, then re-run."
  exit 1
fi
echo "Roadmap in sync with GitHub issue states."
