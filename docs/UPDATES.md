# Desktop updates

Hyper Fusion watches `XetalEngine/x_hyperland` on GitHub, branch **main**. Every new descendant commit on that branch is a desktop release. Publish tested changes there; use another branch for experiments.

## What users see

An animated **UPDATE** badge appears beside **Keys** when a newer commit is available. It stays completely hidden while the desktop is up to date or checking for updates, and remains visible while an update downloads or waits for the next login. Click it for installed/latest revisions, the commit message, a live update log, **Check now**, **Update!**, automatic-update preferences and **Roll back**. Right-click the taskbar and check **Hide Update Ready** to hide the ready/restart notice across all monitors and future logins. New-update and error notices still appear, and update checks continue. Uncheck it to show the notice again. **Options → Desktop updates** hides all update notices; **Show all items** resets both choices. To manage updates while the badge is hidden, run `~/.config/hypr/scripts/desktop-updates.sh`.

The main button changes from **Update!** to **Updating…**, then **Restart** once the update has finished building and validating. The log opens at its newest output and follows new lines; scrolling up pauses following until you return to the bottom. Restart asks you to save your work and confirm, then uses the normal system restart request. If authorization or a shutdown inhibitor blocks it, the update remains ready and the button allows another attempt. Updates never restart the computer automatically.

![Desktop updates](screenshots/desktop-updates.png)

Automatic updates are enabled by default. One session helper checks roughly every 15 minutes, with a short startup delay. After showing the notice for at least 30 seconds, it downloads the advertised commit, merges the new defaults with personal settings, builds native components and validates the complete Hyprland configuration.

**Ordinary automatic updates activate at the next Hyprland login, before the session helpers and native effects load.** No forced logout or compositor-plugin replacement occurs while you are working. The badge changes to **UPDATE READY** after preparation. You can choose **Restart** to finish, or let the update activate at a later login. Pausing automatic updates also postpones activation of an already prepared automatic update; clicking **Restart** explicitly enables that pending update without changing your automatic-update preference. A manually requested update also remains explicit. If a newer release appears while an older one is prepared, the badge offers that newer release and identifies the prepared revision separately.

Each release declares its required compositor in `runtime/manifest.json`. A different installed version or source commit shows **SETUP REQUIRED**; **Update!** opens the graphical Setup wizard for that release. Background updates never elevate privileges. This foreground wizard uses the release's signed Arch package or Fedora 44 RPM bundle, requests administrator authentication, builds and validates the matching desktop, and installs the merged profile in the same operation. **Restart** is offered afterward to start that pair together, and the restart reminder clears at the next login. The same path repairs a compositor mismatch even when the desktop source revision is already current.

## Keeping personal settings

The installer records the delivered revision, defaults and file ownership in `~/.config/hypr/.xetal-update.json`. The incoming release supplies application files; personal settings use the rules in `updates/file_policy.py`. Older installation records without ownership fields remain supported.

Git checkouts use their own commit. GitHub ZIP and tar downloads use `installer/source-revision.txt`, populated by Git's [`export-subst` archive attribute](https://git-scm.com/docs/gitattributes#Documentation/gitattributes.adoc-export-subst). Registration works offline and does not substitute the current GitHub head for an older download. If an old or incomplete archive has no revision, the installer stops before replacing the profile and asks for a fresh download. The update builder uses the same source identification and still rejects any revision that differs from the announced update.

- Shipped application code, scripts, build inputs, templates, assets and runtime manifests are replaced with the exact incoming versions and permissions. This also repairs modified or missing files when their upstream content has not changed. A copied standalone helper at a newly shipped path is replaced through the same transaction, without fingerprint exceptions or additional Git history lookups. Retired application files are removed, including modified copies, with originals in the rollback backup.
- Declared JSON preferences merge with new defaults; overlapping choices retain the user's value. When an older profile has no baseline for a preference file, existing values are retained and missing defaults are added.
- Hotkeys and other declared text settings use a three-way merge. Overlapping changes keep the local configuration and are reported in the update log. The resulting complete configuration must still pass validation before activation.
- Monitor arrangements, selected wallpapers, generated theme colors, personal taskbar CSS and the private Dolphin profile are retained.
- Launcher favorites, shortcut copies, taskbar pins, groups and window sizes belong to the recipient. Fresh-install defaults (Kitty and Calculator) do not repin removed apps or replace those choices during an update.
- Unrelated files absent from both release inventories stay in place. Private state, caches and personal Dolphin data are excluded; temporary state created while building an update is never installed over the user's state. Settings retained from a retired preference file stay in place.
- The prepared plan records hashes. If settings change before login, activation stops and the update is prepared again.

The updater does not pull, reset, stash or rewrite a developer's clone. Its own exact-commit checkout lives in a private cache. A local build ahead of `main`, a rewritten branch or unrelated history does not trigger an automatic downgrade.

For direct development installs, finish by registering the delivered commit and its rendered defaults in `.xetal-update.json`, after validating the deployed files. Copying individual fixes without advancing that inventory leaves the checker comparing an older release and can produce a repeated UPDATE notice or merge failure. Do not mark the desktop current from a checkout's HEAD alone: verify the delivered profile first, preserve personal settings and keep a backup. The normal installer/update transaction maintains this record automatically.

## Failure and recovery

Preparation works in a separate directory. A differing application file no longer blocks an update or needs a manual reinstall. Missing packages, failed builds, invalid configuration or files changed during preparation still leave the current desktop installed. Automatic updates never run `sudo` or change system packages; dependency problems are shown for the user to resolve.

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

The updater tests cover application-file replacement, overlapping preferences, source integrity, interrupted writes, rollback, rate limits, commit ancestry, singleton ownership, logout cleanup and all three theme palettes. A disposable profile based on release `2f75086` with unregistered and modified helpers also completed a full native build, complete configuration validation, activation using that older release's transaction engine, and rollback to the original files.

When adding an editable settings file, declare it in `updates/file_policy.py`; files supplied by a release otherwise belong to the application. Keep personal values in these settings or private state directories rather than editing application source. Replacement tests cover multiple unknown helper collisions, modified code, restored executable permissions, removed application files, missing baselines, rollback originals, disk failures and concurrent edits.
