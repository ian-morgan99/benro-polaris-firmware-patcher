#!/bin/sh
# This investigation is based on v90, whose shared Bulb cancellation path has
# a known unresolved defect. A later integration must replace this explicit
# block with a passing provenance-bound cancellation and lifecycle gate.
echo 'BLOCKED: v90 Bulb cancellation and deferred-timed safety remain unresolved (issue #251)' >&2
exit 1
