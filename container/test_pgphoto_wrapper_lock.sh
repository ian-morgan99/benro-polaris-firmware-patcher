#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WRAPPER=$ROOT/container/ondisk/pgphoto.wrapper.in
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

mkdir -p "$TMP/stage2/libgphoto2/2.5.34" "$TMP/stage2/libgphoto2_port/0.12.2"
cat > "$TMP/stage2/pgphoto.stage2ondisk" <<'EOF'
#!/bin/sh
echo launched
EOF
chmod +x "$TMP/stage2/pgphoto.stage2ondisk"

run_wrapper() {
    OPENPOLARIS_RUN_DIR=$TMP/run \
    OPENPOLARIS_STAGE2_DIR=$TMP/stage2 \
    sh "$WRAPPER"
}

mkdir -p "$TMP/run/openpolaris-pgphoto.launch.lock"
echo 999999 > "$TMP/run/openpolaris-pgphoto.launch.lock/pid"
OUT=$(run_wrapper 2>&1)
printf '%s\n' "$OUT" | grep -q 'reclaiming stale pgphoto launch lock'
printf '%s\n' "$OUT" | grep -q '^launched$'
test ! -e "$TMP/run/openpolaris-pgphoto.launch.lock"

rm -f "$TMP/run/openpolaris-pgphoto.pid" "$TMP/run/openpolaris-pgphoto.backoff"
mkdir -p "$TMP/run/openpolaris-pgphoto.launch.lock"
echo $$ > "$TMP/run/openpolaris-pgphoto.launch.lock/pid"
OUT=$(run_wrapper 2>&1)
printf '%s\n' "$OUT" | grep -q "launch is already in progress (PID $$)"
test -d "$TMP/run/openpolaris-pgphoto.launch.lock"

echo 'PASS: pgphoto wrapper reclaims stale locks and preserves live-owner locks'
