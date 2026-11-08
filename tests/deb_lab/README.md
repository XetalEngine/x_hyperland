# Headless .deb compatibility lab

Run the real HyperFusion installer inside disposable Arch Linux VMs. The host
runner never invokes the host's package manager to install anything. Each app
starts with a fresh qcow2 overlay backed by an immutable, prepared base image.
The guest uses 4 vCPUs and 4 GiB RAM; a batch runs one guest at a time.

The first setup downloads a signed official Arch cloud image, verifies its SHA256
and Arch Boxes signing key, and provisions it using cloud-init. The guest has its
own account and SSH key. QEMU runs as the desktop user with KVM acceleration.
SSH listens on a randomly allocated **127.0.0.1** port. There are no shared host
directories, clipboard devices, agent forwarding, USB or physical-disk passthrough.
Guests have outbound network access for package installation and app startup.

## Using the prepared lab

From the repository root:

```sh
# Test the next few apps without opening a VM window.
python tests/deb_lab/lab.py run obsidian slack zoom

# Run all candidates in apps.json, continuing after individual failures.
python tests/deb_lab/lab.py run --all

# Run only the second batch of ten popular vendor packages.
python tests/deb_lab/lab.py run brave opera spotify steam signal 1password sublime-text anydesk rustdesk cursor

# Focus follow-up work on apps without an enabled native repository package.
python tests/deb_lab/lab.py run opera 1password anydesk

# Test a local download with its normal application command.
python tests/deb_lab/lab.py run-file /path/to/example_amd64.deb --id example --command example

# Rebuild the combined Markdown and JSON reports.
python tests/deb_lab/lab.py report
```

Results, complete installer logs, application output, package inventories, VM
boot logs and screenshots are stored under the lab storage directory. Every run
records the .deb hash, source URL, version, installer source hashes and baseline.
`RESULTS.md` and `results.json` combine all runs. Failed test disks are retained
for diagnosis; successful test disks are retained too. Nothing is published.
The Markdown report shows the latest result for each app; the JSON retains the
full run history. A completed batch returns exit status 1 if any candidate fails,
but still attempts every selected app. Ctrl+C stops the current lab guest.

The candidate list is a selection of widely used applications with official
vendor `.deb` downloads, not a verified cross-vendor download ranking. Repository
URLs and hashes come from the vendors' package indexes, GitHub release assets,
or official download pages. The Cursor URL currently selects the 3.29 release
listed on its download page; recheck that page when updating the candidate.

