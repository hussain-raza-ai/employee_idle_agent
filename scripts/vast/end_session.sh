#!/usr/bin/env bash
# Pre-destroy check. Everything on a Vast instance disappears when it is
# destroyed, so this confirms the work is already on GitHub and in the bucket.
#
#   bash scripts/vast/end_session.sh
#
# Exits 0 and prints SAFE TO DESTROY only when every check passes.
set -uo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
# shellcheck source=scripts/vast/load_env.sh
. "$REPO_DIR/scripts/vast/load_env.sh"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO_DIR/output}"
B2_REMOTE="${B2_REMOTE:-b2:cctv-idle-data}"

cd "$REPO_DIR" || exit 1
PROBLEMS=0
note() { printf '  %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; PROBLEMS=$((PROBLEMS + 1)); }
pass() { printf '  ok    %s\n' "$1"; }

echo "=== 1. Uncommitted changes"
if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
  fail "working tree is dirty:"
  git status --short | sed 's/^/        /'
  note "commit them on a branch, or 'git stash' if they are throwaway"
else
  pass "working tree clean"
fi

echo "=== 2. Unpushed commits"
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
if [[ -z "$BRANCH" ]]; then
  fail "not a git checkout"
elif git rev-parse --abbrev-ref "@{upstream}" >/dev/null 2>&1; then
  AHEAD="$(git rev-list --count '@{upstream}..HEAD' 2>/dev/null || echo 0)"
  if [[ "$AHEAD" -gt 0 ]]; then
    fail "$AHEAD commit(s) on '$BRANCH' not pushed"
    note "git push -u origin $BRANCH"
  else
    pass "'$BRANCH' is pushed"
  fi
else
  fail "'$BRANCH' has no upstream — it exists only on this instance"
  note "git push -u origin $BRANCH"
fi

echo "=== 3. Local-only branches"
LOCAL_ONLY="$(git for-each-ref --format='%(refname:short) %(upstream)' refs/heads \
  | awk '$2 == "" {print $1}' | tr '\n' ' ')"
if [[ -n "${LOCAL_ONLY// /}" ]]; then
  fail "branches with no remote: $LOCAL_ONLY"
else
  pass "every branch has a remote"
fi

echo "=== 4. Unsaved run output"
if [[ -d "$OUTPUT_DIR" ]] && [[ -n "$(ls -A "$OUTPUT_DIR" 2>/dev/null)" ]]; then
  if [[ -f "$OUTPUT_DIR/run_manifest.txt" ]]; then
    # Output newer than the manifest means a run happened after the last save.
    NEWER="$(find "$OUTPUT_DIR" -type f -newer "$OUTPUT_DIR/run_manifest.txt" \
      ! -name run_manifest.txt | head -5)"
    if [[ -n "$NEWER" ]]; then
      fail "output/ changed since the last save_run.sh"
      note "bash scripts/vast/save_run.sh"
    else
      pass "output/ matches the last saved run"
    fi
  else
    fail "output/ has files but was never saved"
    note "bash scripts/vast/save_run.sh"
  fi
else
  pass "output/ empty — nothing to save"
fi

echo "=== 5. Devlog"
if [[ -f docs/devlog.md ]]; then
  LAST="$(git log -1 --format=%cd --date=short -- docs/devlog.md 2>/dev/null || echo '')"
  TODAY="$(date +%F)"
  if [[ "$LAST" == "$TODAY" ]]; then
    pass "docs/devlog.md updated today"
  else
    fail "docs/devlog.md last committed $LAST, not today"
    note "add what happened and what is next, then commit it"
  fi
else
  fail "docs/devlog.md missing"
fi

echo "=== 6. Bucket reachable"
if [[ -z "${RCLONE_CONFIG_B2_ACCOUNT:-}" ]]; then
  note "SKIP  RCLONE_CONFIG_B2_* not set"
elif rclone lsd "$B2_REMOTE/runs" >/dev/null 2>&1; then
  pass "$B2_REMOTE reachable; most recent runs:"
  rclone lsd "$B2_REMOTE/runs" 2>/dev/null | tail -3 | sed 's/^/        /'
else
  fail "cannot reach $B2_REMOTE"
fi

echo
if [[ "$PROBLEMS" -eq 0 ]]; then
  cat <<'EOF'
SAFE TO DESTROY.
Everything is on GitHub and in the bucket. Destroy the instance in the Vast
console to stop storage charges. Stopping instead keeps the data but keeps
billing for it, and a restart only works if that machine's GPU is free.
EOF
  exit 0
else
  echo "$PROBLEMS problem(s) — DO NOT DESTROY yet. Fix the FAIL lines above and re-run."
  exit 1
fi
