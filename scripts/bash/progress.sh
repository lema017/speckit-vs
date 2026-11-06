#!/usr/bin/env bash

# Runs the progress engine with whichever Python is here. The engine is one file, the same on every
# platform. Without a Python the command that called this still goes on: this warns and exits 0.
#
# Usage: ./progress.sh [--harness NAME] COMMAND [OPTIONS]
#
# COMMANDS:
#   show                       Draw the page and report in full
#   step NAME STATUS           Record a step, draw the page and report
#   render                     Draw the pages
#   status                     Read the progress, as JSON
#   browser on|off             Open pages by themselves, or not

# Shell built-ins only up to here: this must still warn when PATH holds nothing useful.
case "${BASH_SOURCE[0]}" in
    */*) script_dir="${BASH_SOURCE[0]%/*}" ;;
    *) script_dir="." ;;
esac
script_dir="$(CDPATH='' cd -- "$script_dir" && pwd)"
project_root="$(CDPATH='' cd -- "$script_dir/../../.." && pwd)"
engine="$script_dir/../progress/engine.py"

if [ ! -f "$engine" ]; then
    echo "progress: the page was not updated: $engine is missing. Run: specify integration upgrade" >&2
    exit 0
fi

for candidate in python3 python 'py -3'; do
    # shellcheck disable=SC2086  # 'py -3' is a command and its option.
    if $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
        # shellcheck disable=SC2086
        exec $candidate -I "$engine" --root "$project_root" "$@"
    fi
done

if command -v specify >/dev/null 2>&1; then
    exec specify progress engine --root "$project_root" "$@"
fi

echo "progress: the page was not updated: no Python 3.9 or newer and no specify command here." >&2
exit 0
