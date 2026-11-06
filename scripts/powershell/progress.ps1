#!/usr/bin/env pwsh

# Runs the progress engine with whichever Python is here. The engine is one file, the same on every
# platform. Without a Python the command that called this still goes on: this warns and exits 0.
# Only a task command exits 1 then, because the model has to mark that task's box by hand.
#
# Usage: ./progress.ps1 [--harness NAME] COMMAND [OPTIONS]
#
# COMMANDS:
#   show                       Draw the page and report in full
#   step NAME STATUS           Record a step, draw the page and report
#   render                     Draw the pages
#   status                     Read the progress, as JSON
#   browser on|off             Open pages by themselves, or not
#   start T011                 Say a task has started
#   done T011 [--note TEXT] [--files A,B] [--then T012]
#                              Check a task's box and record it
#   block|fail|skip T011 --reason TEXT
#                              Say what stopped a task
#   note T011 TEXT             Add a note to a task
#
# No param block on purpose: every argument stays in $args and reaches the engine as written.

$engine = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../progress/engine.py'))
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))

$subcommand = if ($args.Count -ge 1 -and $args[0] -eq '--harness') { $args[2] } else { $args[0] }
$withoutEngine = if (@('start', 'done', 'block', 'fail', 'skip', 'note') -contains $subcommand) { 1 } else { 0 }

if (-not (Test-Path -LiteralPath $engine -PathType Leaf)) {
    [Console]::Error.WriteLine("progress: the page was not updated: $engine is missing. Run: specify integration upgrade")
    exit $withoutEngine
}

# Before PowerShell 7.3 a double quote inside an argument does not survive the trip to a native
# command, so it has to be escaped by hand for the program on the other side.
function ConvertTo-NativeArgument {
    param([string]$Value)
    if ($PSVersionTable.PSVersion.Major -ge 7 -and ($PSNativeCommandArgumentPassing -eq 'Standard' -or $PSNativeCommandArgumentPassing -eq 'Windows')) {
        return $Value
    }
    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    if ($escaped -match '\s') {
        $escaped = $escaped -replace '(\\+)$', '$1$1'
    }
    return $escaped
}

# PowerShell reads a,b as a list before this script sees it. The engine expects the comma back.
$forwarded = @($args | ForEach-Object { ConvertTo-NativeArgument (@($_) -join ',') })
$rootArgument = ConvertTo-NativeArgument $projectRoot
$engineArgument = ConvertTo-NativeArgument $engine

foreach ($candidate in @('python3', 'python', 'py -3')) {
    $parts = @($candidate -split ' ')
    $launcher = @($parts | Select-Object -Skip 1)
    if (-not (Get-Command $parts[0] -CommandType Application -ErrorAction SilentlyContinue)) {
        continue
    }
    # On Windows, python3 and python may be the Microsoft Store stub, which exists but does not run.
    try {
        & $parts[0] @launcher -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' *> $null
    } catch {
        continue
    }
    if ($LASTEXITCODE -ne 0) {
        continue
    }
    & $parts[0] @launcher -I $engineArgument --root $rootArgument @forwarded
    exit $LASTEXITCODE
}

if (Get-Command specify -CommandType Application -ErrorAction SilentlyContinue) {
    & specify progress engine --root $rootArgument @forwarded
    exit $LASTEXITCODE
}

[Console]::Error.WriteLine('progress: the page was not updated: no Python 3.9 or newer and no specify command here.')
exit $withoutEngine
