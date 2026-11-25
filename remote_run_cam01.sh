#!/usr/bin/env bash
# Short cam-01 spike on a GPU instance. Paths come from the environment so the
# script works on any instance; defaults suit the Vast.ai PyTorch template.
#
#   bash remote_run_cam01.sh                     # first video under recordings/cam-01
#   VIDEO=/path/to/clip.mp4 bash remote_run_cam01.sh
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
RECORDINGS_DIR="${RECORDINGS_DIR:-$REPO_DIR/recordings}"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO_DIR/output}"
CAMERA_ID="${CAMERA_ID:-cam-01}"
DEVICE="${DEVICE:-cuda:0}"
TARGET_FPS="${TARGET_FPS:-8}"

[[ -x /venv/main/bin/python ]] && export PATH="/venv/main/bin:$PATH"
cd "$REPO_DIR"

VIDEO="${VIDEO:-$(find "$RECORDINGS_DIR/$CAMERA_ID" -maxdepth 1 -type f \
  \( -name '*.mp4' -o -name '*.mkv' -o -name '*.avi' -o -name '*.mov' \) \
  2>/dev/null | sort | head -1)}"
if [[ -z "$VIDEO" || ! -f "$VIDEO" ]]; then
  echo "No video found. Put one under $RECORDINGS_DIR/$CAMERA_ID/ or set VIDEO=..." >&2
  echo "On Vast, bootstrap.sh pulls recordings from the bucket." >&2
  exit 1
fi

echo "== probe =="
python - "$VIDEO" <<'PY'
import sys, cv2
path = sys.argv[1]
cap = cv2.VideoCapture(path)
print("video", path)
print("open", cap.isOpened(), "frames", int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
      "fps", cap.get(cv2.CAP_PROP_FPS))
ok, frame = cap.read()
print("first_frame", ok, None if not ok else frame.shape)
cap.release()
PY

echo "== run spike =="
# Without CLIP_START the CLI reads the start from an NVR-style file name
# (…_20261118150005_….mp4), and stops with instructions if there is none.
CLIP_ARGS=()
[[ -n "${CLIP_START:-}" ]] && CLIP_ARGS=(--clip-start "$CLIP_START")
PYTHONPATH=src python -m idle_agent \
  --source file \
  --url "$VIDEO" \
  --camera-id "$CAMERA_ID" \
  --device "$DEVICE" \
  --target-fps "$TARGET_FPS" \
  --output-dir "$OUTPUT_DIR" \
  "${CLIP_ARGS[@]}"

echo "== results =="
ls -lah "$OUTPUT_DIR/"
wc -l "$OUTPUT_DIR/events.jsonl" || true
head -n 5 "$OUTPUT_DIR/events.jsonl" || true
echo "Save this run: bash scripts/vast/save_run.sh"
