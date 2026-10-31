# KVM Settings

Open **Apps → KVM**, between Control Panel and Fusion Settings. The chip icon opens a centered, floating 1820 × 920 window, reduced when necessary to fit the screen. It follows the active desktop colors, controls and dialogs; maximize and restore remain available. Clicking KVM again focuses the existing window. Clicking X saves the setup and closes immediately, without a confirmation. Unapplied OpenCore edits are retained as a draft; closing never applies boot-file changes. A component install already in progress finishes in the background. Dialogs remain compact. It closes with the Hyprland session.

The integrated editor retains vmstart_2's Windows and Apple profiles: Single GPU, Virtual GPU, Dual GPU, CPU pinning and features, memory, disks, PCI/USB, machine/network, SMBIOS, TPM, Mac/OpenCore, boot arguments, launch hooks, command preview and saved presets. The original development checkout is not used at runtime.

## First setup

1. Select Windows or Mac. Each has its own captured vmstart_2 baseline and saved configuration.
2. **Downloads** is the first wizard page. **Install / download missing** fetches the compatible components. No KVM binaries are included in the desktop download. Component paths are filled in even before installation.
3. Review the detected Intel/AMD processor and IOMMU state. On GRUB systems, **Apply** previews kernel parameters and asks for administrator access. It backs up the defaults and generated boot menu, detects concurrent edits, and restores both if generation fails. Reboot is required for changed boot parameters. Other bootloaders show manual instructions.
4. Review memory, CPU allocation, GPU, USB devices and disks. The baseline preserves the author's tuning, with no assigned host disks, PCI devices or USB passthrough devices. The wizard adapts hardware placement to the recipient and retains existing device options when choices are unchanged. Disk selection can be skipped; OpenCore, firmware and support media are retained. The wizard is opened from the top button. Adding a GPU reads and validates its ROM with administrator access, then assigns the resulting private file to its graphics function. A supplied ROM takes precedence; failed reads show manual recovery instructions.
5. Finish to save the profile, then choose a launch mode. The configured Mac OpenCore boot image and shared-store driver ISO are downloaded with the components. Guest operating-system disks and installation media are supplied by the user.

Administrator access is requested when launching a VM. No permanent passwordless-sudo rule is installed. Single GPU can detach the host graphics card and end the desktop; its existing confirmation and recovery hooks remain part of that workflow.

## Components and updates

**Paths & Tools → KVM components** lists installed and available versions, compatibility, and individual Download/Update buttons. Downloads use the [community release service](https://www.xetal.net/community/site/kvm.php). A check does not replace components automatically. The first download registers this x_hyperland installation automatically, using a random installation ID and installed revision; the private access token stays in the user workspace. The website lists versions but offers no direct archive links. Anonymous archive URLs are denied. This gates the normal download flow; client registration is not hardware attestation and cannot prevent an installer from copying files. Hover over an available version for compressed and installed sizes; **Open components** opens the downloaded files.

The desktop contains signed download metadata and the editor, with no KVM executables, firmware, disk images or compressed runtime archives. QEMU, OVMF, TPM, OpenCore, Looking Glass, the current AMD KVM module and baseline support files download only when requested in KVM Settings. Missing components make Paths & Tools pulse red. QEMU is built for generic x86-64, with the custom features retained. The publisher and server accept only these seven runtime components: no QEMU, EDK II, kernel, TPM or Looking Glass source trees are shipped.

The captured Windows baseline enables the custom KVM module. It requires the exact published kernel release and an AMD CPU; the wizard switches to standard host KVM for an incompatible CPU/kernel. Downloading a module does not load it. The module helper rejects mismatched CPU/kernel metadata and checks both module vermagic values before invoking any loader. **Use system KVM** disables the custom module when a matching build is unavailable. Selecting the managed module in Paths & Tools validates compatibility before launch, then uses the existing idle-VM checks and rollback loader.

Updates verify the pinned RSA signature, archive size and SHA-256 before bounded extraction. Each component installs into a new version directory and becomes current by an atomic symlink switch. Failed downloads or extraction leave the previous component active. Previous versions remain available on disk. Updates and profile changes are blocked while they would interfere with an active component operation or guest.

## Private data and builds

All writable VM settings live in `~/.local/share/xetal-kvm/`, with a separate `macos/` profile. Components are under `components/<name>/current`. Guest NVRAM is copied from the firmware template once and is never replaced by a component update. TPM identity, state, local certificate authority, presets and disks are not part of the theme or desktop update.

The captured SMBIOS binary/template, 12 AML tables, GPU ROMs, public TPM identity properties and separate Windows/Mac NVRAM seeds arrive in the baseline support package. They are copied into the private workspace once. The configured OpenCore image is likewise copied out of its runtime package before editing. Updates never overwrite those writable copies. `defaults/manifest.json` records the captured profile and asset hashes.

Pages with invalid settings pulse red and show their reasons. **TPM → Install / initialize TPM** downloads missing tools and creates keys/certificates only for an empty private state directory. Existing keys are preserved; replacement remains an explicit operation. Checks inspect a disposable copy of the NV state, leaving the live state alone. The local CA does not supply hardware-vendor attestation.

The TPM page opens with eight choices: copy the host's public identity, generate an identity, use the published build, use the physical TPM, or apply AMD, Intel, Infineon and STMicroelectronics presets. Each action prepares, verifies and saves the selection for the next VM start. Identity changes use a separate runtime and new guest state; **Undo last TPM change** restores the previous selection without deleting its keys. Encrypted guests may require recovery after changing TPMs. Advanced fields and diagnostics remain available behind **Advanced settings** and **Details**. Host identity copying never copies private hardware keys or writes to the host TPM; physical passthrough is a separate explicit choice.

Custom identities require the recipient's local TPM builder, configured in Paths & Tools; unavailable choices explain the missing capability. The developer workstation uses its private builder. Builds run in the background into a new private prefix, restore the builder's identity inputs, and verify the properties actually reported by the resulting TPM before activation. Published binaries still ship without source trees, and the published TPM option needs no builder.

TPM runtime helper scripts are seeded into `tpm-workspace/` without replacing existing edits or identity. Source-dependent rebuilds are optional: provide your own local source/build paths in the editor. The published runtime packages need no compilation. Setup installs the native compilers, autotools, development libraries, hardware utilities, TPM tools, OpenCore disk tools and remote viewer; it does not supply private custom source checkouts. No TPM state, libvirt encryption keys, guest system disks or private publisher keys are included. Matching Looking Glass guest components are still required.

## Development and verification

`config/hypr/kvm/backend/ORIGIN.json` records the imported vmstart_2 revision. The publisher and private signing key live only on the development machine, outside this desktop repository. The publisher creates independently versioned `.tar.xz` archives with maximum xz compression and uses signed, resumable uploads with an atomic release commit.

Run the offline package/boot-edit tests from `config/hypr/kvm` with `python3 -m unittest test_packages test_boot test_activity test_runtime_setup test_setup -v`. `QT_QPA_PLATFORM=offscreen python3 app.py --smoke-dir /tmp/kvm-smoke` opens all Windows and Mac pages using isolated settings and captures screenshots. The backend's original pytest suite also includes real VM and network integration tests; those are separate from the desktop test runner.

Validation covers signed package handling, corruption and traversal rejection, interrupted installs/uploads, kernel/CPU gates, guest NVRAM preservation, rollback of synthetic GRUB files, complete UI navigation, and relocated executable probes. Actual guest booting, physical GPU passthrough and live GRUB/module changes require testing on the intended host.
