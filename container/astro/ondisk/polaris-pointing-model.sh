#!/bin/sh
# ============================================================================
# polaris-pointing-model.sh -- session-local, dry-by-default GOTO residual model
#
# This records accepted plate-solve residuals without sending a motor command.
# A future caller may ask for a bounded prediction, but applying that
# prediction remains an explicit GOTO_MODEL_APPLY=1 decision.  The model is a
# first-order tangent-plane offset only; it is not a replacement for a real
# mount model and must not survive a new calibration or camera change.
# ============================================================================
set -u

OBS=${POINTING_MODEL_OBS:-/tmp/polaris-pointing-model.tsv}
MODEL=${POINTING_MODEL_FILE:-/tmp/polaris-pointing-model.json}
MIN_SAMPLES=${POINTING_MODEL_MIN_SAMPLES:-3}
MAX_OFFSET=${POINTING_MODEL_MAX_OFFSET_DEG:-2.0}

mkdir -p "$(dirname "$OBS")" "$(dirname "$MODEL")" 2>/dev/null

numeric() {
    case "$1" in
        ''|*[!0-9.+eE-]*) return 1;;
    esac
    awk -v v="$1" 'BEGIN { exit !((v+0)==v) }' 2>/dev/null
}

rebuild() {
    _tmp="${MODEL}.tmp.$$"
    awk -F '\t' '
        function wrap(x) { while (x > 180) x-=360; while (x < -180) x+=360; return x }
        BEGIN { p=3.141592653589793/180; n=0; sx=sy=sxx=syy=0 }
        NF >= 5 {
            x=wrap($4-$2)*cos($3*p); y=$5-$3
            n++; sx+=x; sy+=y; sxx+=x*x; syy+=y*y
        }
        END {
            if (!n) exit 1
            mx=sx/n; my=sy/n
            vx=sxx/n-mx*mx; vy=syy/n-my*my
            if (vx < 0) vx=0; if (vy < 0) vy=0
            printf "{\"samples\":%d,\"mean_dra_tangent_deg\":%.9f,\"mean_ddec_deg\":%.9f,\"rms_deg\":%.9f,\"updated_epoch\":%d}\n", n, mx, my, sqrt(vx+vy), systime()
        }
    ' "$OBS" > "$_tmp" 2>/dev/null && mv "$_tmp" "$MODEL" 2>/dev/null || {
        rm -f "$_tmp" 2>/dev/null
        return 1
    }
}

case "${1:-}" in
record)
    [ "$#" -ge 5 ] || { echo "usage: $0 record target_ra target_dec solved_ra solved_dec [roll]" >&2; exit 2; }
    _tra=$2; _tdec=$3; _sra=$4; _sdec=$5; _rot=${6:-0}
    for _v in "$_tra" "$_tdec" "$_sra" "$_sdec" "$_rot"; do
        numeric "$_v" || { echo "non-numeric pointing value" >&2; exit 2; }
    done
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$(date -u +%s)" "$_tra" "$_tdec" "$_sra" "$_sdec" "$_rot" >> "$OBS" || exit 1
    rebuild || exit 1
    cat "$MODEL"
    ;;
predict)
    [ "$#" -ge 3 ] || { echo "usage: $0 predict target_ra target_dec" >&2; exit 2; }
    _ra=$2; _dec=$3
    numeric "$_ra" && numeric "$_dec" || { echo "non-numeric target" >&2; exit 2; }
    [ -r "$MODEL" ] || exit 1
    _n=$(sed -n 's/.*"samples":\([0-9][0-9]*\).*/\1/p' "$MODEL" | head -1)
    _x=$(sed -n 's/.*"mean_dra_tangent_deg":\([-+0-9.eE]*\).*/\1/p' "$MODEL" | head -1)
    _y=$(sed -n 's/.*"mean_ddec_deg":\([-+0-9.eE]*\).*/\1/p' "$MODEL" | head -1)
    [ "${_n:-0}" -ge "$MIN_SAMPLES" ] 2>/dev/null || exit 1
    [ -n "$_x" ] && [ -n "$_y" ] || exit 1
    awk -v ra="$_ra" -v dec="$_dec" -v x="$_x" -v y="$_y" -v max="$MAX_OFFSET" '
        BEGIN {
            p=3.141592653589793/180; c=cos(dec*p)
            if (c < 0) c=-c
            if (c < 0.1 || sqrt(x*x+y*y) > max) exit 1
            # solved - requested is the measured mount error.  Command the
            # opposite tangent-plane correction on the next GOTO.
            out=ra-x/c; while (out < 0) out+=360; while (out >= 360) out-=360
            outdec=dec-y
            if (outdec < -90 || outdec > 90) exit 1
            printf "%.8f %.8f\n", out, outdec
        }
    '
    ;;
status)
    [ -r "$MODEL" ] && cat "$MODEL" || printf '%s\n' '{"samples":0}'
    ;;
reset)
    rm -f "$OBS" "$MODEL" 2>/dev/null
    ;;
*)
    echo "usage: $0 record|predict|status|reset ..." >&2
    exit 2
    ;;
esac
