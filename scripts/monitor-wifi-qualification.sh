#!/usr/bin/env bash
# Read-only sampler for issue #68 Wi-Fi qualification. It sends no 9090/8080
# traffic and writes nothing to the Polaris; run the workload from another
# process while this records radio evidence on the host.

set -u -o pipefail

GIMBAL_HOST="${GIMBAL_HOST:-192.168.0.1}"
WIFI_IFACE="${WIFI_IFACE:-wlp8s0}"
INTERVAL_SECS="${INTERVAL_SECS:-5}"
DURATION_SECS="${DURATION_SECS:-3600}"
OUTPUT="${OUTPUT:-}"
NMCLI_BIN="${NMCLI_BIN:-nmcli}"
IP_BIN="${IP_BIN:-ip}"
SSH_BIN="${SSH_BIN:-ssh}"

usage() {
    sed -n '2,5p' "$0"
    printf 'Usage: %s [--duration SECONDS] [--interval SECONDS] [--output FILE] [--once]\n' "$0"
}

while (($#)); do
    case "$1" in
        --duration) DURATION_SECS="$2"; shift 2 ;;
        --interval) INTERVAL_SECS="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        --once) DURATION_SECS=0; shift ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
done

case "$DURATION_SECS:$INTERVAL_SECS" in
    *[!0-9:]*) printf 'duration and interval must be non-negative integers\n' >&2; exit 2 ;;
esac
if (( INTERVAL_SECS == 0 )); then
    printf 'interval must be greater than zero\n' >&2
    exit 2
fi

emit() {
    if [[ -n "$OUTPUT" ]]; then
        printf '%s\n' "$*" | tee -a "$OUTPUT"
    else
        printf '%s\n' "$*"
    fi
}

host_identity_ok() {
    local connection route_dev
    connection=$($NMCLI_BIN -t -f DEVICE,STATE,CONNECTION device status 2>/dev/null |
        awk -F: -v ifc="$WIFI_IFACE" '$1==ifc && $2=="connected" {print $3}')
    [[ "$connection" == polaris_* ]] || return 1
    route_dev=$($IP_BIN route get "$GIMBAL_HOST" 2>/dev/null |
        awk '{for (i=1; i<=NF; i++) if ($i=="dev") {print $(i+1); exit}}')
    [[ "$route_dev" == "$WIFI_IFACE" ]]
}

remote_sample() {
    $SSH_BIN -o BatchMode=yes -o ConnectTimeout=4 -o StrictHostKeyChecking=accept-new \
        "root@${GIMBAL_HOST}" 'fw=$(cat /app/FwVer 2>/dev/null | tr " \t" "__");
            [ -n "$fw" ] || exit 42;
            psh=$(dmesg 2>/dev/null | grep -c "No more free tdata_psh_info" || true);
            disc=$(dmesg 2>/dev/null | grep -c "Out of tdata_disc_grp" || true);
            set -- $(awk '\''$1 ~ /^wlan0:$/ {gsub(":", "", $1); print $2, $10}'\'' /proc/net/dev);
            c9090=$(awk '\''$2 ~ /:2382$/ && $4 == "01" {n++} END {print n+0}'\'' /proc/net/tcp);
            c8080=$(awk '\''$2 ~ /:1F90$/ && $4 == "01" {n++} END {print n+0}'\'' /proc/net/tcp);
            printf "fw=%s uptime=%s psh=%s disc=%s rx=%s tx=%s c9090=%s c8080=%s\n" \
                "$fw" "$(cut -d" " -f1 /proc/uptime)" "$psh" "$disc" "${1:-?}" "${2:-?}" "$c9090" "$c8080"'
}

start=$(date +%s)
emit $'timestamp\tstatus\tfirmware\tuptime_s\tpsh_errors\tdisc_errors\twlan_rx_bytes\twlan_tx_bytes\testablished_9090\testablished_8080'
while :; do
    now=$(date +%s)
    stamp=$(date -u +%FT%TZ)
    if ! host_identity_ok; then
        emit "$stamp"$'\tWRONG_ROUTE_OR_AP\t-\t-\t-\t-\t-\t-\t-\t-'
    elif sample=$(remote_sample 2>/dev/null); then
        declare -A value=()
        for pair in $sample; do value["${pair%%=*}"]="${pair#*=}"; done
        emit "$stamp"$'\tUP\t'"${value[fw]:-?}"$'\t'"${value[uptime]:-?}"$'\t'"${value[psh]:-?}"$'\t'"${value[disc]:-?}"$'\t'"${value[rx]:-?}"$'\t'"${value[tx]:-?}"$'\t'"${value[c9090]:-?}"$'\t'"${value[c8080]:-?}"
    else
        emit "$stamp"$'\tSSH_DOWN_OR_IDENTITY_FAILED\t-\t-\t-\t-\t-\t-\t-\t-'
    fi
    (( DURATION_SECS == 0 || now - start >= DURATION_SECS )) && break
    sleep "$INTERVAL_SECS"
done
