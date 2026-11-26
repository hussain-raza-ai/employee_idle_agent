#!/usr/bin/env bash
# Full cam-01 clip on a GPU instance, with evidence snapshots and a half-scale
# preview. Paths come from the environment; defaults suit the Vast.ai template.
#
#   bash remote_run_full_cam01.sh
#   VIDEO=/path/to/clip.mp4 CLIP_START=2026-11-18T15:00:07+05:00 bash remote_run_full_cam01.sh
#
# CLIP_START is only needed when the file name is not an NVR export; for
# NVR-7BB9_ch15_main_20261118150007_... the CLI reads 15:00:07 from the name.
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
RECORDINGS_DIR="${RECORDINGS_DIR:-$REPO_DIR/recordings}"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO_DIR/output}"
CAMERA_ID="${CAMERA_ID:-cam-01}"
DEVICE="${DEVICE:-cuda:0}"
TARGET_FPS="${TARGET_FPS:-8}"
CLIP_ARGS=()
[[ -n "${CLIP_START:-}" ]] && CLIP_ARGS=(--clip-start "$CLIP_START")

[[ -x /venv/main/bin/python ]] && export PATH="/venv/main/bin:$PATH"
cd "$REPO_DIR"

VIDEO="${VIDEO:-$(find "$RECORDINGS_DIR/$CAMERA_ID" -maxdepth 1 -type f \
  \( -name '*.mp4' -o -name '*.mkv' -o -name '*.avi' -o -name '*.mov' \) \
  2>/dev/null | sort | head -1)}"
if [[ -z "$VIDEO" || ! -f "$VIDEO" ]]; then
  echo "No video found. Put one under $RECORDINGS_DIR/$CAMERA_ID/ or set VIDEO=..." >&2
  exit 1
fi

# Clear evidence from the previous run so this run's snapshots stand alone.
# Save the previous run first if it matters: bash scripts/vast/save_run.sh
rm -rf "$OUTPUT_DIR/evidence"
mkdir -p "$OUTPUT_DIR/evidence"

echo "== video =="
ls -lah "$VIDEO"

echo "== run full clip with evidence snapshots =="
PYTHONPATH=src python -m idle_agent \
  --source file \
  --url "$VIDEO" \
  --camera-id "$CAMERA_ID" \
  --device "$DEVICE" \
  --target-fps "$TARGET_FPS" \
  --preview-scale 0.5 \
  --output-dir "$OUTPUT_DIR" \
  "${CLIP_ARGS[@]}"

echo "== results =="
ls -lah "$OUTPUT_DIR/"
ls -lah "$OUTPUT_DIR/evidence/" | head -40
wc -l "$OUTPUT_DIR/events.jsonl" || true
head -n 5 "$OUTPUT_DIR/events.jsonl" || true
echo "Save this run: bash scripts/vast/save_run.sh"
