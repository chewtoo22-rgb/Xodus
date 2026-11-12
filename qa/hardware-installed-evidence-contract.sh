#!/usr/bin/env bash
# Contract suite for qa/hardware-installed-evidence.sh.
#
# Exercises every refusal exit code the collector defines and asserts that no
# evidence directory (and so no summary.txt) is left behind after a refusal:
#   40  live/overlay root (overlay, airootfs, squashfs, tmpfs)
#   41  current boot is not UEFI (and the bypass only accepts the literal "1")
#   42  XODUS_CANDIDATE_SHA missing or not an exact lowercase 40-char SHA
#   43  running build-info does not match the candidate (real verifier)
#   44  verifier passed but upstream provenance is missing or malformed
#
# The real collector is never modified and gains no build-info override: it
# always verifies "/" via its sibling x1-build-info-contract.sh. Cases 40-43 run
# the real collector unmodified. Case 44 and the positive path cannot be reached
# without a matching /usr/lib/xodus/build-info on the host, so they run a
# byte-identical copy of the collector in a sandbox next to a stub verifier.
# This exercises the collector's own logic while leaving real runs bound to the
# installed build-info.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
collector="$repo_root/qa/hardware-installed-evidence.sh"
verifier="$repo_root/qa/x1-build-info-contract.sh"

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
pass() { printf 'ok   %s\n' "$*"; }

# Invoke through bash so the checkout file mode cannot hide collector behaviour.
[[ -f "$collector" && ! -L "$collector" ]] || fail "collector is missing or a symlink: $collector"
[[ -f "$verifier" && ! -L "$verifier" ]] || fail "verifier is missing or a symlink: $verifier"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

good_sha=0123456789abcdef0123456789abcdef01234567
upstream=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
# A SHA that is well formed but cannot match any real installed build-info.
mismatch_sha=0000000000000000000000000000000000000000

# expect_refusal <rc> <name> <collector> [VAR=value ...]
# Runs the collector with a clean, explicit environment and asserts the exact
# refusal code and that the evidence directory was never created.
expect_refusal() {
  local expected="$1" name="$2" script="$3"
  shift 3
  local out="$tmp/out/$name"
  local rc
  set +e
  env -i PATH="$PATH" HOME="$tmp" "$@" \
    bash "$script" "$out" >"$tmp/$name.stdout" 2>"$tmp/$name.stderr"
  rc=$?
  set -e
  if [[ "$rc" -ne "$expected" ]]; then
    cat "$tmp/$name.stderr" >&2 || true
    fail "$name returned $rc, expected $expected"
  fi
  [[ ! -e "$out" ]] || fail "$name left an evidence directory behind: $out"
  [[ ! -e "$out/summary.txt" ]] || fail "$name left summary.txt behind"
  grep -q '^refusing installed-system evidence' "$tmp/$name.stderr" \
    || fail "$name did not print a refusal message"
  pass "$name -> $rc, no evidence written"
}

mkdir -p "$tmp/out"
installed_root=(XODUS_CONTRACT_ROOT_SOURCE=/dev/sda2 XODUS_CONTRACT_ROOT_FSTYPE=ext4)

# --- 40: live-media and ephemeral roots (from PR #44) ------------------------
expect_refusal 40 overlay-source "$collector" XODUS_CONTRACT_ROOT_SOURCE=overlay XODUS_CONTRACT_ROOT_FSTYPE=ext4 XODUS_CONTRACT_ALLOW_NO_EFI=1
expect_refusal 40 overlay-fstype "$collector" XODUS_CONTRACT_ROOT_SOURCE=/dev/sda2 XODUS_CONTRACT_ROOT_FSTYPE=overlay XODUS_CONTRACT_ALLOW_NO_EFI=1
expect_refusal 40 squashfs-root "$collector" XODUS_CONTRACT_ROOT_SOURCE=/dev/loop0 XODUS_CONTRACT_ROOT_FSTYPE=squashfs XODUS_CONTRACT_ALLOW_NO_EFI=1
expect_refusal 40 airootfs-root "$collector" XODUS_CONTRACT_ROOT_SOURCE=airootfs XODUS_CONTRACT_ROOT_FSTYPE=ext4 XODUS_CONTRACT_ALLOW_NO_EFI=1
expect_refusal 40 tmpfs-root "$collector" XODUS_CONTRACT_ROOT_SOURCE=tmpfs XODUS_CONTRACT_ROOT_FSTYPE=tmpfs XODUS_CONTRACT_ALLOW_NO_EFI=1
# The live-root gate runs first: a valid candidate SHA must not get past it.
expect_refusal 40 overlay-with-valid-sha "$collector" XODUS_CONTRACT_ROOT_SOURCE=overlay XODUS_CONTRACT_ROOT_FSTYPE=overlay XODUS_CONTRACT_ALLOW_NO_EFI=1 XODUS_CANDIDATE_SHA="$good_sha"

