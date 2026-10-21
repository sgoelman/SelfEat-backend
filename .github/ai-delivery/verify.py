"""Run project checks without AI or repository-write credentials."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def run(args, cwd):
    subprocess.run(args, cwd=cwd, check=True, timeout=900)


def main():
    root = Path(sys.argv[1]).resolve()
    policy = json.loads(Path(__file__).with_name("project.json").read_text())
    output = Path(sys.argv[2])
    patch_file = output / "repair.patch"
    proposed_patch = patch_file.read_bytes() if patch_file.exists() else b""
    expected_diff = subprocess.check_output(
        ["git", "diff", "HEAD", "--", "."], cwd=root
    )
    if policy["kind"] == "huvera":
        web = root / "landing-page"
        for args in (
            ["npm", "ci"],
            ["npm", "audit", "--audit-level=moderate"],
            ["npm", "run", "lint"],
            ["npm", "test"],
            ["npx", "playwright", "install", "--with-deps", "chromium"],
            ["npm", "run", "test:e2e"],
            ["npm", "run", "build"],
        ):
            run(args, web)
        if (root / "backend/pyproject.toml").exists():
            backend = root / "backend"
            run(["python3", "-m", "venv", ".venv"], backend)
            run([".venv/bin/pip", "install", "-e", ".[dev]"], backend)
            for args in (
                [".venv/bin/ruff", "check", "."],
                [".venv/bin/mypy", "src", "tests/integration"],
                [".venv/bin/pytest"],
            ):
                run(args, backend)
    elif policy["kind"] == "expo":
        backend = root.parent / "SelfEat-backend"
        run(["python3", "-m", "venv", ".venv"], backend)
        run([".venv/bin/pip", "install", "-r", "requirements-dev.txt"], backend)
        run(["npm", "ci"], root)
        run(["npx", "tsc", "--noEmit"], root)
        run(
            [
                "npx",
                "expo",
                "export",
                "--platform",
                "web",
                "--output-dir",
                "/tmp/ai-delivery-expo-export",
            ],
            root,
        )
        run(["npx", "playwright", "install", "--with-deps", "chromium"], root)
        run(["npm", "run", "test:e2e"], root)
    elif policy["kind"] == "fastapi":
        run(["python3", "-m", "venv", "/tmp/ai-delivery-venv"], root)
        run(
            ["/tmp/ai-delivery-venv/bin/pip", "install", "-r", "requirements-dev.txt"],
            root,
        )
        run(["/tmp/ai-delivery-venv/bin/python", "-m", "compileall", "-q", "app"], root)
        run(["/tmp/ai-delivery-venv/bin/python", "-m", "pytest"], root)
    else:
        raise ValueError("Unknown project; fail closed")
    # Success is recorded only after every configured command succeeds.
    if (
        subprocess.check_output(["git", "diff", "HEAD", "--", "."], cwd=root)
        != expected_diff
    ):
        raise ValueError("Application checks modified tracked code; refuse publication")
    output.mkdir(exist_ok=True)
    if proposed_patch:
        patch_file.write_bytes(proposed_patch)
    (output / "verified.json").write_text(
        json.dumps(
            {
                "project": policy["kind"],
                "tested_original_head": os.environ["HEAD_SHA"],
                "repair_sha256": hashlib.sha256(proposed_patch).hexdigest(),
                "human_approval": False,
            }
        )
    )


if __name__ == "__main__":
    main()