For new compatibility work, prefer the native package when one is available in
the user's enabled repositories. On the development system on 2026-11-08 this
means skipping `steam` (Arch multilib), `brave-bin` (CachyOS), and
[`spotify-launcher`](https://archlinux.org/packages/extra/x86_64/spotify-launcher/)
(Arch extra). The latter manages Spotify's vendor client rather than repackaging
it with this installer. Check availability with `pacman -Si` before choosing a
batch; configured repositories differ across installations. The historical
candidates remain in `apps.json` for reproducibility, so `--all` includes them.

The normal installer and guest runner are snapshotted for each test, then copied
into that guest. Those exact source files and their hashes stay with the result.
The harness answers only pacman's ordinary `Proceed with installation? [Y/n]`
confirmation. It does not add `--nodeps`, `--overwrite`, fake dependencies or
disable application sandboxes. Unknown prompts and stalled installers time out.
Conversion temporary files use the guest's disk through `TMPDIR`, avoiding its
small RAM-backed `/tmp` when large packages need multiple unpacked copies.
The production installer still performs conversion, script syntax checks,
dependency/transaction checks, registration and file-preservation checks.

GUI checks use Xvfb and Openbox in a private D-Bus session. A pass requires a
visible window owned by the installed package that survives for at least twelve
seconds. The lab also records a screenshot and verifies package removal.
Apps with `local_login: true` (currently AnyDesk) also receive a real tester
login on the guest's virtual tty1 through PAM/logind. The runner verifies the
active seat's user; it does not spoof user IDs or disable app session checks.
The getty override lives only in the guest's `/run`. AnyDesk's root service is
not enabled for this startup test. Guests shut down cleanly after collection so
Btrfs writes and diagnostic state survive on the retained test disk, including
when SSH disconnects before returning the poweroff command's result.

**A GUI smoke pass is not a full compatibility certification.** A window may
display a login screen or app-specific error. Review its screenshot. This does
not verify accounts, sync, audio/video calls, remote access, GPU acceleration,
upgrades, or Hyprland/Wayland behavior. Existing human-confirmed entries in
`deb_apps.json` are not automatically changed. Failed mappings or scripts remain
failures for review; the runner never patches the installer just to obtain a pass.

After reviewing a startup screenshot, eligible results can be added to the
Control Panel catalog as `status: "launch_tested"`, with the version, ISO test
date and scope in `note`. Do not use the human-reported `tested` status for an
unattended run. A blank window or error dialog must remain under investigation
even if the window-presence check passes. Preserve that finding in the run's
`visual_review` field and mark its status `visual-review-needed`.

## First batch: November 8, 2026

The VS Code 1.145.2 control installed, opened and uninstalled successfully.
Ten additional vendor packages were tested with real Debtap conversion and
pacman transactions. After fixing the verified `libuuid1` → `util-linux-libs`
mapping and two harness launch-detection issues, the reviewed results were:

| Applications | Result |
| --- | --- |
| Obsidian 1.15.0, Bitwarden 2026.9.1, Insomnia 13.4.0 | Installation, visible startup and removal passed; screenshots reviewed. Added as **Launch tested**. |
| DBeaver Community 26.2.4 | Installation and removal passed, but the captured configuration dialog was blank. Needs visual investigation; not added as working. |
| Slack 4.53.276 | Requires application-indicator mapping and treatment of its Debian `apt-transport-https` requirement. |
| Zoom 7.2.5.6661 | Unmapped XCB, OpenGL, session-management and XSLT dependencies. |
| ONLYOFFICE 10.0.0-169 | Unmapped X11, GStreamer and font requirements. |
| Vivaldi 8.3.4191.30-1, Microsoft Edge 157.0.4341.42-1 | Converted Debian installation scripts fail syntax validation; need reviewed Arch recipes. |
| TeamViewer 15.83.3 | Unmapped XCB and PolicyKit requirements. |

Full per-run evidence is in the private NVMe lab's `RESULTS.md`, `results.json`
and `runs/` directory. The failed candidates were stopped by the existing
installer checks. No dependency or transaction checks were disabled.

## Second batch: November 8, 2026

Ten more popular vendor applications were attempted in fresh guests. Signal and
Sublime Text passed installation, a visible normal startup screen, screenshot
review and removal. They were added to the Control Panel as **Launch tested**
with the date **2026-11-08**. Signal pairing/messages/calls and Sublime editing,
plugins and licensing were not exercised; neither was tested on Wayland.

| Application | Version | Result |
| --- | --- | --- |
| Brave | 1.99.55 | Blocked by its Debian `brave-keyring` dependency; requires an Arch recipe. |
| Opera | 139.0.6053.38 | Unmapped Qt 5 requirements and Debian-specific `apt-transport-https`/`debconf` requirements. |
| Spotify | 1:1.2.95.453.g0eeebbed | After the library-mapping fix, dependencies resolve, but the converted `.INSTALL` has an unterminated heredoc. Nothing installed; needs a reviewed Arch recipe. |
| Steam | 1:1.0.0.87 | Unmapped D-Bus/PolicyKit/XZ requirements plus Debian-specific `python3-apt`. The launcher needs an Arch recipe and runtime testing. |
| Signal | 8.34.0 | **Launch tested**: normal phone-linking screen; install and removal verified. |
| 1Password | 8.12.44 | Unmapped `gnupg2`, `libxcb-shape0` and `libxcb-xfixes0`. |
| Sublime Text | 4215 | **Launch tested**: normal unregistered editor; install and removal verified. |
| AnyDesk | 8.1.0 | Unmapped `libgcc1` and `libxcb-shm0`. |
| RustDesk | 1.5.1 | Unmapped XCB, systemd, VA-API, GStreamer and PipeWire requirements. |
| Cursor | 3.29.9-1793846899 | Dependency preflight passes; converted `.INSTALL` has an invalid `elif`. Nothing installed; needs a reviewed Arch recipe. |

This batch added verified shared mappings for `libxshmfence1` → `libxshmfence`
and `libayatana-appindicator3-1` → `libayatana-appindicator`, preserving minimum
versions and ABI boundaries. The official file-list references and regression
fixtures are in the Control Panel documentation and `test_deb_dependencies.py`.
Spotify was rerun from a fresh overlay with that change; both its original
dependency failure and subsequent script-validation failure remain in the logs.
The other eight candidates were **not** added as working or launch tested.

## Recipe follow-up: November 8, 2026

After adding reviewed native recipes and shared dependency mappings, these
vendor packages passed installation, package/file verification, a visible
startup screen and removal in fresh Arch guests. Screenshots were reviewed;
the Control Panel lists them as **Launch tested**, dated **2026-11-08**.

| Application | Version | Reviewed startup | Evidence run |
| --- | --- | --- | --- |
| Opera | 139.0.6053.38 | Normal Speed Dial browser page | `20261108T084809Z-opera` |
| 1Password | 8.12.44 | Welcome/sign-in screen; native helper permissions and target-user policy also verified | `20261108T084959Z-1password` |
| AnyDesk | 8.1.0 | Normal Welcome page with a real tester console login; root service not enabled | `20261108T090304Z-anydesk` |

AnyDesk's first launch exposed an undeclared `libevdev.so.2` requirement; its
recipe now includes the Arch provider. The next attempt exposed a lab issue:
AnyDesk refuses to run as a user different from the active local login, and a
bare SSH/Xvfb environment had no such login. A genuine PAM/logind tester session
on virtual tty1 fixes the fixture without patching AnyDesk or disabling checks.
Remote connections, accounts, browser integration, audio/video and Wayland
remain untested. Normal startup is the scope of these catalog entries.

Steam and Brave follow-up work was skipped because native packages were already
available. Spotify was attempted before discovering Arch's native
`spotify-launcher`; its conversion installed but startup lacked an indicator
library. The provisional Spotify recipe was removed, and no passing `.deb`
claim was added. Prefer the native paths described above.

Reviewed native packaging revisions were Opera
`104daab16df3adcd016979dc7f42f0a8f6ee3995` (archived; current vendor layout checked
separately), 1Password `a01e3b048ebbe341d6e6b500304a315a342a7d84`, and AnyDesk
`61d4ea89d878a844b9d2e71d84388c2662e0fe4d`. Package archive hashes and the exact
installer/harness snapshots are in each private lab result. The tests installed
no applications on the development host.

## Storage on a dedicated NVMe

Control files and private keys live in `~/.local/share/hyperfusion-deb-lab`.
An optional `storage.json` redirects VM disks, downloads and reports to another
filesystem. It contains `mount`, `directory`, `uuid`, and `device`. The runner
checks the mount and filesystem UUID, and fails if the expected storage is absent.
It never silently fills the development-system disk instead.

On this workstation the disposable HyperFusion ext4 partition is mounted at
`~/.local/share/hyperfusion-deb-lab/storage`; the image files live in
`storage/var/lib/hyperfusion-deb-lab`. The disk is mounted `nosuid,nodev,noexec`.
Its original OS files are retained, and its Debtap caches seed the new guest.

**Do not start the old VM that passes through the whole physical drive while
that drive is mounted by the host.** Use the lab's image-based guests. When the
lab is idle, unmount the storage before returning that physical drive to the old
VM. The lab does not change `/etc/fstab`, KVM profiles or host autostart/services.

To restore the mount after reboot, use the `device` and `mount` paths recorded
in the private `storage.json`:

```sh
sudo mount -o nosuid,nodev,noexec /dev/disk/by-uuid/YOUR-RECORDED-UUID /path/to/lab/storage
```

## Preparing another baseline

Host prerequisites: Python 3, QEMU/KVM, qemu-img, SSH/scp, xorriso, curl, GnuPG,
and tar. Run as the normal desktop user. The installer scripts refuse to run as
host root; guest setup and test scripts require a lab marker and matching VM UUID.

```sh
python tests/deb_lab/lab.py init \
  --debtap-package /path/to/reviewed/debtap-version-any.pkg.tar.zst \
  --cache /path/to/existing/var/cache/debtap
```

`--cache` is optional, but seeding real existing databases saves considerable
download time. Native pkgfile indexes are refreshed inside the guest. Missing or
invalid databases fail the production preflight; synthetic lookup fixtures are
not accepted as a replacement for real integration tests. AUR helpers are not
automatically built: dependencies needing one are reported by the installer.

The base is created only after a successful setup and clean guest shutdown, then
flattened and made read-only. Use a new `--state` directory to build a new baseline
for updated Arch libraries; old results retain their baseline information.

Optional private `runtime.json` selects a QEMU binary (`qemu`), firmware directory
(`firmware_directory`), paired UEFI files (`firmware_code`, `firmware_vars`) and
guest CPU options (`cpu`). This workstation uses a signature-verified stock QEMU
extracted from its package cache without replacing the customized system binary.
Guest KVM paravirtualization can be disabled with `host,kvm=off` if required by a
modified host KVM stack; KVM acceleration remains enabled. Record that environment
when interpreting results. Firmware variables are private to each lab guest.

Run the harness boundary checks with:

```sh
python -m unittest discover -s tests/deb_lab -p 'test_*.py'
```

References: [Arch Boxes](https://github.com/archlinux/arch-boxes),
[cloud-init NoCloud](https://docs.cloud-init.io/en/latest/reference/datasources/nocloud.html),
[QEMU networking](https://www.qemu.org/docs/master/system/devices/net.html).
