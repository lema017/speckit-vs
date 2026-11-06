"""What each harness sends a hook, and what is taken from it.

Each message below follows the harness's published hook reference, read on 2026-11-06. They were not
captured from a live session, except where it says so. A harness that sends no session or no agent
leaves its report labelled as declared: the page always shows which it is.
"""

from __future__ import annotations

import json

import pytest

from .conftest import task_event

COMMAND = ".specify/scripts/bash/progress.sh --harness x done T001 --note SECRET-NOTE --then T002"
RESULT = "SECRET-OUTPUT"


def claude():
    # https://code.claude.com/docs/en/hooks: agent_id only inside a subagent.
    # These fields are the ones a live session of Claude Code 2.1.303 sent, on 2026-11-06.
    return {
        "session_id": "abc123def456",
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/project",
        "prompt_id": "prompt-1",
        "permission_mode": "acceptEdits",
        "effort": {"level": "medium"},
        "hook_event_name": "PostToolUse",
        "agent_id": "subagent-7",
        "agent_type": "general-purpose",
        "tool_name": "Bash",
        "tool_input": {"command": COMMAND},
        "tool_response": {"stdout": RESULT, "stderr": "", "interrupted": False, "isImage": False, "noOutputExpected": False},
        "tool_use_id": "toolu-1",
        "duration_ms": 12,
    }


def codex():
    # https://developers.openai.com/codex/hooks: subagents report their parent's session, no agent.
    return {
        "session_id": "abc123def456",
        "turn_id": "turn-1",
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_use_id": "call-1",
        "tool_input": {"command": COMMAND},
        "tool_response": RESULT,
    }


def copilot_camel():
    # https://docs.github.com/en/copilot/reference/hooks-configuration: camelCase, toolArgs "unknown".
    return {
        "sessionId": "abc123def456",
        "timestamp": 1704614600000,
        "cwd": "/project",
        "toolName": "bash",
        "toolArgs": json.dumps({"command": COMMAND}),
        "toolResult": {"resultType": "success", "textResultForLlm": RESULT},
    }


def copilot_vscode():
    # The same page: the VS Code compatible form of the same event.
    return {
        "hook_event_name": "PostToolUse",
        "session_id": "abc123def456",
        "timestamp": "2026-01-07T12:00:00Z",
        "cwd": "/project",
        "tool_name": "bash",
        "tool_input": {"command": COMMAND},
        "tool_result": {"result_type": "success", "text_result_for_llm": RESULT},
    }


def cursor():
    # https://cursor.com/docs/hooks: conversation_id is the stable one, tool_name is Shell.
    return {
        "conversation_id": "abc123def456",
        "generation_id": "gen-1",
        "model": "m",
        "hook_event_name": "postToolUse",
        "workspace_roots": ["/project"],
        "user_email": "SECRET-EMAIL",
        "tool_name": "Shell",
        "tool_input": {"command": COMMAND},
        "tool_output": RESULT,
        "tool_use_id": "abc",
        "cwd": "/project",
        "duration": 5,
    }


def devin():
    # https://docs.devin.ai/cli/extensibility/hooks/lifecycle-hooks: the shell tool is exec.
    return {
        "session_id": "abc123def456",
        "prompt_id": "p-1",
        "tool_name": "exec",
        "tool_input": {"command": COMMAND, "shell_id": "main"},
        "tool_response": RESULT,
    }


def gemini():
    # https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md
    return {
        "session_id": "abc123def456",
        "transcript_path": "/tmp/x.json",
        "cwd": "/project",
        "hook_event_name": "AfterTool",
        "timestamp": "2026-01-07T12:00:00Z",
        "tool_name": "run_shell_command",
        "tool_input": {"command": COMMAND},
        "tool_response": {"llmContent": RESULT},
    }


def opencode():
    # https://opencode.ai/docs/plugins/ documents output.args on tool.execute.before. Spec Kit's plugin
    # forwards both callback arguments as {input, output}. Whether args reach tool.execute.after is
    # not stated there, so this takes it from either side, and a harness that sends neither stays declared.
    return {
        "input": {"tool": "bash", "sessionID": "abc123def456", "callID": "c1", "args": {"command": COMMAND}},
        "output": {"title": "t", "output": RESULT, "metadata": {}},
    }


def qwen():
    # https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/hooks.md: agent_id inside a subagent.
    return {
        "session_id": "abc123def456",
        "transcript_path": "/tmp/x",
        "cwd": "/project",
        "hook_event_name": "PostToolUse",
        "timestamp": "2026-01-07T12:00:00Z",
        "permission_mode": "auto",
        "agent_id": "subagent-7",
        "tool_name": "run_shell_command",
        "tool_input": {"command": COMMAND},
        "tool_response": {"output": RESULT},
    }


def tabnine():
    # https://docs.tabnine.com/main/getting-started/tabnine-cli/features/hooks/event-reference
    return dict(gemini())


def vibe():
    # https://github.com/mistralai/mistral-vibe/blob/main/README.md: tool_name is the qualified name.
    return {
        "session_id": "abc123def456",
        "parent_session_id": None,
        "transcript_path": "/tmp/x",
        "cwd": "/project",
        "hook_event_name": "post_tool",
        "tool_name": "file_system.bash",
        "tool_call_id": "c1",
        "tool_input": {"command": COMMAND},
        "tool_status": "success",
        "tool_output": {"stdout": RESULT, "returncode": 0},
        "tool_output_text": RESULT,
        "tool_error": None,
        "duration_ms": 0,
    }


MESSAGES = {
    "claude": (claude, "subagent-7"),
    "codex": (codex, None),
    "copilot": (copilot_camel, None),
    "copilot-vscode": (copilot_vscode, None),
    "cursor-agent": (cursor, None),
    "devin": (devin, None),
    "gemini": (gemini, None),
    "opencode": (opencode, None),
    "qwen": (qwen, "subagent-7"),
    "tabnine": (tabnine, None),
    "vibe": (vibe, None),
}


@pytest.mark.parametrize("harness", sorted(MESSAGES))
def test_the_command_session_and_agent_are_found(engine, harness):
    message, agent = MESSAGES[harness]
    assert engine.read_harness_message(json.dumps(message()).encode()) == (COMMAND, "abc123def456", agent)


@pytest.mark.parametrize("harness", sorted(MESSAGES))
def test_the_report_is_labelled_with_what_the_harness_saw_and_nothing_else_is_kept(project, engine, harness):
    directory = project.feature(events=[
        task_event("T001", "done", actor={"harness": "other", "source": "configured"}),
        task_event("T002", "in_progress", actor={"harness": "other", "source": "configured"}),
    ])
    project.set_current(directory)
    message, agent = MESSAGES[harness]
    key = harness.split("-vscode")[0]
    engine.run_hook(project.root, key, "post_tool_use", json.dumps(message()).encode())
    raw = (directory / "progress.jsonl").read_text(encoding="utf-8")
    for secret in ("SECRET-NOTE", "SECRET-OUTPUT", "SECRET-EMAIL", "/tmp/x"):
        assert secret not in raw
    events, bad, _ = engine.read_events(directory / "progress.jsonl")
    assert bad == 0
    expected = {"harness": key, "agent": agent, "session": "abc123de", "source": "observed"}
    assert [event["actor"] for event in events] == [expected, expected]
