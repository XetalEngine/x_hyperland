# KVM Settings

Open **Apps → KVM**, between Control Panel and Fusion Settings. The chip icon opens a large, floating, maximized window. It follows the active desktop colors, controls and dialogs; maximize restores its smaller size. Clicking KVM again focuses the existing window. Clicking X saves the setup and closes immediately, without a confirmation. Unapplied OpenCore edits are retained as a draft; closing never applies boot-file changes. A component install already in progress finishes in the background. Dialogs remain compact; only the main window starts maximized. It closes with the Hyprland session.

The integrated editor retains vmstart_2's Windows and Apple profiles: Single GPU, Virtual GPU, Dual GPU, CPU pinning and features, memory, disks, PCI/USB, machine/network, SMBIOS, TPM, Mac/OpenCore, boot arguments, launch hooks, command preview and saved presets. The original development checkout is not used at runtime.

## First setup

1. Select Windows or Mac. Each has its own captured vmstart_2 baseline and saved configuration.
2. **Downloads** is the first wizard page. Compatible bundled packages install offline; **Install / download missing** fetches anything absent. Component paths are filled in even before installation.
3. Review the detected Intel/AMD processor and IOMMU state. On GRUB systems, **Apply** previews kernel parameters and asks for administrator access. It backs up the defaults and generated boot menu, detects concurrent edits, and restores both if generation fails. Reboot is required for changed boot parameters. Other bootloaders show manual instructions.
4. Review memory, CPU allocation, GPU, USB devices and disks. The baseline preserves the author's current options. The wizard adapts hardware placement to the recipient and retains existing device options when choices are unchanged. Disk selection can be skipped; OpenCore, firmware and support media are retained.
5. Finish to save the profile, then choose a launch mode. The configured Mac OpenCore boot image and shared-store driver ISO are included. Guest operating-system disks and installation media are supplied by the user.

Administrator access is requested when launching a VM. No permanent passwordless-sudo rule is installed. Single GPU can detach the host graphics card and end the desktop; its existing confirmation and recovery hooks remain part of that workflow.

## Components and updates

**Paths & Tools → KVM components** lists installed and available versions, compatibility, and individual Download/Update buttons. Downloads use the [community release service](https://www.xetal.net/community/site/kvm.php). A check does not replace components automatically. Hover over an available version for compressed and installed sizes; **Open components** opens the downloaded files.

The desktop ships compressed QEMU, OVMF, TPM, OpenCore, Looking Glass and the current AMD KVM module. First opening installs compatible bundled packages offline. QEMU is built for generic x86-64, with the custom features retained. The publisher and server accept only these six runtime components: no QEMU, EDK II, kernel, TPM or Looking Glass source trees are shipped.

The captured Windows baseline enables the custom KVM module. It requires the exact published kernel release and an AMD CPU; the wizard switches to standard host KVM for an incompatible CPU/kernel. Downloading a module does not load it. Selecting the managed module in Paths & Tools validates compatibility before launch, then uses the existing idle-VM checks and rollback loader.

Updates verify the pinned RSA signature, archive size and SHA-256 before bounded extraction. Each component installs into a new version directory and becomes current by an atomic symlink switch. Failed downloads or extraction leave the previous component active. Previous versions remain available on disk. Updates and profile changes are blocked while they would interfere with an active component operation or guest.

## Private data and builds

All writable VM settings live in `~/.local/share/xetal-kvm/`, with a separate `macos/` profile. Components are under `components/<name>/current`. Guest NVRAM is copied from the firmware template once and is never replaced by a component update. TPM identity, state, local certificate authority, presets and disks are not part of the theme or desktop update.

The captured SMBIOS binary/template, 12 AML tables, GPU ROMs, public TPM identity properties and separate Windows/Mac NVRAM seeds are included under `kvm/defaults/assets/`. They are copied into the private workspace once. The configured OpenCore image is likewise copied out of its runtime package before editing. Updates never overwrite those writable copies. `defaults/manifest.json` records the captured profile and asset hashes.

TPM runtime helper scripts are seeded into `tpm-workspace/` without replacing existing edits or identity. Source-dependent rebuilds are optional: provide your own local source/build paths in the editor. The published runtime packages need no compilation. No TPM state, libvirt encryption keys, guest system disks or private publisher keys are included. Matching Looking Glass guest components are still required.

## Development and verification

`config/hypr/kvm/backend/ORIGIN.json` records the imported vmstart_2 revision. The publisher and private signing key live only on the development machine, outside this desktop repository. The publisher creates independently versioned `.tar.xz` archives with maximum xz compression and uses signed, resumable uploads with an atomic release commit.

Run the offline package/boot-edit tests from `config/hypr/kvm` with `python3 -m unittest test_packages test_boot test_activity -v`. `QT_QPA_PLATFORM=offscreen python3 app.py --smoke-dir /tmp/kvm-smoke` opens all Windows and Mac pages using isolated settings and captures screenshots. The backend's original pytest suite also includes real VM and network integration tests; those are separate from the desktop test runner.

Validation covers signed package handling, corruption and traversal rejection, interrupted installs/uploads, kernel/CPU gates, guest NVRAM preservation, rollback of synthetic GRUB files, complete UI navigation, and relocated executable probes. Actual guest booting, physical GPU passthrough and live GRUB/module changes require testing on the intended host.
