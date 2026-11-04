"""Export numeric pytest results without publishing test names or failure text."""

import argparse
import json
import os
from pathlib import Path
from xml.etree import ElementTree


def counts(path: Path, exit_code: int) -> dict[str, int]:
    if exit_code not in (0, 1):
        raise ValueError("Pytest did not finish a normal test run")
    root = ElementTree.parse(path).getroot()
    suites = list(root) if root.tag == "testsuites" else [root]
    if len(suites) != 1 or suites[0].tag != "testsuite":
        raise ValueError("Expected one pytest suite")
    suite = suites[0]
    total, failed, broken, skipped = (
        int(suite.attrib[key]) for key in ("tests", "failures", "errors", "skipped")
    )
    cases = suite.findall("testcase")
    if total <= 0 or total != len(cases) or min(failed, broken, skipped) < 0:
        raise ValueError("Empty or inconsistent test report")
    observed = tuple(
        sum(case.find(tag) is not None for case in cases)
        for tag in ("failure", "error", "skipped")
    )
    if observed != (failed, broken, skipped) or failed + broken + skipped > total:
        raise ValueError("Test status counts do not match the report")
    if bool(failed + broken) != (exit_code == 1):
        raise ValueError("Report does not match the pytest exit status")
    return {
        "total": total,
        "passed": total - failed - broken - skipped,
        "failed": failed,
        "broken": broken,
        "skipped": skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("exit_code", type=int)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = counts(args.report, args.exit_code)
    provenance = {
        key: os.environ[name]
        for key, name in (
            ("repository", "GITHUB_REPOSITORY"),
            ("tested_sha", "GITHUB_SHA"),
            ("event", "GITHUB_EVENT_NAME"),
            ("ref", "GITHUB_REF"),
            ("run_id", "GITHUB_RUN_ID"),
            ("run_attempt", "GITHUB_RUN_ATTEMPT"),
        )
    }
    args.output.write_text(
        json.dumps({"suite": "backend-pytest", **provenance, **result}) + "\n"
    )
    print(
        "Backend pytest:", ", ".join(f"{key}={value}" for key, value in result.items())
    )


if __name__ == "__main__":
    main()