# --- 41: non-UEFI boot -------------------------------------------------------
# /sys/firmware/efi cannot be faked without root, so assert whichever branch
# applies to this host. Either way, only the literal "1" may bypass the gate.
if [[ ! -d /sys/firmware/efi ]]; then
  expect_refusal 41 non-uefi "$collector" "${installed_root[@]}" XODUS_CANDIDATE_SHA="$good_sha"
  for bypass in 0 true yes 01 ' 1' '1 '; do
    expect_refusal 41 "non-uefi-bypass-${bypass// /_}" "$collector" "${installed_root[@]}" XODUS_CONTRACT_ALLOW_NO_EFI="$bypass" XODUS_CANDIDATE_SHA="$good_sha"
  done
else
  # On a UEFI host the gate must pass without any bypass, reaching the SHA gate.
  expect_refusal 42 uefi-host-reaches-sha-gate "$collector" "${installed_root[@]}"
  printf 'note 41 not reachable on this UEFI host; asserted the gate passes instead\n'
fi

# --- 42: candidate SHA must be an exact lowercase 40-hex SHA -----------------
bad_shas=(
  ''
  "${good_sha^^}"
  "${good_sha:0:39}"
  "${good_sha}0"
  "${good_sha:0:39}g"
  " $good_sha"
  "$good_sha "
  "$good_sha"$'\n'
  "HEAD"
)
i=0
for sha in "${bad_shas[@]}"; do
  expect_refusal 42 "bad-sha-$i" "$collector" "${installed_root[@]}" XODUS_CONTRACT_ALLOW_NO_EFI=1 XODUS_CANDIDATE_SHA="$sha"
  i=$((i + 1))
done
expect_refusal 42 unset-sha "$collector" "${installed_root[@]}" XODUS_CONTRACT_ALLOW_NO_EFI=1

# --- 43: real verifier against "/" -------------------------------------------
# No override exists for the build-info path, so the real collector checks the
# host's /usr/lib/xodus/build-info. It is absent on CI and dev hosts, and a real
# Xodus install cannot carry the all-zero source commit.
expect_refusal 43 host-build-info-mismatch "$collector" "${installed_root[@]}" XODUS_CONTRACT_ALLOW_NO_EFI=1 XODUS_CANDIDATE_SHA="$mismatch_sha"
# Prove the default build-info path is still the hard-coded installed one and
# that no XODUS_BUILD_INFO-style override is honoured.
fake_info="$tmp/fake-root/usr/lib/xodus/build-info"
mkdir -p "$(dirname "$fake_info")"
printf 'XODUS_SOURCE_COMMIT=%s\nXODUS_UPSTREAM_COMMIT=%s\n' "$mismatch_sha" "$upstream" >"$fake_info"
expect_refusal 43 build-info-override-ignored "$collector" "${installed_root[@]}" XODUS_CONTRACT_ALLOW_NO_EFI=1 XODUS_CANDIDATE_SHA="$mismatch_sha" \
  XODUS_BUILD_INFO="$fake_info" XODUS_BUILD_INFO_ROOT="$tmp/fake-root" XODUS_ROOT="$tmp/fake-root"
grep -Fq 'bash "$script_dir/x1-build-info-contract.sh" /' "$collector" \
  || fail 'collector no longer verifies "/" with its sibling x1-build-info-contract.sh'
# Exact set of XODUS_* names the collector may reference; a new knob (such as a
# build-info path override) must be reviewed and added here deliberately.
expected_vars=$'XODUS_CANDIDATE_SHA\nXODUS_CONTRACT_ALLOW_NO_EFI\nXODUS_CONTRACT_ROOT_FSTYPE\nXODUS_CONTRACT_ROOT_SOURCE\nXODUS_EXPECTED_SOURCE_COMMIT'
actual_vars="$(grep -oE 'XODUS_[A-Z_]+' "$collector" | LC_ALL=C sort -u)"
[[ "$actual_vars" == "$expected_vars" ]] \
  || fail "collector XODUS_* variables changed: $(tr '\n' ' ' <<<"$actual_vars")"
