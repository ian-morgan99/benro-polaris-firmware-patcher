#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/nmcli" <<'EOF'
#!/bin/sh
printf '%s\n' 'wlp-test:connected:polaris_test'
EOF
cat > "$TMP/ip" <<'EOF'
#!/bin/sh
printf '%s\n' '192.168.0.1 dev wlp-test src 192.168.0.2'
EOF
cat > "$TMP/ssh" <<'EOF'
#!/bin/sh
printf '%s\n' 'fw=FwVer:4.0.0.32 uptime=123.45 psh=7 disc=6 rx=100 tx=200 c9090=1 c8080=1'
EOF
chmod +x "$TMP/nmcli" "$TMP/ip" "$TMP/ssh"

output=$(NMCLI_BIN="$TMP/nmcli" IP_BIN="$TMP/ip" SSH_BIN="$TMP/ssh" \
    WIFI_IFACE=wlp-test "$ROOT/scripts/monitor-wifi-qualification.sh" --once)
grep -q $'timestamp\tstatus\tfirmware' <<< "$output"
grep -q $'\tUP\tFwVer:4.0.0.32\t123.45\t7\t6\t100\t200\t1\t1' <<< "$output"

cat > "$TMP/ip" <<'EOF'
#!/bin/sh
printf '%s\n' '192.168.0.1 dev eth0 src 192.168.0.3'
EOF
chmod +x "$TMP/ip"
output=$(NMCLI_BIN="$TMP/nmcli" IP_BIN="$TMP/ip" SSH_BIN="$TMP/ssh" \
    WIFI_IFACE=wlp-test "$ROOT/scripts/monitor-wifi-qualification.sh" --once)
grep -q $'\tWRONG_ROUTE_OR_AP\t' <<< "$output"
printf 'wifi qualification monitor tests: PASS\n'
