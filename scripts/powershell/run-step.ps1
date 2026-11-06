#!/usr/bin/env pwsh

# Runs the script a Spec Kit command starts with, then records the step and redraws the progress
# page. A model parses that script's output, so it passes through untouched: same stdout, same
# stderr, same exit code. This wrapper adds nothing of its own, and nothing it does can fail the
# command.
#
# Usage: ./run-step.ps1 STEP HARNESS SCRIPT [ARG ...]
#
# No param block on purpose: this wrapper must not claim -Json or anything else meant for the real
# script. The arguments are sorted by hand because whether $args keeps -Json as a parameter name
# depends on how PowerShell was started. In ARG, a -Name takes the next argument as its value unless
# that also starts with a dash, so a positional argument has to come before the -Names.

if ($args.Count -lt 3) {
    [Console]::Error.WriteLine('usage: run-step.ps1 STEP HARNESS SCRIPT [ARG ...]')
    exit 2
}

$stepName = [string]$args[0]
$harnessName = [string]$args[1]
$realScript = [string]$args[2]

# Installed commands name the script from the project root. The event dispatcher anchors only the
# first path of a command's header, so there it still reads scripts/..., which lives under .specify.
# A scripts/ folder the project has of its own must not win over it.
if (-not [System.IO.Path]::IsPathRooted($realScript)) {
    $anchored = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) $realScript
    if (Test-Path -LiteralPath $anchored -PathType Leaf) {
        $realScript = $anchored
    }
}

$positional = @()
$named = @{}
for ($index = 3; $index -lt $args.Count; $index++) {
    $token = [string]$args[$index]
    if ($token -notmatch '^-[A-Za-z]') {
        $positional += $token
        continue
    }
    $name = $token.Substring(1)
    $next = $index + 1
    if ($next -lt $args.Count -and [string]$args[$next] -notmatch '^-[A-Za-z]') {
        $named[$name] = [string]$args[$next]
        $index = $next
    } else {
        $named[$name] = $true
    }
}

$status = 1
try {
    & $realScript @positional @named
    $succeeded = $?
    # A script that ends without calling exit leaves $LASTEXITCODE as the last native command set
    # it, which says nothing about the script. Only a failed run reads it.
    if ($succeeded) {
        $status = 0
    } elseif ($LASTEXITCODE) {
        $status = $LASTEXITCODE
    }
} catch {
    # Without this wrapper a script that stops on an error ends the same way: message, exit 1.
    [Console]::Error.WriteLine($_.ToString())
}

if ($status -eq 0) {
    try {
        # progress.ps1 warns through [Console]::Error, which a redirection does not reach. The real
        # script has finished and this process exits next, so nothing else needs that stream.
        [Console]::SetError([System.IO.TextWriter]::Null)
        & (Join-Path $PSScriptRoot 'progress.ps1') --harness $harnessName step $stepName in_progress --quiet *> $null
    } catch {
        # The page can wait. The command's work cannot.
    }
}

exit $status
