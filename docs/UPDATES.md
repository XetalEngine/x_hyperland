# Desktop updates

Hyper Fusion watches `XetalEngine/x_hyperland` on GitHub, branch **main**. Every new descendant commit on that branch is a desktop release. Publish tested changes there; use another branch for experiments.

## What users see

An animated **UPDATE** badge appears beside **Keys** when a newer commit is available. It stays completely hidden while the desktop is up to date or checking for updates, and remains visible while an update downloads or waits for the next login. Click it for installed/latest revisions, the commit message, a live update log, **Check now**, **Update!**, automatic-update preferences and **Roll back**. Right-click the taskbar → Options can hide the module without disabling checks. To manage updates while the badge is hidden, run `~/.config/hypr/scripts/desktop-updates.sh`.

The main button changes from **Update!** to **Updating…**, then **Restart** once the update has finished building and validating. The log opens at its newest output and follows new lines; scrolling up pauses following until you return to the bottom. Restart asks you to save your work and confirm, then uses the normal system restart request. If authorization or a shutdown inhibitor blocks it, the update remains ready and the button allows another attempt. Updates never restart the computer automatically.

![Desktop updates](screenshots/desktop-updates.png)

Automatic updates are enabled by default. One session helper checks roughly every 15 minutes, with a short startup delay. After showing the notice for at least 30 seconds, it downloads the advertised commit, merges the new defaults with personal settings, builds native components and validates the complete Hyprland configuration.

**Ordinary automatic updates activate at the next Hyprland login, before the session helpers and native effects load.** No forced logout or compositor-plugin replacement occurs while you are working. The badge changes to **UPDATE READY** after preparation. You can choose **Restart** to finish, or let the update activate at a later login. Pausing automatic updates also postpones activation of an already prepared automatic update; clicking **Restart** explicitly enables that pending update without changing your automatic-update preference. A manually requested update also remains explicit. If a newer release appears while an older one is prepared, the badge offers that newer release and identifies the prepared revision separately.

Each release declares its required compositor in `runtime/manifest.json`. A different installed version or source commit shows **SETUP REQUIRED**; **Update!** opens the graphical Setup wizard for that release. Background updates never elevate privileges. This foreground wizard uses the release's signed Arch package or Fedora 44 RPM bundle, requests administrator authentication, builds and validates the matching desktop, and installs the merged profile in the same operation. **Restart** is offered afterward to start that pair together, and the restart reminder clears at the next login. The same path repairs a compositor mismatch even when the desktop source revision is already current.

## Keeping personal settings

The installer records the delivered revision and defaults in `~/.config/hypr/.xetal-update.json`. That baseline distinguishes upstream changes from personal edits.

Git checkouts use their own commit. GitHub ZIP and tar downloads use `installer/source-revision.txt`, populated by Git's [`export-subst` archive attribute](https://git-scm.com/docs/gitattributes#Documentation/gitattributes.adoc-export-subst). Registration works offline and does not substitute the current GitHub head for an older download. If an old or incomplete archive has no revision, the installer stops before replacing the profile and asks for a fresh download. The update builder uses the same source identification and still rejects any revision that differs from the announced update.

- JSON preferences merge with new defaults; overlapping choices retain the user's value.
- Hotkeys and other text configuration use a three-way merge. Conflicting edits stop the update and identify the file.
- Monitor arrangements, selected wallpapers, generated theme colors, personal taskbar CSS and the private Dolphin profile are retained.
- Unknown user files stay in place. A removed upstream file is deleted only if it was unedited.
- The prepared plan records hashes. If settings change before login, activation stops and the update is prepared again.

The updater does not pull, reset, stash or rewrite a developer's clone. Its own exact-commit checkout lives in a private cache. A local build ahead of `main`, a rewritten branch or unrelated history does not trigger an automatic downgrade.

For direct development installs, finish by registering the delivered commit and its rendered defaults in `.xetal-update.json`, after validating the deployed files. Copying individual fixes without advancing that inventory leaves the checker comparing an older release and can produce a repeated UPDATE notice or merge failure. Do not mark the desktop current from a checkout's HEAD alone: verify the delivered profile first, preserve personal settings and keep a backup. The normal installer/update transaction maintains this record automatically.

## Failure and recovery

Preparation works in a separate directory. Missing packages, merge conflicts, failed builds or invalid configuration leave the current desktop installed. Automatic updates never run `sudo` or change system packages; dependency problems are shown for the user to resolve.

Activation has a journal, per-file atomic writes and a backup of changed files. The next startup recovers an interrupted transaction. **Roll back** queues the previous completed version for next login and pauses automatic updates. It refuses to overwrite files edited since that update; inspect the message before resolving any difference.

The required native Burn/Cube/Minimize ABI is checked by their builders. A missing adapter or failed build blocks the prepared desktop. Foreground Setup retains a signed copy of the previous compositor before replacement and restores it if preparation fails or is cancelled. A queued profile is checked against the installed compositor again at activation. On Fedora, the exact bundled library/tool/header versions are checked too, including during profile rollback; a changed runtime requires foreground Setup even if Hyprland itself has the same version and commit. Rollback refuses a backup requiring a different compositor; use that release's Setup to restore the matching pair. [Package pin and recovery details](INSTALLER.md).

## Files and session ownership

| Location | Purpose |
| --- | --- |
| `~/.config/hypr/updates/` | Checker, update UI and merge/transaction engine |
| `~/.config/hypr/.xetal-update.json` | Installed commit and delivered defaults |
| `~/.local/state/xetal-hyprland/updates/` | Settings, cached status, logs, prepared update and rollback backups |
| `~/.cache/xetal-hyprland/updates/` | Exact Git source downloads |

One daemon belongs to the running Hyprland instance; each taskbar reads its cached status. Compositor shutdown closes its socket and stops its owned network/build child processes, including detached compiler descendants. No persistent systemd service, global environment change or other desktop's settings are involved.

Public repositories use GitHub's conditional API requests, cached commit information and rate-limit backoff. Before public release, the private repository can use Git's existing credential helper; the updater never reads or stores tokens itself. Without repository access, checking reports the problem and leaves the desktop unchanged.

## Maintainer checks

```bash
(cd config/hypr/updates && QT_QPA_PLATFORM=offscreen python3 -m unittest discover -v)
python3 -m unittest discover -s tests -v
./tests/run-desktop-tests.sh
```

The updater tests cover merge conflicts, preference preservation, source integrity, interrupted writes, rollback, rate limits, commit ancestry, singleton ownership, logout cleanup and all three theme palettes. A disposable-profile integration run also built the native components, validated the complete config, activated a new revision and restored the previous revision.
