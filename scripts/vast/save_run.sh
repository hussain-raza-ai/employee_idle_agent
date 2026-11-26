#!/usr/bin/env bash
# Upload the current output/ to the bucket under runs/<timestamp>_<git-sha>/ so
# the result is tied to the exact code that produced it.
#
#   bash scripts/vast/save_run.sh                 # auto-named
#   bash scripts/vast/save_run.sh phone-live-1    # with a label
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
# shellcheck source=scripts/vast/load_env.sh
. "$REPO_DIR/scripts/vast/load_env.sh"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO_DIR/output}"
B2_REMOTE="${B2_REMOTE:-b2:cctv-idle-data}"
LABEL="${1:-}"

cd "$REPO_DIR"

if ! command -v rclone >/dev/null; then
  echo "rclone not installed — run bash scripts/vast/bootstrap.sh first." >&2
  exit 1
fi

if [[ ! -d "$OUTPUT_DIR" ]] || [[ -z "$(ls -A "$OUTPUT_DIR" 2>/dev/null)" ]]; then
  echo "Nothing to save: $OUTPUT_DIR is empty." >&2
  exit 1
fi

SHA="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
DIRTY=""
git diff --quiet 2>/dev/null || DIRTY="-dirty"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="${STAMP}_${SHA}${DIRTY}${LABEL:+_$LABEL}"
DEST="$B2_REMOTE/runs/$NAME"

# A small manifest makes a run readable months later without guesswork.
{
  echo "run:        $NAME"
  echo "saved_utc:  $(date -u --iso-8601=seconds)"
  echo "git_sha:    $(git rev-parse HEAD 2>/dev/null || echo nogit)"
  echo "git_branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo nogit)"
  echo "dirty:      $([[ -n "$DIRTY" ]] && echo yes || echo no)"
  echo "host:       ${VAST_CONTAINERLABEL:-$(hostname)}"
  echo "gpu:        $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo none)"
  echo
  echo "event counts by type:"
  if [[ -f "$OUTPUT_DIR/events.jsonl" ]]; then
    python - "$OUTPUT_DIR/events.jsonl" <<'PY'
import collections, json, sys
counts = collections.Counter()
first = last = None
with open(sys.argv[1], encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        ev = json.loads(line)
        counts[ev.get("event_type", "?")] += 1
        first = first or ev
        last = ev
for name, n in sorted(counts.items()):
    print(f"  {name:24s} {n}")
print(f"  {'TOTAL':24s} {sum(counts.values())}")
if first:
    print(f"\nfirst: {first.get('event_type')} at {first.get('started_at')}")
    print(f"last:  {last.get('event_type')} at {last.get('started_at')}")
PY
  else
    echo "  (no events.jsonl)"
  fi
} > "$OUTPUT_DIR/run_manifest.txt"

cat "$OUTPUT_DIR/run_manifest.txt"

echo
echo "Uploading to $DEST ..."
rclone copy "$OUTPUT_DIR" "$DEST" --progress --transfers 8
echo "Saved: $DEST"
