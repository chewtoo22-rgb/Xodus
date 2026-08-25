# Installer Safety Gate

Xodus currently pins pearOS Installer commit `e676698b4a07f797a50fd25241a738ead75248e6` for audit purposes only.

The audited installer is explicitly whole-disk destructive. Its setup path unmounts target partitions, runs `wipefs -a` on the selected disk, creates a new partition table, repartitions the device, and formats the new root filesystem. Upstream also labels the installer work-in-progress.

## Current release policy

- Physical M0 testing is live-boot-only.
- Do not install to a data-bearing disk.
- Changes to the pinned installer revision must pass `Installer Safety Contract` and receive an explicit audit.
- A physical installation candidate is not allowed until CI performs the destructive path against a newly-created disposable virtual disk and then proves that disk boots under UEFI without the ISO attached.

## Next gate

The VM installation gate must:

1. create a uniquely named disposable qcow2 target inside the CI job;
2. boot the exact qualified Xodus ISO under OVMF;
3. ensure the installer sees only the disposable target as writable test storage;
4. execute installation without relying on a human clicking an ambiguous disk selector;
5. shut the VM down and detach the ISO;
6. boot the installed qcow2 under OVMF;
7. verify kernel/userspace startup and capture serial/journal evidence;
8. delete the qcow2 after artifact/evidence handling.

Until that exists and passes, the hardware runbook's no-install boundary remains mandatory.
