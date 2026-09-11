#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SUPERVISOR=$ROOT/container/ondisk/camera_usb_supervisor.sh
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
mkdir -p "$TMP/sys" "$TMP/run"

make_usb() {
    dir=$TMP/sys/$1
    mkdir -p "$dir"
    printf '%s\n' "$2" > "$dir/idVendor"
    printf '%s\n' "$3" > "$dir/idProduct"
    printf '%s\n' "$4" > "$dir/busnum"
    printf '%s\n' "$5" > "$dir/devnum"
}

RESTART_LOG=$TMP/restarts
export RESTART_LOG
cat > "$TMP/restart" <<'EOF'
#!/bin/sh
printf 'restart\n' >> "$RESTART_LOG"
EOF
chmod +x "$TMP/restart"

# Stable camera identity: no restart. An unrelated hub is ignored.
make_usb 1-1 1a40 0101 1 2
make_usb 1-2 25fb 0183 1 3
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_RESTART_GPHOTO=$TMP/restart OPENPOLARIS_USB_POLL_SECS=0.05 \
OPENPOLARIS_USB_MAX_POLLS=3 sh "$SUPERVISOR" > "$TMP/stable.out"
test ! -e "$RESTART_LOG"

# A one-poll transient is debounced; a stable device-address/body change causes
# exactly one restart, then becomes the new baseline instead of looping.
rm -rf "$TMP/run/openpolaris-camera-usb-supervisor.lock"
OPENPOLARIS_RUN_DIR=$TMP/run OPENPOLARIS_USB_SYSFS=$TMP/sys \
OPENPOLARIS_RESTART_GPHOTO=$TMP/restart OPENPOLARIS_USB_POLL_SECS=0.1 \
OPENPOLARIS_USB_MAX_POLLS=8 sh "$SUPERVISOR" > "$TMP/change.out" &
pid=$!
sleep 0.15
printf '4\n' > "$TMP/sys/1-2/devnum"
wait "$pid"
test "$(wc -l < "$RESTART_LOG")" -eq 1
grep -q 'stable identity change' "$TMP/change.out"

echo 'PASS: camera USB supervisor ignores unrelated USB and restarts once after a stable camera identity change (issue #57)'
