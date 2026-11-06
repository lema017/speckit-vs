#!/usr/bin/env bash

# Runs the script a Spec Kit command starts with, then records the step and redraws the progress
# page. A model parses that script's output, so it passes through untouched: same stdout, same
# stderr, same exit code. This wrapper adds nothing of its own, and nothing it does can fail the
# command.
#
# Usage: ./run-step.sh STEP HARNESS SCRIPT [ARG ...]

if [ "$#" -lt 3 ]; then
    echo "usage: run-step.sh STEP HARNESS SCRIPT [ARG ...]" >&2
    exit 2
fi

step="$1"
harness="$2"
script="$3"
shift 3

case "${BASH_SOURCE[0]}" in
    */*) script_dir="${BASH_SOURCE[0]%/*}" ;;
    *) script_dir="." ;;
esac

# Installed commands name SCRIPT from the project root. The event dispatcher anchors only the first
# path of a command's header, so there it still reads scripts/..., which lives under .specify. A
# scripts/ folder the project has of its own must not win over it.
if [ -f "$script_dir/../../$script" ]; then
    script="$script_dir/../../$script"
fi

"$BASH" "$script" "$@"
status=$?

if [ "$status" -eq 0 ]; then
    "$BASH" "$script_dir/progress.sh" --harness "$harness" step "$step" in_progress --quiet </dev/null >/dev/null 2>&1
fi

exit "$status"
