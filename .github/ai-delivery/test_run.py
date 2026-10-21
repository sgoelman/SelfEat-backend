import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "delivery", Path(__file__).with_name("run.py")
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BoundaryTests(unittest.TestCase):
    def test_protected_and_traversal_paths(self):
        for path in (
            "../outside",
            "/tmp/file",
            ".github/workflows/a.yml",
            ".env.local",
            "src/../secret",
            "archive/a",
            "CLAUDE.md",
            "AGENTS.md",
            "src\\file",
        ):
            self.assertFalse(module.safe_path(path), path)
        self.assertTrue(module.safe_path("src/orders.py"))

    def test_invalid_or_contradictory_review_fails_closed(self):
        for value in (
            {},
            {"ready": "yes", "findings": []},
            {
                "ready": True,
                "findings": [{"path": "a", "severity": "high", "issue": "bad"}],
            },
        ):
            with self.assertRaises(ValueError):
                module.validate_review(value)

    def test_repair_cannot_edit_unrelated_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("before")
            with self.assertRaises(ValueError):
                module.apply_edits(
                    root, [{"path": "a.py", "content": "after"}], {"b.py"}
                )
            self.assertEqual((root / "a.py").read_text(), "before")

    def test_validation_is_atomic_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("before")
            (root / "link.py").symlink_to(root / "a.py")
            with self.assertRaises(ValueError):
                module.apply_edits(
                    root,
                    [
                        {"path": "a.py", "content": "after"},
                        {"path": "link.py", "content": "bad"},
                    ],
                    {"a.py", "link.py"},
                )
            self.assertEqual((root / "a.py").read_text(), "before")

    def test_allowed_repair_applies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("before")
            module.apply_edits(root, [{"path": "a.py", "content": "after"}], {"a.py"})
            self.assertEqual((root / "a.py").read_text(), "after")


class OrchestrationTests(unittest.TestCase):
    def test_two_repairs_then_stop_with_findings(self):
        from unittest.mock import patch

        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("before")
            output = root / "results"

            def fake_command(args, **kwargs):
                calls.append(args[0])
                if args[:3] == ["git", "diff", "--name-only"]:
                    return "a.py\n"
                if args[0] == "git":
                    return "diff fixture"
                if args[0] == "claude":
                    return '{"structured_output":{"ready":false,"findings":[{"path":"a.py","severity":"high","issue":"fixture"}]}}'
                result = Path(args[args.index("--output-last-message") + 1])
                result.write_text('{"edits":[{"path":"a.py","content":"after"}]}')
                return ""

            env = {
                "ANTHROPIC_API_KEY": "fixture",
                "OPENAI_API_KEY": "fixture",
                "CLAUDE_MODEL": "fixture",
                "CODEX_MODEL": "fixture",
            }
            with (
                patch.dict(module.os.environ, env),
                patch.object(module, "command", side_effect=fake_command),
                self.assertRaisesRegex(ValueError, "at most two"),
            ):
                module.run(root, "base", output)
            self.assertEqual(calls.count("claude"), 3)
            self.assertEqual(calls.count("codex"), 2)
            self.assertTrue((output / "repair.patch").is_file())

    def test_missing_credentials_makes_no_calls(self):
        from unittest.mock import patch

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(module.os.environ, {}, clear=True),
            patch.object(module, "command") as command,
        ):
            with self.assertRaisesRegex(ValueError, "credentials"):
                module.run(Path(directory), "base", Path(directory) / "results")
            command.assert_not_called()


class VerificationTests(unittest.TestCase):
    def test_failed_application_check_never_creates_success_evidence(self):
        import subprocess
        from unittest.mock import patch

        spec = importlib.util.spec_from_file_location(
            "verify", Path(__file__).with_name("verify.py")
        )
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(
                    verifier.sys, "argv", ["verify", directory, str(root / "evidence")]
                ),
                patch.object(
                    verifier.subprocess, "check_output", return_value=b"fixture-diff"
                ),
                patch.object(
                    verifier,
                    "run",
                    side_effect=subprocess.CalledProcessError(1, "fixture"),
                ),
                self.assertRaises(subprocess.CalledProcessError),
            ):
                verifier.main()
            self.assertFalse((root / "evidence/verified.json").exists())

    def test_success_records_exact_source_revision_and_no_human_approval(self):
        import json
        from unittest.mock import patch

        spec = importlib.util.spec_from_file_location(
            "verify", Path(__file__).with_name("verify.py")
        )
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(
                    verifier.sys, "argv", ["verify", directory, str(root / "evidence")]
                ),
                patch.object(verifier, "run"),
                patch.object(
                    verifier.subprocess, "check_output", return_value=b"fixture-diff"
                ),
                patch.dict(verifier.os.environ, {"HEAD_SHA": "fixture-exact-revision"}),
            ):
                verifier.main()
            proof = json.loads((root / "evidence/verified.json").read_text())
            self.assertEqual(proof["tested_original_head"], "fixture-exact-revision")
            self.assertIs(proof["human_approval"], False)


if __name__ == "__main__":
    unittest.main()
