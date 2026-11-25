#!/usr/bin/env bash
# Prepare a fresh Vast.ai instance for work on this repo.
# Idempotent: safe to run again on an instance that is already set up.
#
#   bash scripts/vast/bootstrap.sh
#
# Expects these as Vast account-level environment variables (see .env.example):
#   GH_TOKEN, RCLONE_CONFIG_B2_TYPE, RCLONE_CONFIG_B2_ACCOUNT, RCLONE_CONFIG_B2_KEY
set -uo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
B2_REMOTE="${B2_REMOTE:-b2:cctv-idle-data}"
RECORDINGS_DIR="${RECORDINGS_DIR:-$REPO_DIR/recordings}"

cd "$REPO_DIR" || exit 1

step() { printf '\n=== %s\n' "$1"; }
warn() { printf '  !! %s\n' "$1"; }
ok()   { printf '  ok %s\n' "$1"; }

step "Repo: $REPO_DIR"
git rev-parse --short HEAD 2>/dev/null || warn "not a git checkout"

step "System packages"
if ! command -v tmux >/dev/null || ! command -v rclone >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq tmux rclone curl ca-certificates git less >/dev/null
fi
for c in tmux rclone git curl; do
  command -v "$c" >/dev/null && ok "$c" || warn "$c missing"
done

step "GitHub CLI"
if ! command -v gh >/dev/null; then
  # Official apt repo; falls back to a warning rather than failing the run.
  (curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg 2>/dev/null \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update -qq && apt-get install -y -qq gh >/dev/null) \
    || warn "gh install failed — use plain git push and open the PR in the browser"
fi

step "Git / GitHub auth"
if [[ -n "${GH_TOKEN:-}" ]]; then
  git config --global --add safe.directory "$REPO_DIR"
  git config --global credential.helper store
  printf 'https://x-access-token:%s@github.com\n' "$GH_TOKEN" > ~/.git-credentials
  chmod 600 ~/.git-credentials
  git config --global user.name  "${GIT_USER_NAME:-hussain-raza-ai}"
  git config --global user.email "${GIT_USER_EMAIL:-hussain-raza-ai@users.noreply.github.com}"
  ok "git can push with GH_TOKEN"
else
  warn "GH_TOKEN not set — set it in the Vast account environment variables"
fi

step "Python dependencies"
# The Vast PyTorch template ships a venv at /venv/main with CUDA torch already in it.
if [[ -x /venv/main/bin/python ]]; then
  export PATH="/venv/main/bin:$PATH"
  ok "using /venv/main (template venv, CUDA torch preinstalled)"
fi
python -m pip install -q --upgrade pip
# torch is intentionally skipped here: the template already has the CUDA build,
# and reinstalling from requirements.txt can replace it with a CPU wheel.
python -m pip install -q "ultralytics>=8.3.0" "opencv-python-headless>=4.8.0" \
  "numpy>=1.24.0" "PyYAML>=6.0"
[[ -f requirements-dev.txt ]] && python -m pip install -q -r requirements-dev.txt
python - <<'PY'
import importlib
for m in ("torch", "ultralytics", "cv2", "yaml", "numpy"):
    try:
        importlib.import_module(m)
        print(f"  ok {m}")
    except Exception as exc:
        print(f"  !! {m}: {exc}")
PY

step "GPU"
if command -v nvidia-smi >/dev/null; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
  python -c "import torch; print('  torch.cuda.is_available():', torch.cuda.is_available())"
else
  warn "nvidia-smi not found — this instance has no GPU; use --device cpu"
fi

step "Claude Code"
if ! command -v claude >/dev/null; then
  curl -fsSL https://claude.ai/install.sh | bash || warn "Claude Code install failed"
  export PATH="$HOME/.local/bin:$PATH"
  grep -q '.local/bin' ~/.bashrc 2>/dev/null \
    || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi
command -v claude >/dev/null && ok "claude installed — run 'claude' then /login" \
                             || warn "claude not on PATH"

step "Recordings from $B2_REMOTE"
mkdir -p "$RECORDINGS_DIR"
if [[ -z "${RCLONE_CONFIG_B2_ACCOUNT:-}" ]]; then
  warn "RCLONE_CONFIG_B2_* not set — skipping data pull; copy a video in manually"
elif rclone lsd "$B2_REMOTE" >/dev/null 2>&1; then
  rclone copy "$B2_REMOTE/recordings" "$RECORDINGS_DIR" --progress --transfers 8
  find "$RECORDINGS_DIR" -type f \( -name '*.mp4' -o -name '*.mkv' -o -name '*.avi' \) \
    -printf '  %s bytes  %p\n' | head -20
else
  warn "cannot reach $B2_REMOTE — check the key and the bucket name"
fi

step "Smoke test (CPU, 120 frames)"
if find "$RECORDINGS_DIR" -type f -name '*.mp4' | grep -q .; then
  PYTHONPATH=src timeout 600 python -m idle_agent --source file --device cpu \
    --max-frames 120 --target-fps 4 --no-preview 2>&1 | tail -8
else
  warn "no video under $RECORDINGS_DIR — smoke test skipped"
fi

cat <<'EOF'

=== Ready. Next:
  tmux new -A -s main
  claude            # then /login on first use
  cat docs/devlog.md
EOF
