#!/bin/sh
set -eu

cd "$(dirname "$0")"
python3 test_analyze_pgphoto_focus_wait.py
