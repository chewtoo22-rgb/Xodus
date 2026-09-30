#!/usr/bin/env python3
"""Exercise the real Core ISO resolver against delayed Actions API indexing."""

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "a" * 40
OTHER_SHA = "b" * 40


def resolver_script():
    workflow = (ROOT / ".github/workflows/qa-qemu-smoke.yml").read_text()
    marker = "      - name: Resolve successful Core ISO build\n"
    _, block = workflow.split(marker, 1)
    block = block.split("      - name: Reclaim runner disk\n", 1)[0]
    _, body = block.split("        run: |\n", 1)
    script = textwrap.dedent(body)
    for expression, value in {
        "${{ github.event_name }}": "pull_request",
        "${{ github.event.workflow_run.id }}": "",
        "${{ github.event.workflow_run.head_sha }}": "",
        "${{ github.event.workflow_run.conclusion }}": "",
        "${{ github.event.pull_request.head.sha }}": SOURCE_SHA,
    }.items():
        script = script.replace(expression, value)
    assert "${{" not in script, "Unexpected GitHub expression in resolver"
    return script


MOCK_GH = """#!/usr/bin/env python3
import json
import os
import sys

url = sys.argv[-1]
sha = os.environ['MOCK_SOURCE_SHA']
if 'status=success' in url:
    # The list index has not caught up with the completed run endpoint.
    result = {'workflow_runs': []}
elif 'workflows/core-iso-build.yml/runs?per_page=50' in url:
    result = {'workflow_runs': [
        {'id': 9001, 'head_sha': sha, 'event': 'pull_request', 'status': 'completed'}
    ]}
elif url.endswith('/actions/runs/9001'):
    result = {
        'status': 'completed',
        'conclusion': os.environ['MOCK_CONCLUSION'],
        'head_sha': os.environ['MOCK_RUN_SHA'],
    }
else:
    raise SystemExit('Unexpected gh api URL: ' + url)
print(json.dumps(result))
"""


def check_case(conclusion, run_sha, expected_code):
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        gh = temp / "gh"
        gh.write_text(MOCK_GH)
        gh.chmod(0o755)
        output = temp / "github-output"
        env = os.environ.copy()
        env.update(
            PATH=f"{directory}:{env['PATH']}",
            GITHUB_REPOSITORY="example/Xodus",
            GITHUB_OUTPUT=str(output),
            REQUESTED_SOURCE_SHA="",
            MOCK_SOURCE_SHA=SOURCE_SHA,
            MOCK_RUN_SHA=run_sha,
            MOCK_CONCLUSION=conclusion,
        )
        result = subprocess.run(
            ["bash", "-c", resolver_script()],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == expected_code, (result.stdout, result.stderr)
        if expected_code == 0:
            assert output.read_text().splitlines() == [
                "run_id=9001",
                f"source_sha={SOURCE_SHA}",
            ]
        else:
            assert not output.exists(), "Unverified run must not be exported"


if __name__ == "__main__":
    check_case("success", SOURCE_SHA, 0)
    check_case("failure", SOURCE_SHA, 6)
    check_case("success", OTHER_SHA, 7)
    print("Core ISO resolver race and fail-closed cases: pass")
