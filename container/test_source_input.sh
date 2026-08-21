#!/bin/bash
# Exercise local-source provenance and archive safety without a firmware image.
set -euo pipefail

IMAGE="${1:-polaris-patcher}"
SOURCE="${2:-}"
[ -n "$SOURCE" ] && [ -f "$SOURCE/configure.ac" ] || {
  echo "usage: $0 DOCKER_IMAGE CLEAN_LIBGPHOTO2_GIT_CHECKOUT" >&2; exit 2;
}

T="$(mktemp -d)"
trap 'find "$T" -depth -mindepth 1 -delete; rmdir "$T"' EXIT

run_preflight() {
  local input="$1" output="$2" allow_dirty="${3:-0}"
  mkdir -p "$output"
  docker run --rm --entrypoint /opt/patcher/build_ptp2.sh \
    -e SOURCE_PREFLIGHT_ONLY=1 -e ALLOW_DIRTY_SOURCE="$allow_dirty" \
    -v "$input:/libgphoto2-source-input:ro" -v "$output:/work/out" \
    "$IMAGE" 2.5.34 0 0
}

run_preflight "$SOURCE" "$T/clean" >/dev/null 2>&1
test "$(sed -n 's/^git_commit=//p' "$T/clean/source-provenance.env")" = \
  "$(git -C "$SOURCE" rev-parse HEAD)"
test -z "$(sed -n 's/^dirty_diff_hash=//p' "$T/clean/source-provenance.env")"

git clone -q --no-hardlinks "$SOURCE" "$T/dirty"
printf 'dirty fixture\n' > "$T/dirty/provenance-fixture.txt"
if run_preflight "$T/dirty" "$T/rejected" 0 >"$T/rejected.log" 2>&1; then
  echo "dirty checkout was not rejected" >&2; exit 1
fi
grep -q 'local source is dirty' "$T/rejected.log"
run_preflight "$T/dirty" "$T/allowed1" 1 >/dev/null 2>&1
run_preflight "$T/dirty" "$T/allowed2" 1 >/dev/null 2>&1
H1="$(sed -n 's/^dirty_diff_hash=//p' "$T/allowed1/source-provenance.env")"
H2="$(sed -n 's/^dirty_diff_hash=//p' "$T/allowed2/source-provenance.env")"
test -n "$H1" && test "$H1" = "$H2"

git -C "$SOURCE" archive --format=tar.gz --prefix=libgphoto2-2.5.34.1/ \
  HEAD -o "$T/source.tar.gz"
run_preflight "$T/source.tar.gz" "$T/archive" >/dev/null 2>&1
test "$(sed -n 's/^source_kind=//p' "$T/archive/source-provenance.env")" = archive
test -n "$(sed -n 's/^input_sha256=//p' "$T/archive/source-provenance.env")"

mkdir "$T/unsafe-source"
printf 'unsafe fixture\n' > "$T/unsafe-source/file"
tar -czf "$T/unsafe.tar.gz" --transform='s,^,../,' -C "$T/unsafe-source" file
if run_preflight "$T/unsafe.tar.gz" "$T/unsafe-output" 0 >"$T/unsafe.log" 2>&1; then
  echo "unsafe archive was not rejected" >&2; exit 1
fi
grep -q 'unsafe source archive member' "$T/unsafe.log"

echo "source-input preflight tests: PASS"