pass 'collector binds provenance to "/" with no override'

# --- Sandbox: byte-identical collector copy beside a stub verifier -----------
sandbox="$tmp/sandbox/qa"
mkdir -p "$sandbox"
cp "$collector" "$sandbox/hardware-installed-evidence.sh"
cmp -s "$collector" "$sandbox/hardware-installed-evidence.sh" || fail 'sandbox collector copy differs'
sandboxed="$sandbox/hardware-installed-evidence.sh"
# The stub records how it was called and replays a chosen verifier result.
cat >"$sandbox/x1-build-info-contract.sh" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
printf 'root=%s\nexpected=%s\n' "${1:-}" "${XODUS_EXPECTED_SOURCE_COMMIT:-}" >"$STUB_LOG"
case "$STUB_MODE" in
  fail) echo 'ERROR: stub mismatch' >&2; exit 68 ;;
  pass) printf 'schema=1\nx1_build_info=pass\ncandidate_sha=%s\nupstream_sha=%s\nhardware_validation_claim=false\n' "$XODUS_EXPECTED_SOURCE_COMMIT" "$STUB_UPSTREAM" ;;
  missing) printf 'schema=1\nx1_build_info=pass\n' ;;
  duplicate) printf 'upstream_sha=%s\nupstream_sha=%s\n' "$STUB_UPSTREAM" "$STUB_UPSTREAM" ;;
  malformed) printf 'upstream_sha=%s\n' "$STUB_UPSTREAM" ;;
esac
STUB

sb_env=("${installed_root[@]}" XODUS_CONTRACT_ALLOW_NO_EFI=1 XODUS_CANDIDATE_SHA="$good_sha" STUB_LOG="$tmp/stub.log" STUB_UPSTREAM="$upstream")

expect_refusal 43 verifier-failure "$sandboxed" "${sb_env[@]}" STUB_MODE=fail
grep -Fqx 'root=/' "$tmp/stub.log" || fail 'verifier was not asked to check "/"'
grep -Fqx "expected=$good_sha" "$tmp/stub.log" || fail 'verifier was not bound to the candidate SHA'
pass 'verifier is called on "/" with XODUS_EXPECTED_SOURCE_COMMIT=candidate'

# --- 44: upstream provenance missing, duplicated or malformed ----------------
expect_refusal 44 upstream-missing "$sandboxed" "${sb_env[@]}" STUB_MODE=missing
expect_refusal 44 upstream-duplicate "$sandboxed" "${sb_env[@]}" STUB_MODE=duplicate
for bad_up in "${upstream^^}" "${upstream:0:39}" "${upstream}a" not-a-sha ''; do
  expect_refusal 44 "upstream-malformed-${#bad_up}" "$sandboxed" "${sb_env[@]}" STUB_MODE=malformed STUB_UPSTREAM="$bad_up"
done

# --- Positive path (sandbox only) --------------------------------------------
# Diagnostic commands are best-effort and read-only; only the summary is checked.
installed="$tmp/out/installed"
env -i PATH="$PATH" HOME="$tmp" "${sb_env[@]}" STUB_MODE=pass \
  bash "$sandboxed" "$installed" >"$tmp/installed.stdout" 2>"$tmp/installed.stderr" \
  || { cat "$tmp/installed.stderr" >&2; fail 'sandboxed positive path refused'; }
summary="$installed/summary.txt"
[[ -f "$summary" ]] || fail 'positive path wrote no summary.txt'
for line in \
  "candidate_sha=$good_sha" \
  "upstream_sha=$upstream" \
  'root_source=/dev/sda2' \
  'root_fstype=ext4' \
  'boot_mode=uefi' \
  'collector=pass' \
  'physical_install_claim=not_automatic'; do
  grep -Fqx "$line" "$summary" || fail "summary missing line: $line"
done
grep -q '^root_backing_disk=' "$summary" || fail 'summary missing root_backing_disk'
[[ "$(tail -n1 "$summary")" == 'physical_install_claim=not_automatic' ]] || fail 'physical claim guard is not the final summary line'
pass 'sandboxed positive path writes a bound summary'

printf 'hardware-installed-evidence contract: PASS\n'
