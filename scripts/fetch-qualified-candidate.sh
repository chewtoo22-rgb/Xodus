#!/usr/bin/env bash
set -euo pipefail

REPO="${XODUS_REPO:-chewtoo22-rgb/Xodus}"
OUT_DIR="${1:-xodus-hardware-candidate}"
[[ $# -le 1 ]] || { echo "usage: $0 [candidate-dir]" >&2; exit 2; }
[[ "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || {
  echo "error: XODUS_REPO must be an owner/repository name" >&2
  exit 2
}
[[ ! -e "$OUT_DIR" && ! -L "$OUT_DIR" ]] || {
  echo "error: candidate output already exists; choose a new directory: $OUT_DIR" >&2
  exit 2
}

for cmd in gh jq sha256sum find; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "error: required command '$cmd' is not installed" >&2
    exit 2
  }
done

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

runs_json="$(gh api "/repos/${REPO}/actions/workflows/hardware-candidate.yml/runs?branch=main&status=success&per_page=1")"
if ! jq -e '
  .workflow_runs[0].conclusion == "success" and
  .workflow_runs[0].status == "completed" and
  .workflow_runs[0].head_branch == "main" and
  (.workflow_runs[0].id | numbers | . > 0 and floor == .) and
  (.workflow_runs[0].head_sha | strings | test("^[0-9a-f]{40}$"))
' <<<"$runs_json" >/dev/null; then
  echo "error: no valid successful main Hardware Candidate Gate run was found" >&2
  exit 3
fi
candidate_run_id="$(jq -er '.workflow_runs[0].id' <<<"$runs_json")"
candidate_run_sha="$(jq -er '.workflow_runs[0].head_sha' <<<"$runs_json")"
main_sha="$(gh api "/repos/${REPO}/branches/main" --jq '.commit.sha')"
if [[ ! "$main_sha" =~ ^[0-9a-f]{40}$ || "$candidate_run_sha" != "$main_sha" ]]; then
  echo "error: latest successful Hardware Candidate Gate run is stale or main HEAD is invalid" >&2
  echo "candidate=${candidate_run_sha} main=${main_sha}" >&2
  exit 3
fi

echo "Fetching qualification manifest from Hardware Candidate Gate run ${candidate_run_id}..."
gh run download "$candidate_run_id" --repo "$REPO" --name "hardware-candidate-${candidate_run_sha}" --dir "$TMP_DIR/qualification"

mapfile -d '' -t manifests < <(find "$TMP_DIR/qualification" -type f -name hardware-candidate.json -print0)
if [[ ${#manifests[@]} -ne 1 ]]; then
  echo "error: expected exactly one hardware-candidate.json in qualification artifacts" >&2
  exit 3
fi
manifest="${manifests[0]}"

if ! jq -e '
  .schema == 1 and
  (.candidate_sha | strings | test("^[0-9a-f]{40}$")) and
  .policy == "live-boot-only" and
  (.core_iso.run_id | numbers | . > 0 and floor == .) and
  (.core_iso.artifact_id | numbers | . > 0 and floor == .) and
  (.core_iso.artifact_name | strings | test("^xodus-reference-iso-[0-9a-f]{40}$")) and
  (.qa_qemu.run_id | numbers | . > 0 and floor == .) and
  .core_iso.run_id != .qa_qemu.run_id
' "$manifest" >/dev/null; then
  echo "error: malformed qualification manifest or unrecognized candidate policy" >&2
  exit 4
fi

candidate_sha="$(jq -er '.candidate_sha' "$manifest")"
core_run_id="$(jq -er '.core_iso.run_id' "$manifest")"
core_artifact="$(jq -er '.core_iso.artifact_name' "$manifest")"
qa_run_id="$(jq -er '.qa_qemu.run_id' "$manifest")"
policy="$(jq -er '.policy' "$manifest")"

if [[ "$candidate_sha" != "$candidate_run_sha" ]]; then
  echo "error: qualification workflow SHA ${candidate_run_sha} does not match manifest SHA ${candidate_sha}" >&2
  exit 4
fi

core_run_json="$(gh api "/repos/${REPO}/actions/runs/${core_run_id}")"
qa_run_json="$(gh api "/repos/${REPO}/actions/runs/${qa_run_id}")"
core_sha="$(jq -er '.head_sha' <<<"$core_run_json")"
qa_sha="$(jq -er '.head_sha' <<<"$qa_run_json")"

if [[ "$core_sha" != "$candidate_sha" || "$qa_sha" != "$candidate_sha" ]]; then
  echo "error: same-SHA release invariant failed" >&2
  echo "candidate=${candidate_sha} core=${core_sha} qa=${qa_sha}" >&2
  exit 5
fi

if ! jq -e '.status == "completed" and .conclusion == "success"' <<<"$core_run_json" >/dev/null ||
   ! jq -e '.status == "completed" and .conclusion == "success"' <<<"$qa_run_json" >/dev/null; then
  echo "error: candidate references a non-successful producer or QA run" >&2
  exit 6
fi

echo "Downloading ISO artifact '${core_artifact}' from Core ISO run ${core_run_id}..."
mkdir -p -- "$OUT_DIR"
gh run download "$core_run_id" --repo "$REPO" --name "$core_artifact" --dir "$OUT_DIR"

[[ ! -e "$OUT_DIR/hardware-candidate.json" && ! -L "$OUT_DIR/hardware-candidate.json" ]] || {
  echo "error: ISO artifact unexpectedly contains a qualification manifest" >&2
  exit 7
}
cp "$manifest" "$OUT_DIR/hardware-candidate.json"
bash "$(dirname "${BASH_SOURCE[0]}")/write-candidate-usb.sh" --verify-bundle "$OUT_DIR"
iso_file="$(find "$OUT_DIR" -type f -name '*.iso' -print -quit)"
final_main_sha="$(gh api "/repos/${REPO}/branches/main" --jq '.commit.sha')"
if [[ "$final_main_sha" != "$candidate_sha" ]]; then
  rm -f -- "$OUT_DIR/hardware-candidate.json"
  echo "error: main advanced while the candidate was downloaded; this bundle is no longer current" >&2
  echo "candidate=${candidate_sha} main=${final_main_sha}" >&2
  exit 3
fi

cat <<EOF

Xodus hardware candidate is ready.
Candidate SHA: ${candidate_sha}
ISO: ${iso_file}
Policy: ${policy}
Core ISO run: ${core_run_id}
QEMU QA run: ${qa_run_id}
Manifest: ${OUT_DIR}/hardware-candidate.json

Do not install to a physical disk while policy remains live-boot-only.
EOF
