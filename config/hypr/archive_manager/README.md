# 7-Zip · Fusion

Fusion Files and desktop icons share a native, themed archive manager backed by
**7-Zip 26.06**. The full source and compiled engine are included in the profile:
installation, updates and operation need no Ark or system 7-Zip package, and no
archive-engine download or upstream version lookup takes place.

## Included source and engine

`vendor/7z2606-src.tar.xz` is the unmodified
[official 26.06 source release](https://github.com/ip7z/7zip/releases/tag/26.06),
1,567,328 bytes compressed (about 1.5 MiB). Its SHA-256 is
`a4e374c8f864f51df48c2cfd0e1413ec3b2ea030deae852d6a655402ebb61ac4`.
The Linux x86-64 `vendor/7zz-fusion` executable is approximately 3.2 MiB.
`vendor/manifest.json` records both hashes and the compiler/runtime requirements.
The included executable uses the system glibc (2.38 or later), available on the
supported Arch, Fedora 44 and Debian 13 installations; GCC's C++ runtime is
linked into it. No external archive-codec plugin is required.

`build_engine.py` applies the included LGPL adapter to a temporary extraction of
the source, then compiles the complete upstream `Alone2` engine. The adapter adds
structured progress, exact member names, input errors and a private password
channel, and omits actual Unix sockets before counting archive inputs. It does
not replace any compression or extraction algorithm. The full
upstream archive-handler and codec set is retained.

To rebuild offline with GCC, make, binutils and Python installed:

```sh
python3 config/hypr/archive_manager/build_engine.py
```

The build verifies the source checksum and updates the engine checksum. Normal
users run the included engine without compiling it. An engine upgrade requires
an intentional source/manifest/adapter update and validation; installing a newer
distribution 7-Zip package does not change Fusion's engine. Pinning keeps behavior
stable; security fixes can still be deliberately shipped in a HyperFusion update.

Upstream copyright and license notices are in `vendor/License.txt`,
`vendor/copying.txt` and `vendor/unRarLicense.txt`. The source archive also contains
its original per-file notices. Most upstream code and our native adapter/build
script use LGPL-2.1-or-later; specified upstream files use BSD/public-domain terms
or the additional unRAR restriction. RAR decoder code cannot be used to develop a
RAR-compatible compressor. The GCC runtime license and Runtime Library Exception
are in `vendor/GCC-GPL-3.0.txt` and `vendor/GCC-RUNTIME-EXCEPTION.txt`. System glibc
remains a distribution-provided dependency. The separate Fusion Python UI uses
the repository license.

## Features

- Shared **7-Zip** menus in Files and on the desktop: Compress, Compress to,
  quick 7z/ZIP, Open archive, Extract here, Extract to a separate folder,
  Extract to, and Test archive.
- Creation formats: **7z, ZIP, tar, tar.gz, tar.xz, tar.bz2, gzip, xz, bzip2,
  and WIM**. The pinned engine creates WIM with its Copy method. Raw gzip/xz/bzip2
  streams accept one file; their tar variants accept folders and multiple files.
- Every compression method supported by these upstream writers: **LZMA2, LZMA,
  PPMd, BZip2, Deflate, Deflate64 and Copy**, where applicable. Compression levels,
  dictionary size, CPU threads, solid 7z archives and split volume sizes are
  configurable. Compression defaults to all detected logical CPU threads on the
  current machine. The engine retains its automatic architecture filters.
- AES-256 passwords for 7z and ZIP, legacy ZIP encryption, and optional encrypted
  7z file names. Passwords are passed through anonymous memory descriptors; they
  are never put in command lines, reports or saved preferences. Upstream ZIP
  passwords must be printable ASCII, with a 99-character AES limit; use 7z for
  Unicode passwords. The UI validates the actual engine restrictions.
- Reading/extraction uses the complete upstream decoder set, including RAR,
  CAB, ISO, disk images and Zstandard. Read support does not imply write support:
  RAR and Zstandard creation are not supported by this pinned upstream engine.
- Searchable, sortable archive contents form an expandable **folder tree**, with
  themed file icons and folders first. Folders omitted by the archive writer
  are reconstructed from member paths. Search keeps matching files inside their
  parent folders. An on-disk SQLite index and paged children keep browsing from
  loading every member into memory.
- **Drag files or folders into Fusion Files to extract.** Select one or several
  entries, then drop onto a folder or the current folder's background. A nested
  file lands directly in the destination; a folder keeps its contents together.
  Multiple selections preserve their layout below their common parent. Drops
  copy out of the archive and use the existing progress, password and overwrite
  dialogs. Canceling the drag does not start extraction. No Ark installation is
  needed: the browser uses the archive handoff already supported by Fusion Files.
- Extract selected entries with the toolbar, or add/delete/rename entries in
  writable formats. Updates use a temporary copy and verify it before replacing
  anything.
- Animated Fusion transfer cards, pause/resume/cancel, live engine progress,
  an expanding attention drawer, explicit Retry/Skip and saved reports.

## Transactions and limits

Work starts in a private directory on the destination filesystem when writable,
or in the user's state directory otherwise. Compression verifies the new archive
before publishing it. Input warnings are queued while other files continue;
retries rebuild the archive, and omissions require an explicit Skip decision and
appear in the completion report. Corrupt extraction never publishes partial
staging data over existing destination files.

The attention drawer shows a requested state until the job confirms a choice,
then keeps the same row visible with its result. Compression input Skip/Retry
choices are acknowledged immediately, including while the engine is busy or
paused; processing can remain paused. Skip shows a distinct icon and an explicit
confirmation that the original is kept. The summary counts accepted skips, and
the detail panel confirms when Skip similar covers current and later matching
issues in this job. Retry similar applies only once to currently queued items.
The final error summary cannot reopen a choice already accepted during that pass.
Skipped inputs stay excluded when another input triggers an archive rebuild,
including filenames containing wildcard characters or newlines. A failed retry
requires a new choice for its new issue revision.

Extraction validates member paths and link targets, unpacks into private staging,
and uses Fusion's transfer worker to publish the result. This includes newly
created destination folders, overwrite choices and scoped administrator access
for destination permissions. Administrator access does not run the archive
parser as root. Compression input permission failures offer retry after access
is corrected, or explicit omission; they do not silently elevate the parser.

Original inputs are kept. Actual Unix sockets are automatically omitted before
counting inputs, without an attention row; ordinary files with a `.sock` suffix
are preserved. No
artificial archive/download/file-size limits are imposed. Disk space, memory,
filesystem and format restrictions still apply. Staging and verification require
additional disk space and time, especially for compressed tar files.

Split archive extraction is supported. Creating a split set with an already
existing base name requires a new name, preventing mixed old/new volume sets.
Extract split or non-updatable formats before editing their contents. Remote
URLs must first be copied to a local folder. Archive drops also require a local
destination; copy extracted files onward for remote locations. A drop keeps its
own selection even if the browser selection changes or the browser closes while
Fusion Files receives it. If the source archive changes during the drop or
extraction, the job stops before publishing. External Ark drag/drop remains
compatible if a user independently keeps Ark installed.

The destination's extraction request starts the job. The browser keeps that
handoff available briefly after Qt returns from a drag, including an
`IgnoreAction` result on Wayland; the compositor's drag result and KIO's request
can arrive independently. A drag with no destination request expires without
extracting anything. Qt retains ownership of the drag's MIME data until its
native transfer finishes.

## Validation

```sh
python3 config/hypr/archive_manager/test_archives.py -v
python3 config/hypr/archive_manager/test_decisions.py -v
QT_QPA_PLATFORM=offscreen python3 config/hypr/archive_manager/test_ui.py -v
QT_QPA_PLATFORM=offscreen python3 config/hypr/archive_manager/test_tree.py -v
dbus-run-session -- env FUSION_ARCHIVE_PRIVATE_BUS=1 QT_QPA_PLATFORM=offscreen \
  python3 config/hypr/archive_manager/test_remote.py -v
```

These use disposable files and cover real format/method round trips, encryption,
split archives, filenames containing Unicode/newlines/wildcards, cancellation,
unreadable inputs, overwrites, malicious paths, new destination folders, GUI
password/queue handling and progress decisions across separate processes. Tree
checks cover implicit directories, parent indexes, paged children, search and
selection. Drop checks cover immutable handoffs, browser closure, cancellation,
changed archives, encrypted files and compressed tar selections.
They also exercise extraction requests arriving before and after the drag
returns, including `IgnoreAction`, and abandoned handoffs expiring without work.
