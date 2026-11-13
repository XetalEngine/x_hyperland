# Ventoy USB

Open **Control Panel → Files & recovery → Ventoy USB**. This is Hyper Fusion's
native, themed interface to the unmodified official **Ventoy 1.1.18** Linux
engine. The engine is bundled; creating and updating USB disks works offline.
No separately installed Ventoy app, AUR helper, download on first use, or root GUI
is required.

1. Connect a USB disk and choose its model, capacity and device path.
2. For a new disk, choose **Create Ventoy USB…**. Type the exact device path and
   acknowledge that **every partition and file on that disk will be erased**.
   Administrator authentication follows this confirmation.
3. Keep the USB connected until the operation completes. The progress indicator
   shows that work is ongoing; the log contains the engine's actual output.
4. Choose **Open in Fusion Files** and copy ISO files onto the USB's data
   partition. Multiple images can coexist; choose one from Ventoy's boot menu.

**Update Ventoy…** updates an existing Ventoy disk without reformatting its data
partition. Its partition style and Secure Boot setting are preserved. An engine
newer than the bundled version is never downgraded. A disk without a verified
Ventoy installation cannot be updated; the helper never falls back to an install.

New disks default to **MBR** and **Secure Boot support enabled**. GPT is available
and selected for disks larger than 2 TiB. Some firmware requires enrolling
Ventoy's key at the USB's first Secure Boot startup. See the
[upstream Secure Boot guide](https://www.ventoy.net/en/doc_secure.html).

Only whole USB disks are eligible, including USB SSDs that do not set the
removable bit. Internal disks, active system/boot/swap disks, disks backing loop
images, active mapper/RAID/LVM members, read-only media and 4Kn devices are
blocked. Custom mount locations outside `/media`, `/run/media` and `/mnt` must
be unmounted manually first. Data mounts are unmounted normally; busy mounts
stop the operation. There is no force-install, lazy unmount or swapoff option.

The root helper rechecks device identity (including the kernel attachment
sequence), the partition snapshot and system usage after authentication and
again after unmounting. Disconnecting and replacing a drive invalidates the
confirmation, even when Linux reuses its `/dev` name. Closing an abandoned
authentication request cannot start a write. Once writing begins, the helper
finishes even if its output pipe closes; the normal close button is blocked
until completion. Logs can be saved from the page.

## Bundle and distribution

`vendor/ventoy-1.1.18-linux.tar.gz` is the complete, unchanged upstream release:

- [Official release](https://github.com/ventoy/Ventoy/releases/tag/v1.1.18)
- [Linux archive](https://github.com/ventoy/Ventoy/releases/download/v1.1.18/ventoy-1.1.18-linux.tar.gz)
- [Upstream checksums](https://github.com/ventoy/Ventoy/releases/download/v1.1.18/sha256.txt)
- Size: **20,320,548 bytes**, approximately **20.3 MB** added to the desktop download,
  plus the small integration and license files. The unpacked engine is about
  24 MB and is extracted only into a temporary directory for an operation.
- SHA-256: `d86ff9de63d94c8b8f1f6b14d23c55af4b88e8207bf2893890892a6a97b1ad54`

The checksum and version are pinned in `../ventoy.py` and recorded in the root
asset manifest. The privileged helper copies the archive into a private working
directory, verifies those exact bytes, checks extraction paths and file types,
and runs the engine there with a fixed system PATH. No persistent engine cache,
network download, standalone WebUI or additional system service is started.

Ventoy's own code is GPL-3.0-or-later; included third-party projects retain their
own licenses. See the full upstream notices in [`vendor/License`](vendor/License)
and the [license overview](https://www.ventoy.net/en/doc_license.html).
The notice files were obtained from the supplied upstream source archive at
revision `74cff34240dca6991b79c6656770670da7b0c39e`; this newer development archive
is **not** used as the executable engine or represented as the release source.

**Corresponding release source is available separately, at no charge:**
[Ventoy v1.1.18 source archive](https://github.com/ventoy/Ventoy/archive/refs/tags/v1.1.18.tar.gz)
([browse the tagged source and build scripts](https://github.com/ventoy/Ventoy/tree/v1.1.18)).
The source archive stays separate from the runtime download. Component notices
identify the incorporated projects and their sources; these licenses are not
replaced by Hyper Fusion's top-level license. Release maintainers must keep
these source directions and notices with redistributions.

Setup supplies `parted`, `xzcat` and `hexdump` on Arch, Fedora and Debian, alongside
the existing Python, util-linux, udev, UDisks and PolicyKit dependencies. The
page reports a missing/corrupt bundle or missing tools before enabling writes.
The archive and notices are release-owned profile files and travel through the
normal installer and desktop updater.

## Verification

```sh
python3 -m unittest discover -s tests -p test_ventoy.py -v
cmake -S config/hypr/control_panel/backend -B config/hypr/control_panel/.build -DBUILD_VENTOY_TESTS=ON
cmake --build config/hypr/control_panel/.build --target ventoy_tests CachyOsTools
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= ctest --test-dir config/hypr/control_panel/.build -R '^ventoy$' --output-on-failure
```

Tests cover device replacement, protected disks, missing/corrupt bundles,
partition changes, update flags, unmount failure, cancelled authentication,
confirmation gating and status feedback. The native tests use a fake helper;
Python operation tests mock privileged execution. Tests do not format physical
disks. Hardware installation and firmware boot compatibility require a spare
USB and the target PC.
