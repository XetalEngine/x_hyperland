# Software catalog sources

The bundled category tree and curated picks are in `catalog.json`. Keep package
names, desktop IDs and sources explicit. `featured_order` controls the Top picks
banner order; vendor entries remain visible without enabling an AUR helper.

- Official apps and package availability come from the machine's enabled Pacman
  databases. Rich metadata and cached icons come from Arch's installed
  `archlinux-appstream-data`, using the [AppStream catalog format](https://www.freedesktop.org/software/appstream/docs/chap-CatalogData.html).
- Optional AUR search uses the [Aurweb v5 RPC interface](https://aur.archlinux.org/rpc).
  Yay and Paru are install helpers for the same catalog, not separate repositories.
- Xetal product descriptions and Linux artifact layouts were checked against
  [the official product site](https://www.xetal.net/community/site/) and its live
  release feeds on 2026-11-24 UTC. Downloads resolve those feeds when requested;
  no release version or expiring artifact URL is stored in the seed catalog.
- Echo, Linux Studio, XMusic and Xetal Video Editor artwork reuses
  `startup/assets/projects` and its `SOURCE.json`. Discord and Chrome reuse the
  existing `control_panel/assets/deb` icons. Banner patterns are painted vectors.

Vendor manifest endpoints are explicitly defined in `software_catalog.py`.
Only published Linux x86_64 artifacts with the expected product/version filename,
size and SHA-256 metadata are offered. The browser handles downloads; the catalog
does not claim to verify downloaded bytes and never executes downloaded files.
