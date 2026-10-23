#!/usr/bin/env bash
# Smoke-test the built engine binary on a CI runner: start it, then run the
# real Ollama silent installer through its HTTP routes and check Ollama runs.
# Usage: scripts/ci-windows-smoke.sh [path-to-engine-binary]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE="${1:-$(ls "$ROOT"/app/src-tauri/binaries/folio-engine-*.exe | head -n1)}"
WORK="$(mktemp -d)"
OUT="$WORK/engine.out"
ERR="$WORK/engine.err"
TOKEN="ci-smoke-$RANDOM$RANDOM"
INSTALL_TIMEOUT_S=600

dump_logs() {
  echo "---- engine stdout ----"; cat "$OUT" 2>/dev/null || true
  echo "---- engine stderr ----"; cat "$ERR" 2>/dev/null || true
}
cleanup() { [ -n "${PID:-}" ] && kill "$PID" 2>/dev/null || true; }
fail() { echo "SMOKE FAILED: $*" >&2; dump_logs; exit 1; }
trap cleanup EXIT

echo "Starting $ENGINE"
FOLIO_ENGINE_TOKEN="$TOKEN" "$ENGINE" --data-dir "$WORK/data" >"$OUT" 2>"$ERR" &
PID=$!

PORT=""
for _ in $(seq 1 60); do
  PORT="$(sed -n 's/^FOLIO_ENGINE_READY port=\([0-9]*\).*/\1/p' "$OUT" | head -n1 | tr -d '\r')"
  [ -n "$PORT" ] && break
  kill -0 "$PID" 2>/dev/null || fail "engine exited before becoming ready"
  sleep 1
done
[ -n "$PORT" ] || fail "no ready line within 60s"
BASE="http://127.0.0.1:$PORT"
AUTH="Authorization: Bearer $TOKEN"
echo "Engine ready on port $PORT"

curl -fsS -H "$AUTH" "$BASE/setup/ollama" || fail "GET /setup/ollama failed"; echo
curl -fsS -X POST -H "$AUTH" "$BASE/setup/ollama/install" || fail "POST /setup/ollama/install failed"; echo

deadline=$((SECONDS + INSTALL_TIMEOUT_S))
state=""
while [ "$SECONDS" -lt "$deadline" ]; do
  body="$(curl -fsS -H "$AUTH" "$BASE/setup/ollama/install")" || fail "polling install status failed"
  state="$(printf '%s' "$body" | sed -n 's/.*"state":"\([a-z]*\)".*/\1/p')"
  echo "install: $body"
  case "$state" in
    done) break ;;
    error) fail "installer reported an error: $body" ;;
  esac
  sleep 5
done
[ "$state" = "done" ] || fail "install did not finish within ${INSTALL_TIMEOUT_S}s"

final="$(curl -fsS -H "$AUTH" "$BASE/setup/ollama")" || fail "GET /setup/ollama failed after install"
echo "ollama: $final"
printf '%s' "$final" | grep -Eq '"running": ?true' || fail "Ollama is not running after install"
echo "SMOKE PASSED"
