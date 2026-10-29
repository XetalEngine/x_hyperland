# Compiz task switchers

Unmodified reference sources and option metadata from the user-supplied
`XetalCompiz_old` tree. They are included so this adaptation can be built and
maintained without that external folder. These X11 plugins are not loaded into
Hyprland; `../geometry.py` and `../scene.py` adapt their layouts to Wayland window
previews.

Ring and Static Application Switcher: Danny Baumann (2007–2008), based on
David Reveman. Shift: Dennis Kasprzyk (2007), based on Danny Baumann and
David Reveman; its original rounded-corner drawing credits Robert Carr.
Stack Window Switcher: Danny Baumann (2007), based on David Reveman.
These plugins and the adapted geometry/renderer are **GPL-2.0-or-later**; see
[COPYING](COPYING) and the retained source headers.

Core Application Switcher and Scale: David Reveman / Novell, Inc. (2005).
Their permissive license and copyright notices are retained at the top of each
source file and apply to those originals.

`vpswitch` and `mswitch` switch viewports, not application windows, and are outside
the Super+Tab task switcher. Shift has two modes, Cover and Flip, exposed as
individual choices. Scale is included as an additional window overview.

## Original source checksums

| Source | SHA-256 |
| --- | --- |
| `compiz-core/plugins/switcher.c` | `b6f75bcc53c9fa4264c789f02fe9bcfff34a38d3708d7dab27c8eea32d8a980d` |
| `compiz-core/metadata/switcher.xml.in` | `1c7cacece2a2604c4550fe337ce3e6ef4509b102b8173f68e7ca88fcc28f9b64` |
| `compiz-core/plugins/scale.c` | `0ae3ebbb31d88ec2ceed6a2c80af303f54e4c9ec97e6e9e2ab37d32bffccd714` |
| `compiz-core/metadata/scale.xml.in` | `b78f392778502e398c085b6aaf67f3908d4a3e28bad1f4ad6db42d672760f0dc` |
| `compiz-plugins-main/src/staticswitcher/staticswitcher.c` | `b6e0821c90d7418d3bb11fe8c6ac26450b54efa95f162aa62be376d76b6d8b29` |
| `compiz-plugins-main/metadata/staticswitcher.xml.in` | `2ea85e22a022f5402d7a441de568b4155b445ad75a2891c6e389087dcc0f6355` |
| `compiz-plugins-main/src/ring/ring.c` | `eaaa8f16da0ad6834c2993d80804860b6485b37d404100c15932771d9a7a23bc` |
| `compiz-plugins-main/metadata/ring.xml.in` | `86d8fb758d3febb9a6e5c16a30f16c8feb5a232525fb5e1e1aefa2671275cd9a` |
| `compiz-plugins-main/src/shift/shift.c` | `eb167ba6c57cff9710cca8ad70c25534255d078cdd21f46acf9fa0bb24cdf801` |
| `compiz-plugins-main/metadata/shift.xml.in` | `dd44962eda28b5bbc5f3fc6fc29d5b1fe2d54610b2efad5457c39142138d6bae` |
| `compiz-plugins-experimental/src/stackswitch/stackswitch.c` | `71d1af90bc246aad27941a6b41df57ecf9435ba4ef3426c8d953339f75779b5f` |
| `compiz-plugins-experimental/metadata/stackswitch.xml.in` | `90113b87801ad1f97f01e37ef0d95af90772d0e54bd6a93b9a3e191e6ecaceac` |
