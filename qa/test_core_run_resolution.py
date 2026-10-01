#!/usr/bin/env python3
"""Exercise the real Core ISO resolver against delayed Actions API indexing."""

import json
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
from pathlib import Path
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
    states = json.loads(os.environ['MOCK_RUN_STATES'])
    counter = Path(os.environ['MOCK_POLL_COUNTER'])
    index = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(index + 1))
    result = states[min(index, len(states) - 1)]
else:
    raise SystemExit('Unexpected gh api URL: ' + url)
print(json.dumps(result))
"""


def check_case(states, expected_code, expected_sleeps=()):
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        gh = temp / "gh"
        gh.write_text(MOCK_GH)
        gh.chmod(0o755)
        sleep = temp / "sleep"
        sleep.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$MOCK_SLEEP_LOG"\n')
        sleep.chmod(0o755)
        output = temp / "github-output"
        polls = temp / "poll-count"
        sleep_log = temp / "sleep-log"
        env = os.environ.copy()
        env.update(
            PATH=f"{directory}:{env['PATH']}",
            GITHUB_REPOSITORY="example/Xodus",
            GITHUB_OUTPUT=str(output),
            REQUESTED_SOURCE_SHA="",
            MOCK_SOURCE_SHA=SOURCE_SHA,
            MOCK_RUN_STATES=json.dumps(states),
            MOCK_POLL_COUNTER=str(polls),
            MOCK_SLEEP_LOG=str(sleep_log),
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
        assert int(polls.read_text()) == len(states), "Resolver did not inspect each expected run state"
        observed_sleeps = sleep_log.read_text().splitlines() if sleep_log.exists() else []
        assert observed_sleeps == list(expected_sleeps), observed_sleeps
        if expected_code == 0:
            assert output.read_text().splitlines() == [
                "run_id=9001",
                f"source_sha={SOURCE_SHA}",
            ]
        else:
            assert not output.exists(), "Unverified run must not be exported"


if __name__ == "__main__":
    completed_success = {"status": "completed", "conclusion": "success", "head_sha": SOURCE_SHA}
    completed_failure = {"status": "completed", "conclusion": "failure", "head_sha": SOURCE_SHA}
    in_progress = {"status": "in_progress", "conclusion": None, "head_sha": SOURCE_SHA}
    check_case([completed_success], 0)
    check_case([completed_failure], 6)
    check_case([{**completed_success, "head_sha": OTHER_SHA}], 7)
    check_case([in_progress, completed_success], 0, ("20",))
    check_case([{**in_progress, "head_sha": OTHER_SHA}], 7)
    check_case([in_progress, completed_failure], 6, ("20",))
    print("Core ISO resolver nullable polling, race and fail-closed cases: pass")
