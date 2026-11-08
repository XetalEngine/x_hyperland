#!/usr/bin/env bash
# Runs only inside the disposable cloud guest created by lab.py.
set -euo pipefail
test "$(id -u)" = 0
test -s /etc/hyperfusion-deb-lab.json
systemd-detect-virt --vm --quiet
python - <<'PY'
import json
from pathlib import Path
marker=json.loads(Path('/etc/hyperfusion-deb-lab.json').read_text())
assert Path('/sys/class/dmi/id/product_uuid').read_text().strip().lower()==marker['uuid']
assert marker['purpose']=='disposable-deb-tests'
PY
export LC_ALL=C TERM=xterm
# Full upgrade: the lab must not produce a partially upgraded Arch system.
pacman -Syu --noconfirm --needed python sudo binutils libarchive pacman-contrib \
    pkgfile fakeroot curl gzip gawk tar file which namcap xz zstd \
    xorg-server-xvfb xorg-xauth xorg-xwininfo xorg-xprop xorg-xwd \
    openbox xdotool dbus mesa nss alsa-lib gtk3 at-spi2-core libxss libxtst \
    ttf-dejavu ttf-liberation noto-fonts desktop-file-utils hicolor-icon-theme \
    gtk-update-icon-cache shared-mime-info imagemagick python-pexpect git base-devel
if test -f /home/tester/input/debtap.pkg.tar.zst; then
    pacman -U --noconfirm /home/tester/input/debtap.pkg.tar.zst
else
    echo 'Provide a reviewed debtap Arch package with init --debtap-package.' >&2
    exit 1
fi
if test -f /home/tester/input/debtap-cache.tar; then
    tar -xf /home/tester/input/debtap-cache.tar -C /var/cache
fi
# Always refresh native repository indexes for the guest's actual repositories.
pkgfile -u
# A seeded cache is checked by the production preflight, never replaced by a fixture.
python - <<'PY'
import sys
sys.path.insert(0,'/home/tester/installer')
from deb_install import prepare_database
prepare_database()
PY
pacman -Q > /home/tester/base-packages.txt
uname -a > /home/tester/base-kernel.txt
date -u --iso-8601=seconds > /home/tester/base-created.txt
touch /etc/hyperfusion-deb-lab-ready
sync
