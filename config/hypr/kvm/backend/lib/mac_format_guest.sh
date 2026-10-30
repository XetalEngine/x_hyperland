#!/bin/bash
# Served only to the temporary, diskless Recovery guest by mac_format.py.
# The host attaches one target after this script has checked in. It must approve
# the guest's disk identity before the single destructive command is reached.
set -euo pipefail
BASE=__BASE__
LABEL=__LABEL__
WORK=$(mktemp -d /tmp/vmstart2-format.XXXXXX)
post() { /usr/bin/curl --fail --silent --show-error --max-time 15 "$@"; }
event() { post -X POST --data-urlencode "stage=$1" --data-urlencode "message=${2:-}" "$BASE/event" >/dev/null; }
upload() { post -X POST --data-binary "@$2" "$BASE/$1" >/dev/null; }
fail() { event error "$1" || true; exit 1; }
trap 'fail "macOS disk preparation failed at line $LINENO (status $?)."' ERR
[[ $(uname -s) == Darwin && $(id -u) == 0 ]] || fail 'Expected macOS Recovery root terminal.'
event hello "$(sw_vers -productVersion)"

# Allow the guest to enumerate the one USB disk the host has just attached.
DISK=wait
for ((attempt=0; attempt<90; attempt++)); do
    diskutil list -plist external physical > "$WORK/disks.plist"
    upload disks "$WORK/disks.plist"
    DISK=$(post "$BASE/selection")
    [[ $DISK == wait ]] || break
    sleep 1
done
[[ $DISK =~ ^disk[0-9]+$ ]] || fail "No unique format target: $DISK"
diskutil info -plist "$DISK" > "$WORK/info.plist"
upload info "$WORK/info.plist"

PERMIT=wait
for ((attempt=0; attempt<30; attempt++)); do
    PERMIT=$(post "$BASE/permit")
    [[ $PERMIT == wait ]] || break
    sleep 1
done
[[ $PERMIT == "ERASE:$DISK" ]] || fail 'The host did not approve this disk identity.'
event formatting "Creating GUID partition map and APFS volume on $DISK"
diskutil eraseDisk APFS "$LABEL" GPT "/dev/$DISK" 2>&1 | while IFS= read -r line; do
    event detail "$line"
done
event verifying 'Checking the partition map and APFS filesystem'
diskutil list -plist "$DISK" > "$WORK/layout.plist"
upload layout "$WORK/layout.plist"
diskutil apfs list -plist > "$WORK/apfs.plist"
upload apfs "$WORK/apfs.plist"
VOLUME=$(post "$BASE/volume")
[[ $VOLUME =~ ^disk[0-9]+s[0-9]+$ ]] || fail 'The new APFS volume was not verified.'
diskutil verifyDisk "$DISK" 2>&1 | while IFS= read -r line; do event detail "$line"; done
diskutil verifyVolume "$VOLUME" 2>&1 | while IFS= read -r line; do event detail "$line"; done
diskutil unmount "$VOLUME" 2>&1 | while IFS= read -r line; do event detail "$line"; done
diskutil unmountDisk "$DISK" 2>&1 | while IFS= read -r line; do event detail "$line"; done
sync
event complete 'APFS volume verified and unmounted'
rm -rf "$WORK"
