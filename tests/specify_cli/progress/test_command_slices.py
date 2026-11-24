"""Command tests for ``specify progress slices``."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from specify_cli import app
from tests.conftest import strip_ansi

from .test_engine_render import HOSTILE
from .test_engine_slices import CLOSED, OPEN, RESET, SIGN_IN, SIGN_UP, SOCIAL, block, login, slice_map, spec

runner = CliRunner()


def slices(*args):
    return runner.invoke(app, ["progress", "slices", *args], env={"COLUMNS": "200"})


def row(output, slice_id):
    (line,) = [line for line in output.splitlines() if line.startswith(slice_id + " ")]
    return " ".join(line.split())


def test_it_lists_every_slice_with_its_state_and_spec(in_project):
    login(in_project)
    in_project.feature("001-sign-up", spec=spec(SIGN_UP), tasks=CLOSED)
    in_project.feature("002-sign-in", spec=spec(SIGN_IN, title="Sign in"), tasks=OPEN)
    result = slices()
    assert result.exit_code == 0, result.output
    output = strip_ansi(result.output)
    assert "login 1 of 4 slices delivered" in " ".join(output.split())
    assert "The whole login." in output
    assert row(output, SIGN_UP) == "D-login-sign-up delivered 001-sign-up Create an account"
    assert row(output, SIGN_IN) == "D-login-sign-in being built 002-sign-in Sign in with a password"
    assert row(output, RESET) == "D-login-reset no spec yet waits for D-login-sign-in Reset the password"
    assert row(output, SOCIAL) == "D-login-social no spec yet waits for D-login-sign-in Sign in with Google"
    assert "1 delivered, 1 being built, 2 no spec yet." in output.replace("\n", " ").replace("1 Delivered", "1 delivered")
    assert "No slice can start now" in output


def test_the_next_slice_and_the_ones_that_can_start_are_marked(in_project):
    slice_map(in_project, block(SIGN_UP, "Create an account"), block("D-login-help", "Read the help"), block(SIGN_IN, "Sign in", SIGN_UP))
    in_project.feature("001-sign-up", spec=spec(SIGN_UP), tasks=None)
    output = strip_ansi(slices().output)
    assert row(output, SIGN_UP) == "D-login-sign-up spec written 001-sign-up Create an account"
    assert row(output, "D-login-help") == "D-login-help next can start now Read the help"
    assert row(output, SIGN_IN) == "D-login-sign-in no spec yet waits for D-login-sign-up Sign in"
    assert "Next: /speckit-specify D-login-help" in output


def test_a_map_with_every_slice_delivered_says_so(in_project):
    slice_map(in_project, block(SIGN_UP, "Create an account"))
    in_project.feature("001-sign-up", spec=spec(SIGN_UP), tasks=CLOSED)
    output = strip_ansi(slices().output)
    assert "Every slice is delivered." in output and "Next:" not in output


def test_a_slice_added_to_the_map_shows_up_at_once(in_project):
    path = slice_map(in_project, block(SIGN_UP, "Create an account"))
    assert "D-login-reset" not in slices().output
    path.write_text(path.read_text(encoding="utf-8") + block(RESET, "Reset the password"), encoding="utf-8")
    assert "D-login-reset" in strip_ansi(slices().output)


def test_one_map_can_be_picked(in_project):
    login(in_project)
    slice_map(in_project, block("D-cart-add", "Add to the cart"), name="cart")
    output = strip_ansi(slices("--map", "cart").output)
    assert "D-cart-add" in output and SIGN_UP not in output


def test_an_unknown_map_fails(in_project):
    login(in_project)
    result = slices("--map", "nope")
    assert result.exit_code == 1
    assert "There is no slice map named nope" in strip_ansi(result.output)


def test_without_maps_it_says_how_one_is_made(in_project):
    in_project.feature("001-sign-up")
    result = slices()
    assert result.exit_code == 0
    assert "No slice maps yet." in strip_ansi(result.output)


def test_it_prints_json_for_machines(in_project):
    login(in_project)
    in_project.feature("001-sign-up", spec=spec(SIGN_UP), tasks=CLOSED)
    (group,) = json.loads(slices("--json").output)
    assert group["name"] == "login" and group["delivered"] == 1 and group["next"] == SIGN_IN
    assert [view["state"] for view in group["slices"]] == ["delivered", "pending", "pending", "pending"]


def test_hostile_text_in_a_map_reaches_the_terminal_without_control_characters(in_project):
    slice_map(in_project, block(SIGN_UP, HOSTILE), request="Request: %s\n\n" % HOSTILE)
    result = slices()
    assert result.exit_code == 0
    assert "\x1b[31m" not in result.output and " " not in result.output


def test_it_fails_outside_a_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert slices().exit_code == 1
