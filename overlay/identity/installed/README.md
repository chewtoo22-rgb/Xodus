# Retaining the Xodus graphical identity after installation

The online installer installs packages into a new root. Copying identity files
into the live ISO therefore does not preserve Welcome, Settings, the shell,
login, wallpaper or boot animation on the installed system. These helpers copy
only reviewed graphical payloads after the upstream packages have settled.

## Build order

Run the normal live root customization first, including the source-built
Welcome and Settings apps and the visible and shell identity helpers. The
installer frontend identity helper must run against the unmodified protected
scripts before installer derivation. Then:

1. Install `identity-payload.py` as
   `/usr/lib/xodus/xodus-identity-payload` and `restore-user-identity.py` as
   `/usr/lib/xodus/xodus-restore-user-identity`, both with mode `0755`.
2. Run `derive-installer-identity.py --apply-installer <live-root>/usr/share/pearOS-installer
   --original-root <audited-installer-checkout> --source-commit <Xodus-SHA>
   --build-info <live-root>/usr/lib/xodus/build-info`.
3. Run `identity-payload.py capture <live-root>` as the final graphical payload
   step, before the package list and SquashFS are made.

The audited original checkout must be at installer commit
`e676698b4a07f797a50fd25241a738ead75248e6` with protected working files byte-identical
to their Git blobs. Use a Linux checkout with LF bytes. Frontend-only changes do
not change the protected setup or post-setup files.

The original `upstream/installer.lock` stays unchanged. The derived scripts have
a separate receipt, `xodus-installed-identity.json`, in the installer directory.
Verification reconstructs their exact expected bytes from the audited original
Git blobs and checked-out Xodus derivation code. Changing a script and updating
the receipt hash is rejected.

## Installer order

The deterministic setup changes add four graphical operations:

1. Verify the live identity manifest before the original keymap operation and
   disk wipe. A changed live payload fails before destructive work starts.
2. Copy the Xodus boot theme before the first installed `mkinitcpio` operation.
   Preserve existing target hooks in order, adding Plymouth after display setup.
   Select `xodus` and rebuild the initramfs at the existing Plymouth step. Failure
   to build or select the theme aborts installation.
3. Select the Xodus GRUB theme at the existing theme configuration step.
4. Copy the full graphical payload after the final package cleanup, before the
   success notification and reboot. Check both compiled apps with target-root
   `ldd` and offscreen rendering. A failed ABI/render check prevents a success
   receipt and aborts installation.

The source capture uses a closed path list. It excludes live-user state,
autologin, machine IDs, hostname, account policy, credentials and build-info.
Existing installed-user homes receive only reviewed skeleton identity files.
The installed OS metadata uses the reviewed live `/usr/lib/os-release`; a valid
existing `/etc/os-release` link is preserved, an independent regular file is
rewritten consistently, and an absent link is created relative to the target.
Other link destinations are rejected.

Full transfer removes conflicting `Current=` selections only from `[Theme]`
sections in the target SDDM configuration, preserving other lines and sections,
including the existing account and autologin settings. The reviewed Xodus
selection then applies consistently. Unsafe configuration paths are rejected.

No helper partitions disks, creates accounts, installs drivers or enables
services. Every original setup/post-setup disk, account and driver command is
unchanged. The post-setup script retains upstream account lockdown, sudoers
checks and removal of the temporary default user.

## First login

Upstream post-setup schedules its theme switcher for the new user's first real
Plasma session. The derived heredoc invokes the Xodus restore helper immediately
after that switcher, then removes the original one-time entry even if restoration
fails, preserving the command's failure status. The helper checks
skeleton bytes against the installed receipt, restores only those graphical
defaults and applies the Xodus color scheme and wallpaper in that user session.
It does not create a recurring autostart entry or overwrite later preferences.

The real session needs `/usr/bin/plasma-apply-colorscheme` and
`/usr/bin/plasma-apply-wallpaperimage`, both provided by the existing
[`plasma-workspace` package](https://archlinux.org/packages/extra/x86_64/plasma-workspace/files/).
The wallpaper CLI calls Plasma's session API, as shown in the
[KDE source](https://github.com/KDE/plasma-workspace/blob/Plasma/6.7/wallpapers/image/plasma-apply-wallpaperimage.cpp).
Disposable roots use `--root <fixture> --home /home/user`;
the fixture mode performs no session or disk operation. The real-root invocation
must run as the user who owns the home, and refuses root.

## Retained ISO gate

Selectively extract these paths from the actual SquashFS:

```text
usr/share/pearOS-installer/system_install/setup
usr/share/pearOS-installer/post-install/post_setup
usr/share/pearOS-installer/xodus-installed-identity.json
usr/lib/xodus/build-info
usr/lib/xodus/xodus-identity-payload
usr/lib/xodus/xodus-restore-user-identity
usr/lib/xodus/identity-payload.json
```

Verify the scripts with:

```sh
python3 overlay/identity/installed/derive-installer-identity.py \
  --verify-installer "$extracted/usr/share/pearOS-installer" \
  --original-root "$fresh_audited_installer_checkout" \
  --source-commit "$qualified_xodus_source_sha" \
  --build-info "$extracted/usr/lib/xodus/build-info"
```

Compare each embedded helper byte-for-byte with the corresponding checked-out
Xodus source and require mode `0755`. Extract the paths named in the identity
manifest and run `identity-payload.py verify --source-root <extracted-root>
--expected-source <qualified-source-SHA>` to check closed inventory and every
payload hash. The extractor should reject unexpected manifest paths before
using them as extraction selectors. The manifest itself does not authorize
changes to installer code.

## Disposable verification

```sh
python3 qa/installed-identity-contract.py --original-root "$fresh_audited_installer_checkout"
```

The tests use temporary directories and inspect shell syntax. They never invoke
the installer scripts. They cover original Git object authority, full script
byte comparison, self-hash tampering, hook order, unchanged disk/account/driver
commands, target/source path escapes, hardlinks, source hashes, executable modes,
ABI failure and one-time restoration. Real installed boot and render evidence
still require the installer VM and installed-system gates.
