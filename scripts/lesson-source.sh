#!/usr/bin/env bash
# Prints the directory to run a lesson from: the code of the release the lesson
# is pinned to (third column of lessons.conf, lesson-<id> by default), unpacked
# into .lesson/<id>. Falls back to the current code when that release is not
# available locally, e.g. a copy downloaded without git history.

set -eu
cd "$(dirname "$0")/.."

lesson="$1"
ref=$(awk -v id="$lesson" '!/^[[:space:]]*#/ && $1 == id {print $3; exit}' lessons.conf)
ref="${ref:-lesson-$lesson}"

if ! git rev-parse -q --verify "refs/tags/$ref^{commit}" >/dev/null 2>&1; then
  echo "Release $ref is not available locally, running the current code. 'git pull' fetches it." >&2
  echo "."
  exit 0
fi

echo "Running the code of release $ref." >&2
dir=".lesson/$lesson"
rm -rf "$dir"
mkdir -p "$dir"
git archive "$ref" | tar -x -C "$dir"
cp .env "$dir/.env"
echo "$dir"
