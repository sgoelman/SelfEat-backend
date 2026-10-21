import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('delivery', Path(__file__).with_name('run.py'))
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BoundaryTests(unittest.TestCase):
    def test_protected_and_traversal_paths(self):
        for path in ('../outside', '/tmp/file', '.github/workflows/a.yml', '.env.local', 'src/../secret', 'archive/a', 'CLAUDE.md', 'AGENTS.md', 'src\\file'):
            self.assertFalse(module.safe_path(path), path)
        self.assertTrue(module.safe_path('src/orders.py'))

    def test_invalid_or_contradictory_review_fails_closed(self):
        for value in ({}, {'ready': 'yes', 'findings': []}, {'ready': True, 'findings': [{'path': 'a', 'severity': 'high', 'issue': 'bad'}]}):
            with self.assertRaises(ValueError):
                module.validate_review(value)

    def test_repair_cannot_edit_unrelated_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.py').write_text('before')
            with self.assertRaises(ValueError):
                module.apply_edits(root, [{'path': 'a.py', 'content': 'after'}], {'b.py'})
            self.assertEqual((root / 'a.py').read_text(), 'before')

    def test_validation_is_atomic_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.py').write_text('before')
            (root / 'link.py').symlink_to(root / 'a.py')
            with self.assertRaises(ValueError):
                module.apply_edits(root, [{'path': 'a.py', 'content': 'after'}, {'path': 'link.py', 'content': 'bad'}], {'a.py', 'link.py'})
            self.assertEqual((root / 'a.py').read_text(), 'before')

    def test_allowed_repair_applies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.py').write_text('before')
            module.apply_edits(root, [{'path': 'a.py', 'content': 'after'}], {'a.py'})
            self.assertEqual((root / 'a.py').read_text(), 'after')


if __name__ == '__main__':
    unittest.main()

class OrchestrationTests(unittest.TestCase):
    def test_two_repairs_then_stop_with_findings(self):
        from unittest.mock import patch
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.py').write_text('before')
            output = root / 'results'
            def fake_command(args, **kwargs):
                calls.append(args[0])
                if args[:3] == ['git', 'diff', '--name-only']:
                    return 'a.py\n'
                if args[0] == 'git':
                    return 'diff fixture'
                if args[0] == 'claude':
                    return '{"structured_output":{"ready":false,"findings":[{"path":"a.py","severity":"high","issue":"fixture"}]}}'
                result = Path(args[args.index('--output-last-message') + 1])
                result.write_text('{"edits":[{"path":"a.py","content":"after"}]}')
                return ''
            env = {'ANTHROPIC_API_KEY': 'fixture', 'OPENAI_API_KEY': 'fixture', 'CLAUDE_MODEL': 'fixture', 'CODEX_MODEL': 'fixture'}
            with patch.dict(module.os.environ, env), patch.object(module, 'command', side_effect=fake_command):
                with self.assertRaisesRegex(ValueError, 'at most two'):
                    module.run(root, 'base', output)
            self.assertEqual(calls.count('claude'), 3)
            self.assertEqual(calls.count('codex'), 2)
            self.assertTrue((output / 'repair.patch').is_file())

    def test_missing_credentials_makes_no_calls(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(module.os.environ, {}, clear=True), patch.object(module, 'command') as command:
                with self.assertRaisesRegex(ValueError, 'credentials'):
                    module.run(Path(directory), 'base', Path(directory) / 'results')
                command.assert_not_called()
