#!/usr/bin/env bash
# Prints the BUG_SCENARIO value for a lesson id from lessons.conf.

set -eu
cd "$(dirname "$0")/.."

available=$(awk '!/^[[:space:]]*(#|$)/ {printf "%s%s", sep, $1; sep=", "}' lessons.conf)
lesson="${1:-}"
if [ -z "$lesson" ]; then
  echo "Usage: make lesson <id>. Available lessons: $available" >&2
  exit 1
fi
scenarios=$(awk -v id="$lesson" '!/^[[:space:]]*#/ && $1 == id {print $2; exit}' lessons.conf)
if [ -z "$scenarios" ]; then
  echo "Unknown lesson '$lesson'. Available lessons: $available" >&2
  exit 1
fi
echo "$scenarios"
