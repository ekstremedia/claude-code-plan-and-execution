#!/usr/bin/env python3
"""Tests for the two transcript-reading scripts, against synthetic transcripts.

    python3 -m unittest discover -s tests

The record shapes below are the ones Claude Code 2.1.322 writes: a streamed
assistant message appears as several records that repeat its blocks, a tool
result arrives in a user record, and a worker's transcript sits under
`<session>/subagents/agent-<id>.jsonl` beside an `agent-<id>.meta.json`.

Standard library only.
"""

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(filename):
    """Import a hyphenated script from scripts/ as a module."""
    name = filename[: -len(".py")].replace("-", "_")
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "scripts", filename)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify_models = load("verify-models.py")
statusline = load("subagent-statusline.py")


def assistant(msg_id, *blocks, effort="medium", model="claude-sonnet-5-5"):
    """One main-thread or worker assistant record."""
    return {
        "type": "assistant",
        "effort": effort,
        "timestamp": "2026-11-10T19:43:21.000Z",
        "message": {
            "id": msg_id,
            "model": model,
            "content": list(blocks),
            "usage": {"input_tokens": 1, "output_tokens": 10},
        },
    }


def tool_use(block_id, name, **inp):
    return {"type": "tool_use", "id": block_id, "name": name, "input": inp}


def tool_result(block_id, text, is_error=False, **tool_use_result):
    """The user record that carries one tool result."""
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": block_id,
                    "content": text,
                    "is_error": is_error,
                }
            ]
        },
        "toolUseResult": tool_use_result or text,
    }


def write_jsonl(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, separators=(",", ":")) + "\n")


class VerifyModels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.session = os.path.join(self.tmp.name, "abc.jsonl")

    def worker(self, agent_id, agent_type, shape):
        base = os.path.join(self.tmp.name, "abc", "subagents", f"agent-{agent_id}")
        write_jsonl(base + ".jsonl", [assistant("w1", model="claude-sonnet-5-5")])
        with open(base + ".meta.json", "w", encoding="utf-8") as fh:
            json.dump({"agentType": agent_type, "requestShape": shape}, fh)

    def test_a_streamed_delegation_is_counted_once(self):
        call = tool_use("toolu_1", "Agent", subagent_type="implementer")
        write_jsonl(
            self.session,
            [
                # The same message, written twice as it streamed.
                assistant("m1", call),
                assistant("m1", call),
                assistant("m2", tool_use("toolu_2", "Agent", subagent_type="plan-reviewer")),
            ],
        )
        summary = verify_models.scan(self.session)
        self.assertEqual(summary["delegations"], {"implementer": 1, "plan-reviewer": 1})

    def test_request_shape_is_read_from_meta(self):
        write_jsonl(self.session, [assistant("m1")])
        self.worker("a1", "implementer", "foreground")
        self.worker("a2", "implementer", "background")
        entry = verify_models.scan_subagents(self.session)["implementer"]
        self.assertEqual(entry["runs"], 2)
        self.assertEqual(entry["shapes"], {"foreground": 1, "background": 1})

    def test_a_backgrounded_worker_is_reported(self):
        write_jsonl(self.session, [assistant("m1")])
        self.worker("a1", "implementer", "background")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            verify_models.report(verify_models.scan(self.session))
        self.assertIn("WARNING: implementer ran in the background x1", out.getvalue())

    def test_a_pin_drop_after_a_notification_is_found(self):
        write_jsonl(
            self.session,
            [
                {
                    "type": "attachment",
                    "timestamp": "2026-11-10T19:42:52.000Z",
                    "attachment": {
                        "type": "command_permissions",
                        "allowedTools": [],
                        "model": "claude-sonnet-5-5",
                    },
                },
                assistant("m1", effort="medium"),
                {"type": "user", "origin": {"kind": "task-notification"}, "message": {"content": "x"}},
                assistant("m2", effort="xhigh", model="claude-opus-5-5"),
            ],
        )
        summary = verify_models.scan(self.session)
        self.assertEqual(summary["task_notifications"], 1)
        self.assertEqual(len(summary["pin_drops"]), 1)
        self.assertTrue(summary["pin_drops"][0]["after_notification"])


