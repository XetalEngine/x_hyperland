# Fedora 44 runtime bundle

These are unmodified, signed **Fedora 44 x86-64** RPMs from
[giperborey/Hyprland on Fedora COPR](https://copr.fedorainfracloud.org/coprs/giperborey/Hyprland/),
not packages from Fedora's official repositories. The compositor is Hyprland
**0.56.2-6.fc44**, built from commit
`efb50993780079460b0cbed1363e2166a2de1d9f`, matching this desktop's native adapters.

The 19 runtime/development RPMs total **55,923,257 bytes (55.9 MB)**. Their
corresponding LGPL source packages total **55,445,103 bytes (55.4 MB)** separately.
Every individual file is below 100 MB. All files are included directly in Git
and GitHub Download ZIP; no Git LFS or COPR repository configuration is needed.

[`config/hypr/runtime/fedora-44.json`](../../../config/hypr/runtime/fedora-44.json)
records exact package versions, architectures, sizes, SHA-256 hashes and original
HTTPS URLs. The included `copr-key.gpg` has fingerprint
`199F98CA56F2AE4B77E6C7190357FF4CE7B95988`.
Setup first verifies the immutable bundle against this key in a separate RPM
key database, then imports the verified public key into the system RPM keyring
for DNF's normal signature checks. It never enables a third-party repository.

| Component | Pinned Fedora EVR |
| --- | --- |
| hyprland | `0:0.56.2-6.fc44` |
| hyprland-devel | `0:0.56.2-6.fc44` |
| aquamarine | `0:0.15.1-3.fc44` |
| aquamarine-devel | `0:0.15.1-3.fc44` |
| hyprutils | `0:0.14.3-1.fc44` |
| hyprutils-devel | `0:0.14.3-1.fc44` |
| hyprgraphics | `0:0.5.1-7.fc44` |
| hyprgraphics-devel | `0:0.5.1-7.fc44` |
| hyprlang | `0:0.6.8-7.fc44` |
| hyprlang-devel | `0:0.6.8-7.fc44` |
| hyprcursor | `0:0.1.13-9.fc44` |
| hyprcursor-devel | `0:0.1.13-9.fc44` |
| hyprwire | `0:0.3.1-5.fc44` |
| hyprwire-devel | `0:0.3.1-5.fc44` |
| hyprpaper | `0:0.8.4-11.fc44` |
| hyprlock | `0:0.9.6-4.fc44` |
| xdg-desktop-portal-hyprland | `1:1.5.0-1.fc44` |
| hyprtoolkit | `0:0.6.0-4.fc44` |
| hyprpolkitagent | `0:0.2.0-2.fc44` |

Fedora package notices and licenses remain embedded in each RPM. Aquamarine is
BSD-3-Clause/MIT; Hyprcursor, Hyprgraphics, Hyprutils, Hyprwire, Hyprlock,
Hyprpolkitagent, Hyprtoolkit and the Hyprland portal retain BSD-3-Clause notices.
Hyprpaper also includes HPND-sell-variant material. Hyprland includes BSD-3-Clause,
BSD-2-Clause, HPND-sell-variant and LGPL-2.1-or-later material; Hyprlang is
LGPL-3.0-only.

The `sources/` directory contains the exact signed Hyprland and Hyprlang source
RPMs, including upstream source archives, license text, Fedora spec files and
patches. Their hashes and download URLs are in the manifest. They can be
extracted without installing them using `rpm2cpio FILE.src.rpm | cpio -id` in a
new empty directory. They are not installed by Setup.

When replacing this bundle, update its manifest, signing-key provenance and
corresponding sources together. Validate dependency resolution, all native
builds and recovery with `tests/fedora_container.py` in a disposable Fedora
container before publishing. Never use these RPMs on Arch, other Fedora releases,
RHEL derivatives or immutable desktops.
