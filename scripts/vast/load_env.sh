# Load this project's secrets into the current shell. Source it, do not run it:
#
#   . scripts/vast/load_env.sh
#
# The secrets live in ~/.cctv.env on the instance, copied from the Windows PC at
# the start of each session:
#
#   scp "$HOME\vast-secrets\cctv.env" vast:/root/.cctv.env
#
# One KEY=VALUE per line (an "export " prefix is allowed):
#   GH_TOKEN, RCLONE_CONFIG_B2_TYPE, RCLONE_CONFIG_B2_ACCOUNT,
#   RCLONE_CONFIG_B2_KEY, B2_REMOTE
#
# Why a file and not Vast account env vars: a team "member" cannot edit the
# team's env vars, and team env vars would reach every member's instances.
#
# A file saved in Windows Notepad has CRLF line endings and may start with a
# UTF-8 BOM. Either would end up inside the token and break authentication, so
# both are stripped into a clean copy, ~/.cctv.env.sh, which is what gets loaded.

_cctv_src="${CCTV_ENV_FILE:-$HOME/.cctv.env}"
_cctv_out="$HOME/.cctv.env.sh"
if [ -f "$_cctv_src" ]; then
  (umask 077
   # The `|| true` keeps a caller running under `set -e -o pipefail` alive
   # when the file holds no KEY=VALUE lines at all.
   sed -e '1s/^\xEF\xBB\xBF//' -e 's/\r$//' "$_cctv_src" \
     | { grep -E '^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*=' || true; } \
     | sed -E 's/^[[:space:]]*(export[[:space:]]+)?/export /' > "$_cctv_out")
  # shellcheck disable=SC1090
  . "$_cctv_out"
fi
unset _cctv_src _cctv_out
