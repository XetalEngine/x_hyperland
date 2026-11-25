# Bundled shell enhancements

These are pinned upstream shell sources, loaded only by Fusion's interactive
Bash profile. `manifest.json` records revisions, source URLs and build commands.

- **ble.sh**: BSD-3-Clause; see `blesh/LICENSE.md` and `blesh/licenses/` for
  upstream and included third-party notices. The complete pinned project and
  contrib revision are available through the manifest links.
- **bash-completion 2.18.0**: GPL-2.0-or-later; see `bash-completion/COPYING`.
  The unmodified corresponding source release is included as
  `bash-completion-2.18.0.tar.xz`. Its SHA-256 is recorded in the manifest.

There is no startup network request, global shell modification or package-manager
operation. Caches and personal history must never be added to this directory.
Keep upstream code unchanged; Fusion's configuration belongs in `../blerc` and
`../bash-enhancements.sh`. Test with a fresh cache when updating either vendor.
