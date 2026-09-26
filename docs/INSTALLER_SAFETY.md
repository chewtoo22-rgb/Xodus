# Installer Safety Gate

Xodus pins pearOS Installer commit `e676698b4a07f797a50fd25241a738ead75248e6` and audits the `system_install/setup` blob before preparing the Xodus-qualified copy used in the destructive VM gate.

The audited installer is explicitly whole-disk destructive. Its setup path unmounts target partitions, runs `wipefs -a` on the selected disk, creates a new partition table, repartitions the device, and formats the new root filesystem. Upstream also labels the installer work-in-progress.

## Current release policy

- M0 physical testing, when the live-image gate is green, is live-boot-only.
- Do not install to a data-bearing disk.
- Changes to the pinned installer revision must pass `Installer Safety Contract` and receive an explicit audit.
- Every automated destructive installer target must first pass `scripts/installer-target-guard.sh`.
- The destructive VM gate exists and has historical green evidence on an expendable disk. It must be rerun for the intended candidate; it does not authorize physical installation by itself.
- A physical installation trial also requires a successful live-hardware checklist, an empty dedicated disk, explicit human opt-in, and a verified recovery/rollback procedure. That recovery/rollback gate remains open.

## Disposable target guard

`installer-target-guard.sh` is a read-only, fail-closed preflight placed in front of the destructive installer runner. It rejects:

- regular files and partitions instead of whole devices;
- any target or child partition that is mounted;
- the device backing the currently running root filesystem;
- targets smaller than 20 GiB;
- devices without an exact path confirmation;
- loop devices that are not explicitly marked disposable or whose backing files are outside approved temporary paths;
- physical disks unless a separate deliberate physical-install opt-in is present.

The `Installer Target Guard` workflow creates a sparse temporary image, attaches it as a loop device, proves unsafe invocation modes are rejected, proves the marked disposable target is accepted, then mounts that target and proves the guard rejects it again.

## Installer VM rehearsal

`qa/installer-vm-rehearsal.sh` checks the non-destructive VM topology separately from the destructive install test. The `Installer VM Rehearsal` workflow:

1. resolves a proven Core ISO build and independently verifies its packaged SHA-256;
2. creates a fresh 32 GiB qcow2 target in runner-temporary storage;
3. boots the exact ISO under OVMF/UEFI with that expendable disk attached as the only writable installation target;
4. keeps the VM alive through a watchdog window and captures serial, firmware, ISO, and virtual-disk evidence;
5. records `installer_invoked=no` explicitly so a green rehearsal can never be confused with proof of installation.

This checks the disposable-disk topology without weakening the physical live-boot-only policy. A rehearsal pass means the ISO stays bootable with that topology; it does **not** prove installation or authorize physical installation.

## Deterministic installer driver contract

The destructive VM test does not drive the Electron disk selector. Xodus pins both the installer commit and the Git blob for `system_install/setup`, then `scripts/audit-installer-driver.sh` proves the machine-facing contract before direct invocation:

- the whole-disk target is assigned from positional argument `$1`;
- that assignment occurs before the first destructive `wipefs` boundary;
- GPT creation, `sgdisk`, and `partprobe` continue to operate on that same `$DISK` value;
- the new root filesystem is mounted at `/mnt`;
- installer progress remains observable through `/tmp/progress`.

`Installer Driver Contract` CI re-fetches the exact pinned commit, verifies the `system_install/setup` blob SHA, syntax-checks the entrypoint, and fails closed if any required target semantics drift. `Destructive VM Install Gate` then prepares the qualified Xodus payload handoff, uses the exact guarded device path, and captures installer and installed-disk evidence.

## Destructive VM proof and remaining gate

`Destructive VM Install Gate` is designed to:

1. create a uniquely named disposable qcow2/raw target inside the CI job and pass its exposed block device through the target guard;
2. boot the exact qualified Xodus ISO under OVMF;
3. ensure the installer sees only the disposable target as writable test storage;
4. invoke the audited, Xodus-qualified `system_install/setup <exact-device>` entrypoint only after its blob and driver contract pass;
5. shut the VM down and detach the ISO;
6. boot the installed target under OVMF;
7. verify installed payload, kernel/userspace startup, and capture serial/journal evidence;
8. delete the disposable target after artifact/evidence handling.

A current passing run is required before considering an installation candidate. Even then, the hardware runbook's no-install boundary remains in force until the separate live-hardware, target-disk, and recovery/rollback requirements are satisfied. VM success is not physical NUC/SATA proof.
