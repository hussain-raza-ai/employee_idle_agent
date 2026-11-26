# Cam-01 offline spike

Run person detect + idle/away state machine on a local recording under `recordings/cam-01/`.

## Prerequisites

- Python 3.10+ from [python.org](https://www.python.org/downloads/) (Windows Store stub is not enough — `python --version` must print a real version)
- NVIDIA GPU + CUDA recommended (Vast.ai 8 GB VRAM is enough). CPU works but is slow.
- Sample MP4 in `recordings/cam-01/` (already gitignored)

Or one-shot on Windows after Python is installed:

```powershell
.\scripts\run_cam01.ps1
# optional: .\scripts\run_cam01.ps1 --max-frames 120 --device cpu
```

## Setup

```powershell
cd employee_idle_agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On Windows with an NVIDIA GPU, install a CUDA build of PyTorch first (pick the
command from pytorch.org), then `pip install -r requirements.txt`; otherwise
pip installs the CPU wheel.

On Vast.ai, run `bash scripts/vast/bootstrap.sh` instead. The PyTorch template
already ships CUDA torch, and the script pulls the recordings from the bucket.

## Run (full clip)

```powershell
$env:PYTHONPATH = "src"
python -m idle_agent --source file --camera-id cam-01
```

The start time comes from the NVR file name. If a clip has been renamed, pass
it explicitly, e.g. `--clip-start "2026-11-18T15:00:07+05:00"`; without either
the CLI stops rather than guess.

If multiple videos exist, pass the path explicitly:

```powershell
python -m idle_agent --source file --url "recordings/cam-01/NVR-7BB9_ch15_main_20261118150007_20261118152059.mp4"
```

## CPU smoke test (short)

```powershell
python -m idle_agent --source file --device cpu --max-frames 120 --target-fps 4
```

## Outputs

| File | Meaning |
|------|---------|
| `output/events.jsonl` | IDLE/AWAY/PHONE/INTERACTING/OFF_SEAT/NOT_WORKING `_STARTED`/`_ESCALATED`/`_ENDED` events |
| `output/evidence/*.jpg` | Annotated snapshot for each `_STARTED` and `_ESCALATED` event |
| `output/preview.mp4` | Boxes, zone polygons, state labels, `m=` motion scores |

The CLI loads `config/demo_overrides.yaml` on top of `config/idle_rules.yaml` by
default (pass `--demo-overrides ""` to disable). The demo file currently keeps
the production durations (idle 180 s, away 300 s, escalate 900 s) and only
changes the primary-track settings and `debounce_leave_seconds`, and turns off
the shift calendar. For quicker test runs, lower `idle_confirm_seconds` and
`away_confirm_seconds` there, not in `idle_rules.yaml`.

On Vast, save the run before the instance goes: `bash scripts/vast/save_run.sh`.

## Later: live RTSP

```powershell
python -m idle_agent --source rtsp --url "rtsp://USER:PASS@NVR_HOST:554/Streaming/Channels/102" --camera-id cam-01
```

Prefer a factory LAN host for RTSP. Cloud GPUs usually cannot reach private NVR IPs without VPN.
