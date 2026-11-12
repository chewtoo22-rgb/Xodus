# Xodus installer presentation

The graphical installer uses Xodus white/violet artwork on a near-black background. The derivation covers the English, Czech and Romanian live installer pages, dynamic navigation bar, disk/progress artwork, all post-install translation dictionaries and the first setup wizard. Product names and default hostnames become Xodus; internal compatibility paths and upstream legal authorship remain.

## Sources and ordering

`upstream/installer.lock` remains unchanged. `apply-installer-identity.py INSTALLER_ROOT` validates the frontend inventory and canonical SHA-256 of the locked installer commit `e676698b4a07f797a50fd25241a738ead75248e6`, including setup blob `99046db1958c0f7fe6710f3e7236a6bc2cc4fdde`. It rejects source drift before writing files. Invoke this helper immediately after the verified installer checkout, **before** the installed identity helper derives setup/post_setup hooks from that source.

Protected backend, Electron main process, package metadata, installer entrypoints and post_setup bytes are checked unchanged after frontend transformation. The original legal bodies stay in the active pages; original license presentations and the progress source notice are also retained under `xodus-upstream-notices/`. The generated `xodus-frontend-identity.json` records transformed frontend and protected source hashes. Later setup derivation has its own provenance record.

After packages and customization are installed, invoke `apply-calamares-identity.py LIVE_ROOT`. Its manifest describes the audited `pear-calamares-config` package version `26.8.0-13` (archive SHA-256 `d1eedaa6c3fe269ea92cce97385fe10e5eeeb22451b24391db7559a3afecb980`). The manifest checks exact settings/branding content, independent of the package filename. The helper creates `/etc/calamares/branding/Xodus/` and changes only the settings branding selector. Original package branding and SPDX notices remain available. Installation modules and `launch.sh` are hashed before/after and stay unchanged. The result is recorded in `xodus-calamares-identity.json`.

## Disk Continue correction

The upstream disk page invokes `showEraseModal()`, while `updateContinueButtonState()` searched only for callbacks containing `select_disk`. The frontend derivation recognizes both callbacks and requires a nonempty disk selection. NODISK and `/dev/null` stay rejected. Erase confirmation, cancellation, backend commands, IPC and partition behavior remain unchanged.

## Verification

Run the source contract against a Git checkout containing the locked installer commit and the audited extracted Calamares configuration:

```sh
python3 qa/installer-frontend-identity-contract.py INSTALLER_SOURCE \
  --calamares-root PACKAGE_ROOT/etc/calamares
```

The contract reconstructs the actual pinned source with `git archive`, verifies backend bytes, legal bodies, control callbacks and the narrow renderer patch, and checks that changed frontend/backend/Calamares inputs are rejected without partial writes.

Chromium rendered the real frontend at 1280×800 using review-only Electron filesystem/process substitutes, so no installation or host shell command ran. Language→recovery→online install→agreement→disk→erase confirmation→progress navigation was exercised. The updated disk Continue control was disabled with no selection, enabled for `/dev/vda`, and disabled for selected NODISK. The setup account form stayed disabled while empty and continued after valid matching fields. Failure messages retained red emphasis; account/profile and appearance accents render violet. Screenshot evidence is retained in the task's `work/xodus-installer-review/` directory.

This verifies frontend presentation and mocked interaction. An actual built ISO must still render the Electron application and Calamares, and the installation gates must pass after integration.
