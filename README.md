# Factory CCTV AI Agent — Employee Idle Time (Phase 1)

On-prem computer-vision pipeline that detects employee **idle** and **away** time at factory workstations from existing CCTV feeds, then POSTs structured events to your software/ERP API.

**Phase 1 scope:** Employee idle time only.  

## Architecture overview

```
CCTV (RTSP) → Video Ingest → YOLO Person Detect + ByteTrack
    → Zone ROI Engine → Idle State Machine → Event Queue
        → ERP API Adapter (+ PostgreSQL audit store)
```

Full design: [docs/architecture.md](docs/architecture.md)

## Repository layout

| Path | Purpose |
|------|---------|
| `config/cameras.yaml` | Pilot cameras, RTSP, coverage |
| `config/zones.yaml` | Workstation ROI polygons |
| `config/idle_rules.yaml` | Thresholds, shifts, breaks, escalations |
| `config/erp_api.yaml` | Outbound API endpoint & auth |
| `config/hardware.yaml` | On-prem GPU sizing for pilot |
| `docs/` | Architecture, API contract, checklists |
| `schemas/idle_event.schema.json` | Event payload JSON Schema |
| `openapi/erp-events.yaml` | OpenAPI for outbound events |
| `recordings/` | Place pilot CCTV sample clips here |

## Quick start — cam-01 offline spike

1. Place an MP4 under `recordings/cam-01/` (see [docs/pilot-recordings.md](docs/pilot-recordings.md)).
2. Follow [docs/cam01-spike.md](docs/cam01-spike.md):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m idle_agent --source file --camera-id cam-01 --clip-start "2026-11-18T15:00:05+05:00"
```

Outputs: `output/events.jsonl`, `output/evidence/*.jpg` and `output/preview.mp4`.

Live RTSP (after NVR credentials): same CLI with `--source rtsp --url "rtsp://..."`.

## Development on a GPU instance (Vast.ai)

The GPU instance is disposable: code lives on GitHub, recordings and run outputs
live in a private B2/S3 bucket. [CLAUDE.md](CLAUDE.md) holds the project rules,
the known bugs and the commands; [docs/devlog.md](docs/devlog.md) records what
each session did and what is next.

```bash
bash scripts/vast/bootstrap.sh     # fresh instance: tools, deps, data, smoke test
pytest -q                          # CPU unit tests, no GPU or torch needed
bash scripts/vast/save_run.sh      # upload output/ to the bucket
bash scripts/vast/end_session.sh   # prints SAFE TO DESTROY when nothing would be lost
```

Configure with environment variables (see [.env.example](.env.example)):
`GH_TOKEN`, `B2_REMOTE`, `RCLONE_CONFIG_B2_*`.

## Tech stack (locked)

- Ingest: RTSP / ONVIF (OpenCV / FFmpeg)
- Detect: YOLOv8n/s + ByteTrack + YOLOv8-pose
- Host: On-prem NVIDIA GPU (or Jetson for 1–2 cams)
- Services: Python, FastAPI, Redis Streams, PostgreSQL
- Outbound: HTTPS REST with retry + idempotency keys

## Privacy

Phase 1 uses anonymous track IDs only — no face recognition.
