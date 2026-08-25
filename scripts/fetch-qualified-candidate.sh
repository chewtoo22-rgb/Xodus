#!/usr/bin/env bash
set -euo pipefail

REPO="${XODUS_REPO:-chewtoo22-rgb/Xodus}"
OUT_DIR="${1:-xodus-hardware-candidate}"

for cmd in gh jq sha256sum find; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "error: required command '$cmd' is not installed" >&2
    exit 2
  }
done

mkdir -p "$OUT_DIR"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

runs_json="$(gh api "/repos/${REPO}/actions/workflows/hardware-candidate.yml/runs?branch=main&status=success&per_page=1")"
candidate_run_id="$(jq -er '.workflow_runs[0].id' <<<"$runs_json")"
candidate_run_sha="$(jq -er '.workflow_runs[0].head_sha' <<<"$runs_json")"

echo "Fetching qualification manifest from Hardware Candidate Gate run ${candidate_run_id}..."
gh run download "$candidate_run_id" --repo "$REPO" --dir "$TMP_DIR/qualification"

manifest="$(find "$TMP_DIR/qualification" -type f -name hardware-candidate.json -print -quit)"
if [[ -z "$manifest" ]]; then
  echo "error: hardware-candidate.json was not found in qualification artifacts" >&2
  exit 3
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

core_sha="$(gh api "/repos/${REPO}/actions/runs/${core_run_id}" --jq '.head_sha')"
qa_sha="$(gh api "/repos/${REPO}/actions/runs/${qa_run_id}" --jq '.head_sha')"
core_conclusion="$(gh api "/repos/${REPO}/actions/runs/${core_run_id}" --jq '.conclusion')"
qa_conclusion="$(gh api "/repos/${REPO}/actions/runs/${qa_run_id}" --jq '.conclusion')"

if [[ "$core_sha" != "$candidate_sha" || "$qa_sha" != "$candidate_sha" ]]; then
  echo "error: same-SHA release invariant failed" >&2
  echo "candidate=${candidate_sha} core=${core_sha} qa=${qa_sha}" >&2
  exit 5
fi

if [[ "$core_conclusion" != "success" || "$qa_conclusion" != "success" ]]; then
  echo "error: candidate references a non-successful producer or QA run" >&2
  echo "core=${core_conclusion} qa=${qa_conclusion}" >&2
  exit 6
fi

echo "Downloading ISO artifact '${core_artifact}' from Core ISO run ${core_run_id}..."
gh run download "$core_run_id" --repo "$REPO" --name "$core_artifact" --dir "$OUT_DIR"

checksum_file="$(find "$OUT_DIR" -maxdepth 2 -type f \( -name '*.sha256' -o -name 'SHA256SUMS' \) -print -quit)"
if [[ -z "$checksum_file" ]]; then
  echo "error: no SHA-256 checksum file was found beside the ISO artifact" >&2
  exit 7
fi

checksum_dir="$(dirname "$checksum_file")"
checksum_name="$(basename "$checksum_file")"
(
  cd "$checksum_dir"
  sha256sum -c "$checksum_name"
)

cp "$manifest" "$OUT_DIR/hardware-candidate.json"

iso_file="$(find "$OUT_DIR" -type f -name '*.iso' -print -quit)"
if [[ -z "$iso_file" ]]; then
  echo "error: no ISO file was found after artifact download" >&2
  exit 8
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
