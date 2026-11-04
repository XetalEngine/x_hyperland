# KVM Settings

Open **Apps → KVM**, between Control Panel and Fusion Settings. The chip icon opens a centered, floating 1820 × 920 window, reduced when necessary to fit the screen. It follows the active desktop colors, controls and dialogs; maximize and restore remain available. Clicking KVM again focuses the existing window. Clicking X saves the setup and closes immediately, without a confirmation. Unapplied OpenCore edits are retained as a draft; closing never applies boot-file changes. A component install already in progress finishes in the background. Dialogs remain compact. It closes with the Hyprland session.

The integrated editor retains vmstart_2's Windows and Apple profiles: Single GPU, Virtual GPU, Dual GPU, CPU pinning and features, memory, disks, PCI/USB, machine/network, SMBIOS, TPM, Mac/OpenCore, boot arguments, launch hooks, command preview and saved presets. The original development checkout is not used at runtime.

## First setup

1. Select Windows or Mac. Each has its own captured vmstart_2 baseline and saved configuration.
2. **Downloads** is the first wizard page. **Install / download missing** fetches the compatible components. No KVM binaries are included in the desktop download. Component paths are filled in even before installation.
3. Review the detected Intel/AMD processor and IOMMU state. On GRUB systems, **Apply** previews kernel parameters and asks for administrator access. It backs up the defaults and generated boot menu, detects concurrent edits, and restores both if generation fails. Reboot is required for changed boot parameters. Other bootloaders show manual instructions.
4. Review memory, CPU allocation, GPU, USB devices and disks. The baseline preserves the author's tuning, with no assigned host disks, PCI devices or USB passthrough devices. The wizard adapts hardware placement to the recipient and retains existing device options when choices are unchanged. Disk selection can be skipped; OpenCore, firmware and support media are retained. The wizard is opened from the top button. Its vBIOS field starts empty: use **Browse** for an existing ROM or **AutoDump** to read and validate the selected GPU's ROM with administrator access. AutoDump strips any pre-header and fills the private file path; Next assigns it only to the graphics function. Failed reads show recovery instructions. The PCI/USB and Dual GPU pages also share this dumper.
5. Finish to save the profile, then choose a launch mode. The configured Mac OpenCore boot image and shared-store driver ISO are downloaded with the components. Guest operating-system disks and installation media are supplied by the user.

Administrator access is requested when launching a VM. No permanent passwordless-sudo rule is installed. Single GPU can detach the host graphics card and end the desktop; its existing confirmation and recovery hooks remain part of that workflow.

After a **Virtual GPU** or **Dual GPU** launch reports that the guest is running,
KVM Settings minimizes itself once. The viewer stays open. Failed starts or
viewer-launch errors leave Settings visible, and restoring Settings does not
minimize it again. **Super+Ctrl+Z** hides or shows the minimized effects while
apps keep running; the taskbar icons can still restore them.

Virtual GPU and Dual GPU open their console/viewer as a floating window by default. The **Floating** checkbox beside the launch-page preview/setup buttons saves separately for each mode and profile; uncheck it to tile newly opened screens. It also applies to SPICE, VNC and Looking Glass opened while a guest is running. The rule belongs only to that viewer launch.

**Machine & network → Create Bridge** appears when the selected host bridge is missing. One click selects the connected Ethernet adapter, requests administrator authentication, preserves its IP/DNS settings, and selects the new bridge for the guest. NetworkManager checkpoints recover the original connection if setup fails; the original Ethernet profile is retained. Existing bridges are reused. Ambiguous, Wi-Fi-only or complex enterprise connections explain the alternative instead of guessing. **NAT — share the host connection** works without a bridge, including on Wi-Fi. The wizard offers both choices at Finish and defaults to NAT when the baseline bridge is unavailable. Host network changes are blocked while a guest is running.

Single GPU saves the selected devices' original drivers before handoff and restores them after a failed start, including a device left unbound. It ends the initiating graphical login and refuses handoff while another graphical user session is active. The launch service preserves the recipient's private workspace path for all three modes; Mac helpers run from the installed source directory. Failed starts and termination signals clean up the supervisor's owned processes before restoring the host.

## Components and updates

**Paths & Tools → KVM components** offers **Basic free**, **Enhanced free** (build 1963), and a disabled Xetallic MAX placeholder. Basic is the fresh-install default and needs no account or installation token. It includes upstream QEMU/OVMF and uses system KVM. Enhanced is free with an active Echo account; MAX is coming soon and reserves NOS MAX eligibility. The **Switch to Basic** and **Switch to Enhanced** buttons prepare missing components before selecting the edition; a failed download leaves the current selection intact. Each edition has its own signed feed, installed versions and download cache. Switching remaps managed tools and read-only firmware while retaining disks, NVRAM, TPM state and guest identity. Custom paths survive ordinary refreshes; explicitly choosing an edition selects its QEMU/OVMF pair. The internal feed identifiers remain `stock` and `xetallic`.

