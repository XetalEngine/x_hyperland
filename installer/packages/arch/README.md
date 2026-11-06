# Matching Arch runtime

These unmodified, signed x86-64 packages come from the
[official Arch Linux Archive](https://archive.archlinux.org/packages/).
Together with the Hyprland package in the parent directory they form the
runtime recorded in [arch.json](../../../config/hypr/runtime/arch.json).
All twelve package and signature SHA-256 hashes are checked before use, and
pacman's trusted Arch keyring verifies the original package signatures.

| Package | Version |
| --- | --- |
| aquamarine | 0.15.1-1 |
| hyprgraphics | 0.5.1-4 |
| hyprutils | 0.14.3-1 |
| hyprlang | 0.6.8-5 |
| hyprcursor | 0.1.13-7 |
| hyprwire | 0.3.1-3 |
| hyprtoolkit | 0.6.0-1 |
| hyprland-guiutils | 0.2.2-4 |
| hyprpaper | 0.8.4-9 |
| hyprlock | 0.9.6-3 |
| xdg-desktop-portal-hyprland | 1.4.1-2 |

Hyprland 0.56.2 needs Aquamarine ABI 14 and Hyprgraphics ABI 4. Current repositories
provide ABI 15 and ABI 5, so bundling only the compositor no longer suffices.
The matching toolkit, lock screen and wallpaper helper must be selected in the
same transaction. Ordinary desktop dependencies are downloaded automatically.

Packages retain their original metadata and license notices. Corresponding Arch
packaging/source references are available through the package URLs recorded in
their `.PKGINFO` and the [Arch packaging repositories](https://gitlab.archlinux.org/archlinux/packaging/packages).
Missing local packages are fetched from the archive at their exact recorded
filename and verified; no package is installed with dependency checks disabled.

Replace the runtime as a unit when updating it. Run the repository matrix,
historical upgrade checks and disposable Arch install/build/recovery tests before
shipping a new runtime.
