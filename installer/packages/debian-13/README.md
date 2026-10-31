# Debian 13 native runtime

`debian-13-runtime.zip` contains **52 native amd64/all DEB packages**, totaling
**22.3 MB**, for Debian 13 (trixie). It includes Hyprland **0.56.2**, its matching
headers and libraries, Waybar 0.15, Kitty 0.48.2 and SDL3 3.4.18. The desktop's
own wallpapers are already in the main profile; Hyprland's optional background
collection and debugging packages are not installed.

This is a Hyper Fusion bundle. Packages with `~xetal13.1` versions are local
backports built on Debian 13 with its GCC 14 and glibc 2.41, using Debian source
packages. The remaining packages are unmodified Debian trixie-backports DEBs.
These local builds are **not official Debian binary releases**. They do not
install an Arch package, upgrade the system to Debian testing, or add a package
repository. Other dependencies come from the recipient's configured Debian
repositories with APT's normal authentication checks.

The [manifest](../../../config/hypr/runtime/debian-13.json) records exact package
identities, sizes and SHA-256 hashes. Setup verifies the ZIP and every member,
then copies and verifies packages in a root-owned transaction directory before
APT uses them. The trusted release checkout supplies the expected hashes;
these DEBs do not carry the Fedora bundle's RPM publisher signatures.

## Source and build details

The `sources/` directory contains the original archives, complete Debian
packaging and patches, vendored Kitty Go dependencies, and the corresponding
source packages for the included Debian backports. Each source archive is also
below 100 MB; source archives are separate from the 22.3 MB runtime ZIP and are
not installed on the desktop. Copyright and license notices remain in the
sources and each DEB's `/usr/share/doc/PACKAGE/copyright`.

Sources come from [Debian's package pool](https://deb.debian.org/debian/pool/main/)
and [trixie-backports](https://backports.debian.org/trixie-backports/overview/).
Hyprland uses Debian's `0.56.2+ds-3` source packaging, based on commit
`efb50993780079460b0cbed1363e2166a2de1d9f`. Its Debian GCC compatibility patches
are retained, with one additional explicit `string_view` conversion for GCC 14.
The compositor/effect API stays on that source version. Qt window previews
select the Qt 6.8-compatible vertical-mirroring API when needed.

Prepare all corresponding sources in a **new** directory:

```bash
python3 installer/packages/debian-13/rebuild.py /tmp/hyper-fusion-debian-sources
```

Use a disposable Debian 13 build environment with `dpkg-dev`, `debhelper`,
`patch`, the build dependencies listed in each `debian/control`, and the
matching backported libraries. Kitty additionally needs Go 1.26 from
trixie-backports. `rebuild.py` does not install build dependencies or modify
repositories. After provisioning those dependencies, `--build SOURCE --jobs 3`
can prepare and build one source in a new destination. Build libraries first:
Lua, libinput, Wayland, wayland-protocols, then Hyprland. Waybar, Kitty and SDL3
have independent source recipes. Build flags match the supplied binary build:
`nocheck nodoc`, with `noudeb` where applicable. Runtime/desktop integration is
checked separately; this does not claim that all upstream package test suites
were run.

## Installation and recovery

The bundle is restricted to **Debian 13 x86-64**. Ubuntu, older/newer Debian
releases and derivatives need their own verified runtime and are not accepted
by this automatic path.

Setup simulates the native bundle and full desktop transaction first and
rejects application removals. It saves exact previous packages before replacing
anything, downloads the selected dependencies, and records the transaction in
`/var/lib/xetal-hyprland/debian-runtime/`. If the desktop build fails, recovery
restores replaced versions and removes only newly introduced runtime packages
and their newly introduced dependants. Ordinary dependencies may remain installed. It refuses unrelated removals or externally changed versions.
Package pins live in the dedicated `/etc/apt/preferences.d/xetal-hyprland` file;
other APT preferences and repositories are preserved.

The portable QEMU binary and EDK II firmware are unchanged. The SDL3 backport
supplies the host library required by QEMU's bundled SDL compatibility layer.
Arch-specific Control Panel package and kernel tools remain Arch-specific.

Run [the Debian container check](../../../tests/debian_container.py) only in a
disposable Debian 13 container. It exercises the real package transaction,
complete native desktop build, configuration validation, old-version recovery
and an injected post-install failure. Graphical VM login and physical GPU
passthrough remain separate tests.