Downloads use the [community release service](https://www.xetal.net/community/site/kvm.php). A check does not replace components automatically. Xetallic's first download retains the existing installation-registration flow. Its launch additionally resumes the Echo session on the authoritative server; banned, suspended, expired or revoked accounts cannot start a new VM. Remember me uses the system password wallet; without a wallet, sign-in lasts for the Settings session. Hover over an available version for compressed and installed sizes; **Open components** opens the selected edition's files.

The desktop contains signed download metadata and the editor, with no KVM executables, firmware, disk images or compressed runtime archives. QEMU, OVMF, TPM, OpenCore, Looking Glass, the current AMD KVM module and baseline support files download only when requested in KVM Settings. Missing components make Paths & Tools pulse red. QEMU is built for generic x86-64, with the custom features retained. The publisher and server accept only these seven runtime components: no QEMU, EDK II, kernel, TPM or Looking Glass source trees are shipped.

**Paths & Tools also pulses red when an installed component has a newer compatible release.** Its tooltip and page banner name the components and show installed → available versions. Checks run when KVM Settings opens, including while a VM is running, or through **Check for updates**. Previously verified release metadata supplies the notice while offline. Each update notice clears when that component is updated; unrelated diagnostics remain. Missing optional components, older releases and builds for another CPU/kernel do not count as available updates. These notices do not block launching a VM or install anything automatically.

Use the documented `git clone --depth 1` install command to avoid fetching past bundles. Older Git history still contains earlier binary releases; removing files from the current checkout does not erase that history.

Stock disables the custom KVM module. Xetallic exposes it as an optional choice, requiring an AMD CPU and the exact published kernel release. Downloading does not load it. Before loading, the helper checks compatibility, authenticated image integrity and both module vermagic values, then retains the existing idle-VM checks and rollback loader. This edition loads modules for the current boot only; persistent installation is rejected. Selecting Stock unloads an idle custom module before restoring the system module. A distribution module that was previously overwritten by an older manual install must first be restored; no kernel package is changed automatically.

When the published module is enabled, its normal load action works in all three
launch modes. Virtual GPU and Dual GPU use the same loader before preparing the
guest; they continue to skip Single GPU's display teardown and other shell hooks.

**Paths & Tools → Guest script** includes the Windows batch template on every supported desktop build, including ZIP installs, before any KVM components are downloaded. Preview it and use **Copy**, save it as a `.bat` file inside Windows, and set `HOST_LOGIN` to your Linux SSH account and a host address reachable from the guest. Adjust `HOST_PORT`, helper/socket paths and `GUEST_NAME` if you changed the defaults. Running it still requires Windows OpenSSH Client, a working host SSH connection, and the matching custom AMD module and host helper; it is unnecessary for standard system KVM. It runs only when you choose to run it after Windows reaches the desktop. Existing custom guest-script selections are preserved; the former managed module path moves to the included template.

Updates verify the pinned RSA signature, archive size and SHA-256 before bounded extraction. Each component installs into a new version directory and becomes current by an atomic symlink switch. Failed downloads or extraction leave the previous component active. Previous versions remain available on disk. Updates and profile changes are blocked while they would interfere with an active component operation or guest.

## Private data and builds

All writable VM settings live in `~/.local/share/xetal-kvm/`, with a separate `macos/` profile. Components are under `editions/<stock|xetallic>/components/<name>/current`; `edition.json` remembers the selection. Each launch pins that selection in its service environment. An existing pre-edition installation is adopted as Enhanced, preserving its component directories through compatibility links. Guest NVRAM is copied once and is never replaced by an edition switch or update. TPM identity, state, local certificate authority, presets and disks are not part of the theme or desktop update.

The captured SMBIOS binary/template, 12 AML tables, GPU ROMs, public TPM identity properties and separate Windows/Mac NVRAM seeds arrive in the baseline support package. They are copied into the private workspace once. The configured OpenCore image is likewise copied out of its runtime package before editing. Updates never overwrite those writable copies. `defaults/manifest.json` records the captured profile and asset hashes.

Pages with invalid settings pulse red and show their reasons. **TPM → Install / initialize TPM** downloads missing tools and creates keys/certificates only for an empty private state directory. Existing keys are preserved; replacement remains an explicit operation. Checks inspect a disposable copy of the NV state, leaving the live state alone. The local CA does not supply hardware-vendor attestation.

The TPM page opens with eight choices: copy the host's public identity, generate an identity, use the published build, use the physical TPM, or apply AMD, Intel, Infineon and STMicroelectronics presets. Each action prepares, verifies and saves the selection for the next VM start. Identity changes use a separate runtime and new guest state; **Undo last TPM change** restores the previous selection without deleting its keys. Encrypted guests may require recovery after changing TPMs. Advanced fields and diagnostics remain available behind **Advanced settings** and **Details**. Host identity copying never copies private hardware keys or writes to the host TPM; physical passthrough is a separate explicit choice.

Custom identities require the recipient's local TPM builder, configured in Paths & Tools; unavailable choices explain the missing capability. The developer workstation uses its private builder. Builds run in the background into a new private prefix, restore the builder's identity inputs, and verify the properties actually reported by the resulting TPM before activation. Published binaries still ship without source trees, and the published TPM option needs no builder.

TPM runtime helper scripts are seeded into `tpm-workspace/` without replacing existing edits or identity. Source-dependent rebuilds are optional: provide your own local source/build paths in the editor. The published runtime packages need no compilation. Setup installs the native compilers, autotools, development libraries, hardware utilities, TPM tools, OpenCore disk tools and remote viewer; it does not supply private custom source checkouts. No TPM state, libvirt encryption keys, guest system disks or private publisher keys are included. Matching Looking Glass guest components are still required.

## Development and verification

### Edition runtime (November 4, 2026)

The edition cards are shared in `edition_ui.py`; the active client connects them
to component preparation and saved edition selection. Install the full runtime
together: the former presentation-only cards cannot launch the newer packages.
At startup `edition_migration.py` adopts an existing component installation as
Enhanced, verifies runtime metadata against signed catalogs, and repairs the
QEMU placeholder left by the old installer. It retains existing directories and
cached downloads, never opens guest disks, and does not rewrite saved profiles.
The migration is idempotent and resumable; new installs still default to Basic.
The updated module preflight validates the installed runtime images without
looking for plaintext `.ko` files or calling `modinfo` on them. No logout is needed
after installing this client; reopening KVM Settings loads the updated runtime.
Virtual/Dual GPU device checks use `runtime_probe.py` after launch authorization:
it holds QEMU in memory and inspects a diskless paused fixture. It loads no custom
module or guest hook, retains the short-lived authorization for the actual launch,
and returns only public capability/PCI data. The GUI caches that data by component
identity; Basic and external QEMU binaries retain their ordinary direct probes.

`editions.py`, `echo_account.py`, `runtime_access.py`, `vm_session.py` and
`vm_memory.py` implement selection, account access and the launch lifetime.
All three launch modes and the integrated test runner enter the supervisor
before host/GPU handoff. A short-lived root-owned kernel key carries the Echo
session across Single GPU desktop teardown; only its serial is stored under
root-owned `/run/xetal-kvm-auth`. It expires after 180 seconds and is revoked
once the launch images are resident. Credentials never enter VM JSON or argv.

The Xetallic publisher packages QEMU's main ELF and both KVM modules with
AES-256-GCM, independent nonces, component/path associated data, and signed
ciphertext hashes. Ciphertext remains cached on disk. HTTPS authorization
returns a content key only after a fresh native Echo Resume. The supervisor
decrypts directly into anonymous memfds, authenticates before use, seals new
writes, and pins the mappings until its child exits. Root-only descriptor
passing gives the QEMU/module wrappers access without a named plaintext file.
The module helper reads bounded ELF metadata directly from the descriptor and
uses `finit_module` with flags zero, retaining the kernel's ABI and signature
checks. It does not depend on `modinfo` accepting anonymous paths.
`mlockall`, per-image `mlock`, disabled core dumps and no disk fallback are
mandatory. Failure stops before hardware handoff. Stock uses normal files.

This is account-gated distribution, not host-owner attestation: root can inspect
memory, and privileged hibernation/kernel dumping is outside the loader's
control. Do not describe it as unextractable or rely on OVMF being unusable with
another QEMU. Existing developer build outputs and older previews are not
deleted. Distribution must retain the upstream license notices and satisfy
QEMU/Linux corresponding-source obligations independently of account access.

The community website adds `api/kvm-session.php` and `lib/kvm_sessions.php`.
It reuses the native Echo PHP bridge's Login/Resume, including current bans,
session revocation and paid `nos_level` (MAX is exactly 2). No Echo database or
server binary modification is required. Its private content-key directory
must be outside the HTTP document root and mode 0700. See the master publisher
README for deployment order. Website source changes do not deploy that endpoint.

Focused offline checks: `python3 -m unittest test_editions test_module_image test_packages
test_runtime_setup test_activity test_network_bridge -v`. The opt-in
`sudo python3 test_memory_runtime.py --offline-fixture` uses a synthetic token
and `/usr/bin/true` only: it tests locked memory, kernel-key permissions,
descriptor passing and execution without networking or loading a module.
Actual signed QEMU artifacts were installed in disposable directories and
checked with `--version`; real VM boots and GPU handoff remain host qualification.

`config/hypr/kvm/backend/ORIGIN.json` records the imported vmstart_2 revision. The publisher and private signing key live only on the development machine, outside this desktop repository. The publisher creates independently versioned `.tar.xz` archives with maximum xz compression and uses signed, resumable uploads with an atomic release commit.

Run the offline package/boot-edit tests from `config/hypr/kvm` with `python3 -m unittest test_packages test_boot test_activity test_runtime_setup test_setup test_network_bridge -v`. `QT_QPA_PLATFORM=offscreen python3 app.py --smoke-dir /tmp/kvm-smoke` opens all Windows and Mac pages using isolated settings and captures screenshots. The backend's original pytest suite also includes real VM and network integration tests; those are separate from the desktop test runner.

Validation covers signed package handling, corruption and traversal rejection, interrupted installs/uploads, kernel/CPU gates, guest NVRAM preservation, rollback of synthetic GRUB files, complete UI navigation, and relocated executable probes. Actual guest booting, physical GPU passthrough and live GRUB/module changes require testing on the intended host.
