#!/usr/bin/env bash

# Runs the progress engine with whichever Python is here. The engine is one file, the same on every
# platform. Without a Python the command that called this still goes on: this warns and exits 0.
# Only a task command exits 1 then, because the model has to mark that task's box by hand.
#
# Usage: ./progress.sh [--harness NAME] COMMAND [OPTIONS]
#
# COMMANDS:
#   show [--open] [--design]   Draw the page and report in full; --open also opens it
#   step NAME STATUS           Record a step, draw the page and report
#   design NAME STATUS [--area AREA] [--note TEXT]
#                              Record a step of the design, draw its page and report
#   render                     Draw the pages
#   status                     Read the progress, as JSON
#   browser on|off             Open pages by themselves, or not
#   start T011                 Say a task has started
#   done T011 [--note TEXT] [--files A,B] [--then T012]
#                              Check a task's box and record it
#   block|fail|skip T011 --reason TEXT
#                              Say what stopped a task
#   note T011 TEXT             Add a note to a task

# Shell built-ins only up to here: this must still warn when PATH holds nothing useful.
# The event dispatcher on Windows hands Git Bash this path with backslashes.
source_path="${BASH_SOURCE[0]//\\//}"
case "$source_path" in
    */*) script_dir="${source_path%/*}" ;;
    *) script_dir="." ;;
esac
script_dir="$(CDPATH='' cd -- "$script_dir" && pwd)"
project_root="$(CDPATH='' cd -- "$script_dir/../../.." && pwd)"
engine="$script_dir/../progress/engine.py"

if [ "${1:-}" = "--harness" ]; then subcommand="${3:-}"; else subcommand="${1:-}"; fi
case "$subcommand" in
    start|done|block|fail|skip|note) without_engine=1 ;;
    *) without_engine=0 ;;
esac

if [ ! -f "$engine" ]; then
    echo "progress: the page was not updated: $engine is missing. Run: specify integration upgrade" >&2
    exit "$without_engine"
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
exit "$without_engine"
