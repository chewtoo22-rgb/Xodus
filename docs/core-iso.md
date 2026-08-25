# Xodus Core ISO — M0 Reference Build

## Upstream baseline

Xodus M0 currently pins pearOS `iso` at:

`8175d4851fcf85b2325c56a3751c0697e044d049`

The upstream README documents the reference build entrypoint as:

```sh
sudo ./build-binary
```

Required Arch-side tools are `arch-install-scripts`, `mtools`, `squashfs-tools`, `xorriso`, `e2fsprogs`, `git`, and `pv`. The live image uses prebuilt Ploader artifacts already present under `pear/efiboot/ploader/`; the reference ISO build should not rebuild the bootloader during M0.

## Reproducibility contract

1. CI must checkout the exact SHA in `upstream/iso.lock`, never floating `main`.
2. CI must validate that `build-binary` exists and is executable before attempting a build.
3. Generated upstream source, work directories, and ISO artifacts remain outside tracked source.
4. The first successful artifact is intentionally an unmodified pearOS reference ISO. Xodus identity overlays are applied only after the reference build is reproducible.
5. Each candidate artifact must ship with SHA-256 output and retained build logs.

## M0 sequence

- [x] Pin current upstream ISO commit.
- [x] Record upstream build dependencies and entrypoint.
- [ ] Prove the pinned source contract in GitHub Actions.
- [ ] Run a full Arch-native reference ISO build in CI.
- [ ] Upload ISO, checksum, and logs as artifacts.
- [ ] Hand artifact to the QA lane for QEMU/OVMF boot smoke testing.

## CI host constraint

The upstream builder is Arch-native and requires root/chroot operations. Standard Ubuntu GitHub-hosted runners are therefore suitable for source-contract validation but are not treated as the final reference build environment. The full builder should run in an Arch container/VM path with the privileges required by `pacstrap`, `arch-chroot`, filesystem image creation, and loop/mount operations, or on a self-hosted Arch runner if GitHub-hosted container privileges prove insufficient.
