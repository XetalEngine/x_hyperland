# Bundled compositor

`hyprland-0.56.2-4-x86_64.pkg.tar.zst` is the unmodified, signed official Arch
package from the [Arch Linux Archive](https://archive.archlinux.org/packages/h/hyprland/).
It is already compressed: 51,303,184 bytes (48.9 MiB). The detached `.sig` file
is included alongside it, so GitHub's Download ZIP contains both actual files.

Setup checks both against `config/hypr/runtime/manifest.json`, then verifies the
package signature with pacman's keyring before installing. It prefers this copy,
reuses verified cached copies, and falls back to the archive if necessary.
Other desktop dependencies and the previous compositor's recovery package may
still require network access.

Hyprland is BSD-3-Clause; the license is reproduced in
[`LICENSES/Hyprland-BSD-3-Clause.txt`](../../LICENSES/Hyprland-BSD-3-Clause.txt)
and inside the package. [Upstream source](https://github.com/hyprwm/Hyprland/tree/efb50993780079460b0cbed1363e2166a2de1d9f).

When changing the tested runtime, replace the bundle and signature together with
the runtime manifest after validating the desktop and native effects. Do not
accumulate previous compositor versions here.
