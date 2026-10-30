Version-matched OpenCore validators

1.0.8/ocvalidate is the Linux x86_64 binary from the official OpenCorePkg
1.0.8 release, copied from the local MAC_OS_NEW/Downloads/OpenCorePkg package.
Source: https://github.com/acidanthera/OpenCorePkg/releases/tag/1.0.8
The upstream BSD 3-Clause license is included in 1.0.8/LICENSE.txt.

Each version directory contains ocvalidate and manifest.json with version,
opencore_sha256, ocvalidate_sha256 and source. The editor requires BOTH the
OpenCore.efi and validator hashes to match; it does not guess a version from
binary strings. Keep this directory in backups of the vmstart2 installation.
