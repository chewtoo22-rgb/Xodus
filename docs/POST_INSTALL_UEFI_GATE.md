# Post-install UEFI gate

Physical installation stays locked until a disposable VM install passes this independent verifier.

`qa/post-install-uefi-smoke.sh <installed-disk.qcow2> <output-dir>` consumes the disk produced by the destructive installer test. It does **not** attach the installer ISO.

A candidate installed disk passes only when all of the following are true:

1. The image is qcow2 or raw and exposes a GPT with both an EFI System Partition and Linux filesystem partition.
2. The EFI System Partition contains at least one `.efi` executable.
3. The Linux root contains `/etc/os-release` and a usable init implementation.
4. The verifier injects a CI-only systemd sentinel into the installed root.
5. The disk boots by itself under OVMF/UEFI QEMU.
6. Installed userspace reaches `multi-user.target` and emits `XODUS_POSTINSTALL_BOOT_OK` over the emulated serial port.

Merely keeping QEMU alive until a watchdog expires is intentionally insufficient: firmware can idle forever with a broken or absent bootloader.

The output directory captures the partition table, block layout, EFI executable list, installed OS metadata, QEMU log, serial log, UEFI variable store, and machine-readable post-install evidence.

## Safety boundary

The verifier is for expendable VM disks produced by CI. It is not permission to run the upstream whole-disk installer on physical storage. Hardware install remains locked until the complete chain is automated and green:

`qualified ISO -> guarded disposable disk -> pinned installer -> detach ISO -> post-install UEFI userspace sentinel`