class SubagentStatusline(unittest.TestCase):
    CWD = "/work/project"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.transcript = os.path.join(self.tmp.name, "abc.jsonl")
        self.worker = os.path.join(self.tmp.name, "abc", "subagents", "agent-a1.jsonl")
        # Keep the per-worker state files inside the test's own directory.
        self._tempdir = tempfile.tempdir
        tempfile.tempdir = self.tmp.name
        self.addCleanup(setattr, tempfile, "tempdir", self._tempdir)
        self._no_color = os.environ.get("NO_COLOR")
        os.environ["NO_COLOR"] = "1"
        self.addCleanup(self._restore_no_color)

    def _restore_no_color(self):
        if self._no_color is None:
            os.environ.pop("NO_COLOR", None)
        else:
            os.environ["NO_COLOR"] = self._no_color

    def run_script(self, columns=200, status="running", task_id="a1"):
        """Feed one tick to the script; return {id: content}."""
        payload = {
            "transcript_path": self.transcript,
            "cwd": self.CWD,
            "columns": columns,
            "tasks": [
                {
                    "id": task_id,
                    "agentType": "implementer",
                    "status": status,
                    "description": "Phase 2: scan reader",
                    "startTime": int((time.time() - 125) * 1000),
                    "tokenCount": 41200,
                    "cwd": self.CWD,
                }
            ],
        }
        stdin, out = sys.stdin, io.StringIO()
        sys.stdin = io.StringIO(json.dumps(payload))
        try:
            with contextlib.redirect_stdout(out):
                self.assertEqual(statusline.main(), 0)
        finally:
            sys.stdin = stdin
        rows = {}
        for line in out.getvalue().splitlines():
            rec = json.loads(line)
            rows[rec["id"]] = rec["content"]
        return rows

    def test_the_row_shows_activity_files_and_the_last_check(self):
        write_jsonl(
            self.worker,
            [
                {"type": "attachment", "attachment": {"type": "hook_success"}},
                assistant("w1", tool_use("t1", "Read", file_path=f"{self.CWD}/app/A.php")),
                tool_result("t1", "<?php"),
                assistant("w2", tool_use("t2", "Edit", file_path=f"{self.CWD}/app/A.php")),
                assistant("w2", tool_use("t2", "Edit", file_path=f"{self.CWD}/app/A.php")),
                tool_result("t2", "ok"),
                # An Edit that failed changed nothing, so it is not a changed file.
                assistant("w2b", tool_use("t2b", "Edit", file_path=f"{self.CWD}/app/Nope.php")),
                tool_result("t2b", "String to replace not found in file.", is_error=True),
                assistant("w3", tool_use("t3", "Write", file_path=f"{self.CWD}/tests/ATest.php")),
                tool_result("t3", "ok"),
                assistant("w4", tool_use("t4", "Bash", command="bin/test-php tests/ATest.php")),
                tool_result("t4", "PASS  3 passed  (tests/ATest.php)"),
                assistant("w5", tool_use("t5", "Edit", file_path=f"{self.CWD}/app/B.php")),
            ],
        )
        # B.php is the current action, and not yet a changed file: its result
        # has not come back.
        row = self.run_script()["a1"]
        self.assertEqual(
            row,
            "implementer · Phase 2: scan reader · edit app/B.php · 2 files changed"
            " · test-php ok · 41.2k tok · 2m",
        )
        write_jsonl(self.worker, [tool_result("t5", "ok")])
        self.assertIn("3 files changed", self.run_script()["a1"])

    def test_a_failed_check_and_a_shell_edit_are_seen(self):
        write_jsonl(
            self.worker,
            [
                assistant("w1", tool_use("t1", "Bash", command="cd x && bin/check-php app/")),
                tool_result("t1", "Exit code 1\nFAIL  exit 1  (app/)", is_error=True),
                assistant("w2", tool_use("t2", "Bash", command="python3 - <<'EOF'\nopen('f')\nEOF")),
                tool_result(
                    "t2",
                    "",
                    stdout="",
                    bashEditDiff={"files": [{"filePath": f"{self.CWD}/app/C.php", "hunks": []}]},
                ),
            ],
        )
        row = self.run_script()["a1"]
        self.assertIn("edit app/C.php", row)
        self.assertIn("1 file changed", row)
        self.assertIn("check-php FAIL", row)

    def test_only_appended_records_are_parsed_on_the_next_tick(self):
        write_jsonl(
            self.worker,
            [
                assistant("w1", tool_use("t1", "Edit", file_path=f"{self.CWD}/a.txt")),
                tool_result("t1", "ok"),
            ],
        )
        self.assertIn("1 file changed", self.run_script()["a1"])
        with open(self.worker, "a", encoding="utf-8") as fh:
            # A record still being written: no newline yet, so not parsed yet.
            fh.write('{"type":"assistant","message":{"content":[{"type":"tool_use"')
        self.assertNotIn("write b.txt", self.run_script()["a1"])
        with open(self.worker, "a", encoding="utf-8") as fh:
            fh.write(',"id":"t2","name":"Write","input":{"file_path":"/work/project/b.txt"}}]}}\n')
        row = self.run_script()["a1"]
        self.assertIn("write b.txt", row)
        self.assertIn("1 file changed", row)
        # The second tick resumed from the cached offset rather than starting over.
        write_jsonl(self.worker, [tool_result("t2", "ok")])
        self.assertIn("2 files changed", self.run_script()["a1"])

    def test_the_row_never_exceeds_the_width_it_was_given(self):
        write_jsonl(
            self.worker,
            [
                assistant(
                    "w1",
                    tool_use("t1", "Edit", file_path=f"{self.CWD}/app/Services/Deep/Nested/Long.php"),
                )
            ],
        )
        for columns in (200, 120, 80, 60, 40, 20, 5):
            row = self.run_script(columns=columns)["a1"]
            self.assertLessEqual(len(row), columns, f"{columns}: {row!r}")
        # At a comfortable width the path keeps its tail, the part that names the file.
        self.assertIn("Long.php", self.run_script(columns=80)["a1"])

    def test_a_failed_check_fits_too_and_is_the_last_fact_to_go(self):
        write_jsonl(
            self.worker,
            [
                assistant("w1", tool_use("t1", "Edit", file_path=f"{self.CWD}/app/A.php")),
                tool_result("t1", "ok"),
                assistant("w2", tool_use("t2", "Bash", command="bin/check-php app/")),
                tool_result("t2", "Exit code 1", is_error=True),
            ],
        )
        for columns in (200, 80, 60, 40, 30, 20, 12, 5, 1):
            row = self.run_script(columns=columns)["a1"]
            self.assertLessEqual(len(row), columns, f"{columns}: {row!r}")
        self.assertIn("check-php FAIL", self.run_script(columns=60)["a1"])
        # Too narrow for the wrapper's name: the failure itself still shows.
        self.assertEqual(self.run_script(columns=20)["a1"], "implementer · FAIL")

    def test_a_cache_directory_someone_else_could_read_is_not_used(self):
        write_jsonl(
            self.worker,
            [
                assistant("w1", tool_use("t1", "Edit", file_path=f"{self.CWD}/a.txt")),
                tool_result("t1", "ok"),
            ],
        )
        directory = statusline.cache_dir()
        self.assertEqual(os.stat(directory).st_mode & 0o777, 0o700)

        # Left open by whoever made it: closed again before anything is written.
        os.chmod(directory, 0o777)
        self.assertEqual(statusline.cache_dir(), directory)
        self.assertEqual(os.stat(directory).st_mode & 0o777, 0o700)
        self.assertIn("1 file changed", self.run_script()["a1"])
        for name in os.listdir(directory):
            self.assertEqual(os.stat(os.path.join(directory, name)).st_mode & 0o777, 0o600)

        # Planted as a symlink to somewhere else: refused, and the row is
        # still produced, from a full parse with nothing written.
        elsewhere = os.path.join(self.tmp.name, "elsewhere")
        os.mkdir(elsewhere)
        for name in os.listdir(directory):
            os.unlink(os.path.join(directory, name))
        os.rmdir(directory)
        os.symlink(elsewhere, directory)
        self.assertIsNone(statusline.cache_dir())
        self.assertIn("1 file changed", self.run_script()["a1"])
        self.assertEqual(os.listdir(elsewhere), [])

    def test_a_finished_worker_shows_its_status_not_its_last_tool(self):
        write_jsonl(
            self.worker,
            [assistant("w1", tool_use("t1", "Edit", file_path=f"{self.CWD}/a.txt"))],
        )
        row = self.run_script(status="completed")["a1"]
        self.assertIn("completed", row)
        self.assertNotIn("edit a.txt", row)

    def test_a_worker_without_a_transcript_keeps_its_default_row(self):
        self.assertEqual(self.run_script(task_id="missing"), {})
        self.assertEqual(self.run_script(task_id="../../etc/passwd"), {})


if __name__ == "__main__":
    unittest.main()
