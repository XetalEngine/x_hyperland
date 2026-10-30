#!/usr/bin/env python3
"""Launch sequence for vmstart_2.

The GUI cannot supervise QEMU itself. Passing the only GPU through means
stopping the display manager, which kills this process along with the desktop.
So the whole sequence is written out as one self-contained script and handed to
systemd as a transient unit, which lives outside the login session and survives
the display stack going away.

No libvirt, no ~/.zshrc: every step the hooks used to do is reproduced here in
plain sysfs so vmstart_2 stands on its own.
"""

import json
import os
import re
import shlex
import subprocess
import sys

import smbios
import mac_memory

from portable import data_root
APP_DIR = str(data_root())
RUN_DIR = os.path.join(APP_DIR, "run")
SCRIPT = os.path.join(RUN_DIR, "launch.sh")
LOG = os.path.join(RUN_DIR, "launch.log")


def _pci_is_bridge(slot):
    """True for a PCI/PCIe bridge (base class 0x06). vfio lets a bridge stay in
    a passed-through IOMMU group bound to its own driver, so it is not a device
    that must be handed to the guest."""
    try:
        cls = int(open(f"/sys/bus/pci/devices/{slot}/class").read().strip(), 16)
        return ((cls >> 16) & 0xff) == 0x06
    except Exception:
        return False


# --------------------------------------------------------------- preflight ---
def preflight(cfg, pinning):
    """Everything checked before anything is torn down.

    Returns [(severity, message)] where severity is 'error' (blocks launch),
    'warn' (proceed at your own risk) or 'ok'.
    """
    out = []

    for sev, msg in cfg.validate():
        out.append((sev, msg))
    if cfg.profile == "macos" and not any(d.get("driver") == "vfio-pci"
            and not d.get("_disabled") for d in cfg.devices):
        out.append(("error", "Select the Mac profile's GPU passthrough devices before a Single GPU launch. "
                    "Use Virtual GPU to open Recovery in a window."))

    # --- qemu binary ---------------------------------------------------
    binary = cfg.data["_meta"]["binary"]
    if not os.path.isfile(binary):
        out.append(("error", f"QEMU binary missing: {binary}"))
    elif not os.access(binary, os.X_OK):
        out.append(("error", f"QEMU binary not executable: {binary}"))
    else:
        out.append(("ok", f"QEMU binary {binary}"))

    # --- memory ----------------------------------------------------------
    need, psize, sysfs = _hugepages(cfg)
    if cfg.profile == "macos":
        out.extend(mac_memory.checks(mac_memory.spec(cfg)))
    elif need:
        human = f"{psize // 1024 // 1024} MiB" if psize < 1024 ** 3 else f"{psize // 1024 ** 3} GiB"
        if not os.path.isfile(sysfs):
            out.append(("error", f"kernel has no {human} hugepage pool ({sysfs})"))
        else:
            free = 0
            try:
                free = int(open(sysfs.replace("nr_hugepages", "free_hugepages")).read())
            except Exception:
                pass
            if free < need:
                out.append(("warn", f"{need} x {human} hugepages needed, {free} free. "
                                    f"The launch allocates them and stops if the host "
                                    f"is too fragmented to deliver, rather than "
                                    f"starting a VM that cannot get its memory."))
            else:
                out.append(("ok", f"{need} x {human} hugepages needed, {free} free"))

        # The path only gets the page size of the filesystem it sits on.
        ram = next((o for o in cfg.objects if o.get("id") == "pc.ram"), None)
        path = (ram or {}).get("mem-path", "")
        if path:
            mnt = _hugetlbfs_mount(path)
            if not mnt:
                # No longer a hard stop: the launch mounts a private hugetlbfs
                # at this path before QEMU starts. Only flag if that mount could
                # not happen (the parent filesystem is read-only).
                parent = path if os.path.isdir(path) else os.path.dirname(path) or "/"
                if _read_only_fs(parent):
                    out.append(("error", f"mem-path {path} is not on hugetlbfs and its "
                                         f"parent is read-only, so the launch cannot "
                                         f"mount one there"))
                else:
                    out.append(("ok", f"mem-path {path} is not hugetlbfs yet; the launch "
                                      f"mounts a private {human} hugetlbfs there"))
            elif mnt[1] and mnt[1] != psize:
                out.append(("error", f"mem-path is on {mnt[0]}, mounted with "
                                     f"{mnt[1] // 1024 // 1024} MiB pages, but "
                                     f"{human} is configured. The mount wins."))
            else:
                out.append(("ok", f"mem-path {path} on hugetlbfs {mnt[0]}"))
    elif any(o.get("id") == "pc.ram" for o in cfg.objects):
        out.append(("warn", "guest RAM is not hugepage backed"))

    # --- vfio ------------------------------------------------------------
    if not os.path.isdir("/sys/module/vfio_pci"):
        out.append(("warn", "vfio-pci is not loaded; the script will modprobe it"))
    if not os.path.exists("/sys/kernel/iommu_groups") or \
            not os.listdir("/sys/kernel/iommu_groups"):
        out.append(("error", "no IOMMU groups. Enable IOMMU/SVM in firmware and add "
                             "amd_iommu=on to the kernel command line."))
    else:
        out.append(("ok", "IOMMU active"))

    for d in cfg.devices:
        if d.get("driver") != "vfio-pci" or d.get("_disabled"):
            continue
        slot = d.get("host", "")
        base = f"/sys/bus/pci/devices/{slot}"
        if not os.path.isdir(base):
            out.append(("error", f"{d.get('id')}: PCI device {slot} not present"))
            continue
        grp = os.path.realpath(f"{base}/iommu_group") if os.path.islink(f"{base}/iommu_group") else ""
        if grp:
            members = set(os.listdir(os.path.join(grp, "devices")))
            passed = {x.get("host") for x in cfg.devices
                      if x.get("driver") == "vfio-pci" and not x.get("_disabled")}
            # PCI bridges (root ports) are exempt: the kernel's vfio viability
            # check allows a bridge to remain bound to its own driver, so a root
            # port sharing the GPU's group is not something that must be passed.
            missing = {m for m in (members - passed) if not _pci_is_bridge(m)}
            if missing:
                out.append(("error", f"{d.get('id')}: IOMMU group {os.path.basename(grp)} "
                                     f"also holds {', '.join(sorted(missing))}; the whole "
                                     f"group must be passed"))
            else:
                bridges = {m for m in (members - passed) if _pci_is_bridge(m)}
                if bridges:
                    out.append(("ok", f"{d.get('id')}: IOMMU group {os.path.basename(grp)} "
                                      f"also holds bridge(s) {', '.join(sorted(bridges))}, "
                                      f"which vfio allows to stay put"))

    # --- real time ---------------------------------------------------------
    if rt_wanted(pinning):
        try:
            rt = open("/proc/sys/kernel/sched_rt_runtime_us").read().strip()
        except Exception:
            rt = "?"
        want = rt_runtime(pinning)
        if want is None:
            # The user asked for the host value to be left alone, so say what
            # that value will do rather than reporting it as already correct.
            if rt == "-1":
                out.append(("ok", "RT throttling already disabled on the host"))
            else:
                pct = _rt_percent(rt)
                out.append(("warn", f"real-time scheduling requested and "
                                    f"sched_rt_runtime_us is {rt}{pct}; the script is set "
                                    f"to leave it alone, so the kernel will throttle "
                                    f"these threads"))
        elif rt != str(want):
            target = "-1 (no throttling)" if want < 0 else f"{want}{_rt_percent(want)}"
            out.append(("warn", f"real-time scheduling requested but "
                                f"sched_rt_runtime_us is {rt}; the script sets it "
                                f"to {target}"))
        elif want < 0:
            out.append(("ok", "RT throttling already disabled"))
        else:
            out.append(("ok", f"sched_rt_runtime_us is already {want}{_rt_percent(want)}"))

    if not pinning.get("vcpupin"):
        out.append(("warn", "no CPU pinning configured; vCPUs will float"))
    elif not any("debug-threads=on" in str(x) for x in cfg.to_argv()):
        # Every thread this script pins is found by its name, and QEMU only
        # names threads when asked. Without this the vCPU search comes back
        # empty, the script refuses to pin anything at all, and the guest runs
        # unpinned -- silently, because that is the deliberate safe fallback.
        out.append(("warn", "-name has no debug-threads=on, so QEMU will not name "
                            "its threads and NOTHING will be pinned"))

    # --- iothreads ---------------------------------------------------------
    # An iothread only carries work for a device that names it. QEMU creates
    # and pins the thread either way, so a config with iothreads nobody uses
    # looks tuned while doing nothing -- worth saying once, not fixing here.
    iot = iothread_ids(cfg)
    if iot:
        users = [d.get("id") for d in cfg.devices
                 if not d.get("_disabled") and d.get("iothread") in iot]
        if not users:
            out.append(("warn", f"{len(iot)} iothread object(s) defined "
                                f"({', '.join(iot)}) but no device uses one; they will "
                                f"be created and pinned, and then sit idle"))
        pins = [c for c in (pinning.get("iothreadpin") or []) if str(c).strip()]
        if len(pins) < len(iot):
            out.append(("warn", f"{len(iot)} iothreads but only {len(pins)} cpuset(s) "
                                f"planned; the rest go to the emulator cpuset"))
        # 'IO <id>' has to fit in the kernel's 15-character comm field, and
        # pthread_setname_np rejects a longer name outright instead of
        # truncating it -- so the thread keeps QEMU's own name and cannot be
        # told apart from an emulator thread.
        long_ids = [i for i in iot if len(i) > 12]
        if long_ids:
            out.append(("warn", f"iothread id(s) {', '.join(long_ids)} exceed 12 "
                                f"characters, so QEMU cannot name the thread and it "
                                f"cannot be pinned separately; shorten them"))

    # --- tool paths -------------------------------------------------------
    tools = cfg.data.get("tools", {})
    if tools.get("kvm_build_enabled"):
        kvm = tools.get("kvm_build", "")
        if not kvm:
            out.append(("warn", "KVM module build is enabled but no script is set"))
        elif not os.path.isfile(kvm):
            out.append(("error", f"KVM build script missing: {kvm}"))
        else:
            # The module cannot be swapped while a VM holds it, and the failure
            # arrives as a bare PID from make. Say so here instead.
            holders = 0
            try:
                for line in open("/proc/modules"):
                    f = line.split()
                    if f[0] == "kvm_amd":
                        holders = int(f[2])
            except Exception:
                pass
            if holders:
                running = subprocess.run(["pgrep", "-a", "qemu-system"],
                                         capture_output=True, text=True).stdout.strip()
                out.append(("error", f"kvm_amd is in use by {holders} process(es), so the "
                                     f"module cannot be rebuilt"
                                     + (f": {running.splitlines()[0]}" if running else "")))
            else:
                out.append(("ok", f"KVM module build: {os.path.basename(kvm)} "
                                  f"{tools.get('kvm_build_args') or '(load only)'}"))

    for node, what in (("libvirt-pflash0-storage", "OVMF_CODE"),
                       ("libvirt-pflash1-storage", "NVRAM VARS")):
        b = next((x for x in cfg.blockdevs if x.get("node-name") == node
                  and not x.get("_disabled")), None)
        if not b:
            continue
        fn = b.get("filename", "")
        if not os.path.isfile(fn):
            out.append(("error", f"{what} missing: {fn}"))
        elif what.startswith("NVRAM") and _read_only_fs(fn):
            out.append(("error", f"NVRAM is on a read-only filesystem: {fn}"))
        elif what.startswith("NVRAM") and not os.access(fn, os.W_OK):
            # Not an error. The launch runs as root under systemd, so a
            # root-owned 0600 VARS file is normal and perfectly writable there.
            st = os.stat(fn)
            out.append(("ok", f"{what} {os.path.basename(fn)} "
                              f"(uid {st.st_uid}, mode {oct(st.st_mode & 0o777)}; "
                              f"launch runs as root)"))
        else:
            out.append(("ok", f"{what} {os.path.basename(fn)}"))

    blob = smbios.blob_path(cfg.simple.get("smbios", ""))
    if blob is not None and not os.path.isfile(blob):
        out.append(("error", f"SMBIOS blob missing: {blob}"))

    for tbl in cfg.acpitables:
        p = tbl.split("=", 1)[1] if "=" in tbl else tbl
        if not os.path.isfile(p):
            out.append(("error", f"ACPI table missing: {p}"))

    # --- tpm -------------------------------------------------------------
    tpm = _tpm(cfg)
    if tpm:
        # This is the check that was missing. The socket was reported as
        # "created at launch" while nothing created it, so QEMU died on connect
        # after the desktop was already gone.
        if not os.path.isfile(tpm["binary"]) or not os.access(tpm["binary"], os.X_OK):
            out.append(("error", f"guest has an emulated TPM but swtpm is not "
                                 f"executable: {tpm['binary']}"))
        elif not tpm["state"]:
            out.append(("error", "guest has an emulated TPM but no state directory "
                                 "is configured (Paths & Tools -> swtpm state)"))
        elif not os.path.isdir(tpm["state"]):
            out.append(("error", f"TPM state directory missing: {tpm['state']}"))
        else:
            out.append(("ok", f"swtpm {os.path.basename(tpm['binary'])} -> "
                              f"{tpm['sock']} (state {tpm['state']})"))
        if os.path.exists(tpm["sock"]):
            out.append(("warn", f"{tpm['sock']} already exists; the start hook "
                                f"removes it and any swtpm holding it"))
        # sockaddr_un.sun_path is 108 bytes including the terminator. swtpm
        # fails with "Path for UnixIO socket is too long" and QEMU then has
        # nothing to connect to.
        if len(tpm["sock"].encode()) > 107:
            out.append(("error", f"TPM socket path is {len(tpm['sock'])} bytes; the "
                                 f"unix socket limit is 107. Use a shorter path."))

    # --- every path QEMU opens at startup -----------------------------------
    for c in cfg.data.get("chardevs", []):
        # A disabled chardev is never emitted, so validating it reports a
        # missing socket for something that is not on the command line. Under
        # TPM passthrough the swtpm chardev is switched off exactly this way.
        if c.get("_disabled"):
            continue
        raw = c.get("_raw", "")
        path = c.get("path")
        if not path or "socket" not in raw:
            continue
        if tpm and path == tpm["sock"]:
            continue                       # covered above
        if not os.path.exists(path) and "server=on" not in raw:
            # A client-mode chardev connects at startup and QEMU exits if the
            # other end is not listening yet.
            out.append(("error", f"chardev {c.get('id')} connects to {path}, "
                                 f"which does not exist and nothing creates it"))

    # --- networking ---------------------------------------------------------
    net = cfg.data.get("network") or {}
    raw_netdev = cfg.simple.get("netdev", "")
    if '"fd"' in raw_netdev:
        if net.get("mode") == "tap" and net.get("ifname"):
            br = net.get("bridge") or ""
            if br and not os.path.isdir(f"/sys/class/net/{br}"):
                out.append(("error", f"bridge {br} does not exist on this host"))
            else:
                out.append(("ok", f"tap {net['ifname']} on {br or 'no bridge'} "
                                  f"(created by the start hook, replacing libvirt's "
                                  f"inherited fd)"))
        else:
            out.append(("error", "netdev still uses libvirt's inherited file "
                                 "descriptor and no tap is configured to replace it"))

    # --- hugepage directory ---------------------------------------------------
    ram = next((o for o in cfg.objects if o.get("id") == "pc.ram"), None)
    mp = (ram or {}).get("mem-path")
    if mp and not os.path.isdir(mp) and cfg.profile != "macos":
        # The start hook creates the directory and mounts a hugetlbfs on it, so
        # the only thing that can stop that is a read-only parent to mkdir into.
        parent = os.path.dirname(mp)
        while parent and not os.path.isdir(parent):
            parent = os.path.dirname(parent)
        if _read_only_fs(parent or "/"):
            out.append(("error", f"{mp} does not exist and its parent {parent} is "
                                 f"read-only, so the start hook cannot create it"))
        else:
            out.append(("ok", f"{mp} will be created and mounted by the start hook"))

    # --- server sockets -------------------------------------------------------
    for sk in _server_sockets(cfg):
        if not os.path.exists(sk):
            continue
        busy = subprocess.run(["fuser", sk], capture_output=True).returncode == 0
        if busy:
            out.append(("error", f"{sk} is in use by a running process; a VM may "
                                 f"already be running"))
        else:
            out.append(("warn", f"stale socket {sk} will be removed by the start hook"))

    # --- hooks ---------------------------------------------------------------
    for key, path in (("start", START), ("revert", REVERT)):
        if not os.path.isfile(path):
            out.append(("ok", f"{key}.sh will be generated from the config"))
            continue
        r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        if r.returncode != 0:
            # A hand-edited hook with a syntax error would abort the launch
            # halfway, and for start.sh that means after the display is gone.
            last = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "?"
            out.append(("error", f"{key}.sh has a syntax error: {last}"))
        else:
            edited = _sha(open(path).read()) != _stamps().get(key, "")
            out.append(("ok", f"{key}.sh ok"
                              + (" (hand-edited, used as-is)" if edited else "")))

    if os.geteuid() != 0 and not _can_sudo():
        out.append(("error", "passwordless sudo is not available; the launch needs "
                             "root to stop the display manager and rebind the GPU"))

    return out


def _hugetlbfs_mount(path):
    """(mount, pagesize) of the hugetlbfs filesystem containing path."""
    best = None
    try:
        for line in open("/proc/mounts"):
            parts = line.split()
            if len(parts) < 4 or parts[2] != "hugetlbfs":
                continue
            m = parts[1].rstrip("/") or "/"
            if path == m or path.startswith(m + "/"):
                size = None
                mm = re.search(r"pagesize=(\d+)([KMG]?)", parts[3])
                if mm:
                    mult = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}[mm.group(2)]
                    size = int(mm.group(1)) * mult
                if best is None or len(m) > len(best[0]):
                    best = (parts[1], size)
    except Exception:
        pass
    return best


def _read_only_fs(path):
    try:
        return bool(os.statvfs(path).f_flag & os.ST_RDONLY)
    except Exception:
        return False


def _can_sudo():
    try:
        return subprocess.run(["sudo", "-n", "true"], capture_output=True,
                              timeout=5).returncode == 0
    except Exception:
        return False


# -------------------------------------------------------------------- hooks ---
# start.sh and revert.sh are the two halves that used to live in
# /etc/libvirt/hooks. They are generated once from the config and then belong to
# the user: launch.sh only ever calls them, so editing them does not get
# overwritten on the next launch.
START = os.path.join(RUN_DIR, "start.sh")
REVERT = os.path.join(RUN_DIR, "revert.sh")
STAMP = os.path.join(RUN_DIR, ".hooks.json")
# Where start.sh parks the host's own sched_rt_runtime_us so revert.sh can put
# it back. A file rather than a variable because the two halves are separate
# scripts run by separate shells.
RT_SAVED = os.path.join(RUN_DIR, ".sched_rt_runtime_us")

# Length of one RT scheduling period in microseconds. This is
# kernel.sched_rt_period_us, which vmstart_2 does not touch, so a quota is
# always read against this.
RT_PERIOD_US = 1000000


def rt_runtime(pinning):
    """The sched_rt_runtime_us the config asks for, or None for 'leave it'.

    Absent from the config means -1: that is what the script did before this
    was settable, and a session saved back then must keep launching the way it
    always did.
    """
    if "rt_runtime_us" not in pinning:
        return -1
    v = pinning.get("rt_runtime_us")
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return -1


def _rt_percent(value):
    """' (95% of each period)' for a quota, '' for -1 or anything unreadable."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return ""
    if v < 0:
        return ""
    return f" ({v * 100 / RT_PERIOD_US:g}% of each period)"


def rt_wanted(pinning):
    """Whether any thread class is being asked for a real-time policy."""
    scheds = {pinning.get(k, {}).get("scheduler")
              for k in ("vcpusched", "emulatorsched", "iothreadsched")}
    return bool(scheds & {"fifo", "rr"})


def _gpu_slots(cfg):
    return [d.get("host") for d in cfg.devices
            if d.get("driver") == "vfio-pci" and not d.get("_disabled")]


def iothread_ids(cfg):
    """The live '-object iothread' ids, in command line order."""
    return [o.get("id") for o in cfg.objects
            if o.get("qom-type") == "iothread" and not o.get("_disabled") and o.get("id")]


def _iothread_pins(cfg, pinning):
    """(iothread id, cpuset) for each iothread the config actually creates.

    The cpusets come from the pinning plan, which computes one per I/O thread.
    Pairing is positional against the objects that exist, so if the two ever
    disagree -- a hand-edited config, an object added on the Machine tab --
    the extras fall through to the emulator pass instead of being pinned to a
    cpuset nobody asked for.
    """
    pins = [str(c).strip() for c in (pinning.get("iothreadpin") or []) if str(c).strip()]
    return list(zip(iothread_ids(cfg), pins))


def _qmp_path(cfg, standalone=True):
    """The QMP unix socket path, for the stuck-shutdown watcher."""
    for a in cfg.to_argv(standalone):
        if isinstance(a, str) and a.startswith("unix:") and "server" in a:
            return a[5:].split(",")[0]
    return ""


def _server_sockets(cfg, standalone=True):
    """Unix sockets QEMU binds as a server (monitor, QMP).

    bind() fails with EADDRINUSE on a leftover socket file and QEMU does not
    unlink first, so an unclean exit breaks the *next* launch.
    """
    out = []
    for a in cfg.to_argv(standalone):
        if not isinstance(a, str):
            continue
        if "server" in a:
            m = re.search(r"path=([^,]+)", a)
            if m:
                out.append(m.group(1))
        m = re.match(r"unix:([^,]+),.*server", a)
        if m:
            out.append(m.group(1))
    return sorted(set(out))


def _tpm(cfg):
    """(socket path, state dir, swtpm binary) if the guest has an emulated TPM.

    libvirt used to start swtpm as part of domain startup. Nothing else does,
    so a libvirt-free launch has to start it too or QEMU dies on connect.
    """
    tpmdev = cfg.simple.get("tpmdev", "")
    if "emulator" not in tpmdev:
        return None
    m = re.search(r"chardev=([^,]+)", tpmdev)
    if not m:
        return None
    chardev = next((c for c in cfg.data.get("chardevs", [])
                    if c.get("id") == m.group(1)), None)
    if not chardev or not chardev.get("path"):
        return None
    tools = cfg.data.get("tools", {})
    state = tools.get("swtpm_state") or ""
    if not state:
        uuid = cfg.simple.get("uuid", "")
        if uuid:
            state = f"/var/lib/libvirt/swtpm/{uuid}/tpm2"
    return {"sock": chardev["path"], "state": state,
            "binary": tools.get("swtpm_binary") or "/usr/bin/swtpm"}


def _hugepages(cfg):
    """(pages, page size, sysfs pool path) for the configured guest RAM.

    The page size comes from the explicit memory settings, not from guessing at
    mem-path. And the pool is written through its own sysfs node rather than
    /proc/sys/vm/nr_hugepages, which only ever addresses the default size: a 1G
    request through that path silently allocates 2M pages instead.
    """
    ram = next((o for o in cfg.objects if o.get("id") == "pc.ram"), None)
    mem = cfg.data.get("memory", {})
    if mem:
        if not mem.get("hugepages"):
            return 0, 0, ""
        psize = int(mem.get("pagesize") or 2 * 1024 * 1024)
    else:
        if not (ram and ram.get("mem-path")):
            return 0, 0, ""
        psize = 1024 ** 3 if "1G" in str(ram.get("mem-path", "")) else 2 * 1024 * 1024
    want = int((ram or {}).get("size") or 0)
    if not want:
        return 0, 0, ""
    sysfs = f"/sys/kernel/mm/hugepages/hugepages-{psize // 1024}kB/nr_hugepages"
    return want // psize, psize, sysfs


def _mac_memory_guard(cfg):
    """Read-only runtime recheck before any existing handoff hook runs."""
    if cfg.profile != "macos":
        return []
    command = shlex.join([sys.executable, os.path.join(APP_DIR, "lib", "mac_memory.py"),
                          "--spec", json.dumps(mac_memory.spec(cfg), separators=(",", ":"))])
    return [command + " || exit 1"]


def _mac_temporary_memory(cfg):
    return cfg.profile == "macos" and mac_memory.temporary(cfg.data)


def _mac_memory_prepare(cfg):
    """Own temporary pages in launch.sh; leave the GPU hooks' work unchanged."""
    if not _mac_temporary_memory(cfg):
        return []
    helper = shlex.join([sys.executable, os.path.join(APP_DIR, "lib", "mac_hugepages.py")])
    spec = shlex.quote(json.dumps(mac_memory.spec(cfg), separators=(",", ":")))
    return [
        'MAC_HP_TOKEN="$$-$(date +%s%N)"',
        'mac_hp_release() {',
        f'    {helper} --release --token "$MAC_HP_TOKEN" || log "Hugepage cleanup needs a retry; see macos/run/.temporary-hugepages.json"',
        '}',
        'trap mac_hp_release EXIT',
        "trap 'exit 130' INT",
        "trap 'exit 143' TERM",
        f'{helper} --prepare --spec {spec} --token "$MAC_HP_TOKEN" --owner "$$" || exit 1',
    ]


def build_start(cfg, pinning):
    """Everything that happens before QEMU: memory, module, GPU handoff."""
    pages, psize, sysfs = _hugepages(cfg)
    slots = _gpu_slots(cfg)
    tools = cfg.data.get("tools", {})

    L = []
    a = L.append
    a("#!/usr/bin/env bash")
    a("#")
    a("# vmstart_2 start hook. Generated from the config, then yours to edit:")
    a("# launch.sh only calls this, and will not overwrite it once you change it.")
    a("# Use 'Regenerate from config' in the Launch Procedure tab to get a fresh copy.")
    a("#")
    a("# Runs as root. Exit non-zero to abort the launch; nothing is torn down")
    a("# until the display manager section below, so an early failure is free.")
    a("set -uo pipefail")
    a("")
    a('DM_SERVICE="${DM_SERVICE:-sddm.service}"')
    a('log() { echo "[$(date +%H:%M:%S)] [start] $*"; }')
    a("")
    L.extend(_mac_memory_guard(cfg))
    # ------------------------------------------------------ stale state --
    # Everything a previous run could have left behind, cleared before any of
    # it can make this launch fail in a confusing way. A reset button pressed
    # mid-flight leaves all of this lying around.
    a("# ------------------------------------------------------- stale state --")
    # A marker left over from a run that was reset mid-flight would tell the
    # revert hook there is a display to restore when there is not.
    a(f'rm -f {shlex.quote(os.path.join(RUN_DIR, ".handover"))}')
    # Likewise a parked sched_rt_runtime_us: if this launch does not change the
    # value, the revert hook must not "restore" one an abandoned run saved.
    a(f'rm -f {shlex.quote(RT_SAVED)}')
    a("")
    a('STALE=$(pgrep -f "qemu-system-x86_64.*guest=" 2>/dev/null || true)')
    a('if [[ -n "$STALE" ]]; then')
    a('    log "a previous QEMU is still running:"')
    a('    ps -o pid=,etime=,args= -p $STALE 2>/dev/null | cut -c1-120 | sed "s/^/    /"')
    a('    log "refusing to start a second VM on the same disks and GPU"')
    a("    exit 1")
    a("fi")
    a("")
    tpm = _tpm(cfg)
    if tpm:
        a(f'if [[ -S {shlex.quote(tpm["sock"])} ]] || pgrep -f "swtpm.*{tpm["sock"]}" >/dev/null 2>&1; then')
        a('    log "clearing a stale swtpm"')
        a(f'    pkill -f "swtpm.*{tpm["sock"]}" 2>/dev/null || true')
        a("    sleep 0.5")
        a(f'    rm -f {shlex.quote(tpm["sock"])}')
        a("fi")
    net = cfg.data.get("network") or {}
    if net.get("ifname"):
        a(f'if ip link show {shlex.quote(net["ifname"])} >/dev/null 2>&1; then')
        a(f'    log "removing a stale tap {net["ifname"]}"')
        a(f'    ip link set {shlex.quote(net["ifname"])} down 2>/dev/null || true')
        a(f'    ip tuntap del dev {shlex.quote(net["ifname"])} mode tap 2>/dev/null || true')
        a("fi")
    # A GPU left on vfio-pci by an interrupted run has to go back to its host
    # driver first, or the module unload below fails and the handover never
    # completes.
    for slot in _gpu_slots(cfg):
        a(f'CUR=$(basename "$(readlink -f /sys/bus/pci/devices/{slot}/driver 2>/dev/null)" 2>/dev/null)')
        a(f'if [[ "$CUR" == "vfio-pci" ]]; then')
        a(f'    log "{slot} was left on vfio-pci by an earlier run; releasing it"')
        a(f'    echo "" > /sys/bus/pci/devices/{slot}/driver_override 2>/dev/null || true')
        a(f'    echo {slot} > /sys/bus/pci/drivers/vfio-pci/unbind 2>/dev/null || true')
        a("fi")
    a("echo 1 > /sys/bus/pci/rescan 2>/dev/null || true")
    a("")

    if pages and cfg.profile != "macos":
        human = f"{psize // 1024 // 1024} MiB" if psize < 1024 ** 3 else f"{psize // 1024 ** 3} GiB"
        a("# ----------------------------------------------------------- memory --")
        a(f'POOL={shlex.quote(sysfs)}')
        a(f'log "allocating {pages} x {human} hugepages ({pages * psize // 1024**3} GiB)"')
        a('if [[ ! -w "$POOL" ]]; then')
        a(f'    log "no {human} hugepage pool at $POOL; aborting"')
        a("    exit 1")
        a("fi")
        # Writing the pool size is best effort: under fragmentation the kernel
        # hands back fewer than asked and says nothing, and QEMU then dies after
        # the display manager is already gone. So free page cache and actively
        # compact memory between attempts, and retry a few times before giving
        # up — 2 MiB pages fragment easily on a host that has been up a while.
        a(f'GOT=0')
        a(f'for attempt in 1 2 3 4; do')
        a(f'    echo {pages} > "$POOL" 2>/dev/null || true')
        a(f'    GOT=$(cat "$POOL")')
        a(f'    [[ "$GOT" -ge {pages} ]] && break')
        a(f'    log "attempt $attempt: got $GOT of {pages}; compacting memory and retrying"')
        a('    sync')
        a('    echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true')
        a('    echo 1 > /proc/sys/vm/compact_memory 2>/dev/null || true')
        a('    sleep 1')
        a("done")
        a(f'if [[ "$GOT" -lt {pages} ]]; then')
        a(f'    log "only got $GOT of {pages} after compaction; memory too fragmented."')
        a(f'    log "free some RAM (close apps) and retry, allocate hugepages at boot,"')
        a(f'    log "or switch to 1 GiB pages, which do not fragment. Aborting."')
        a("    exit 1")
        a("fi")
        a('log "hugepages ok: $GOT"')
        a("")

    rt = rt_runtime(pinning)
    if rt_wanted(pinning) and rt is not None:
        a("# ------------------------------------------------------- scheduling --")
        # The old value is parked first so the revert hook can put it back. A
        # clean shutdown reboots the host anyway, but a failed start and a
        # NO_REBOOT run both come back to a live desktop, and leaving RT
        # throttling off there means one runaway RT thread can wedge it.
        a(f'RT_SAVED={shlex.quote(RT_SAVED)}')
        a('cat /proc/sys/kernel/sched_rt_runtime_us > "$RT_SAVED" 2>/dev/null || true')
        if rt < 0:
            a('log "disabling RT throttling"')
        else:
            a(f'log "setting RT throttling to {rt} us of each {RT_PERIOD_US} us period"')
        a(f"echo {rt} > /proc/sys/kernel/sched_rt_runtime_us")
        a("")

    kvm = tools.get("kvm_build", "")
    if tools.get("kvm_build_enabled") and kvm:
        a("# ------------------------------------------------------- kvm module --")
        # The module cannot be swapped while anything holds it. Catch that here
        # with a clear message instead of letting the build fail with a bare
        # PID, and before anything is torn down.
        a('HOLDERS=$(lsmod | awk \'$1=="kvm_amd"{print $3}\')')
        a('if [[ "${HOLDERS:-0}" != "0" ]]; then')
        a('    log "kvm_amd is in use by $HOLDERS process(es); cannot rebuild it"')
        a('    pgrep -a qemu-system 2>/dev/null | sed "s/^/    /" || true')
        a('    log "stop any running VM first, or untick the module build on Paths & Tools"')
        a("    exit 1")
        a("fi")
        for k, v in sorted((tools.get("kvm_env") or {}).items()):
            if str(v) != "":
                a(f"export {k}={shlex.quote(str(v))}")
        args = tools.get("kvm_build_args", "").strip()
        a(f'log "building KVM module: {os.path.basename(kvm)}"')
        a(f'if ! bash {shlex.quote(kvm)}{" " + args if args else ""}; then')
        a('    log "module build failed; nothing torn down yet"')
        a("    exit 1")
        a("fi")
        for k in ("intercept_cpuid", "intercept_vmmcall", "intercept_svm_insn_gp"):
            a(f'[[ -r /sys/module/kvm_amd/parameters/{k} ]] && '
              f'log "  {k}=$(cat /sys/module/kvm_amd/parameters/{k})"')
        a("")

    socks = _server_sockets(cfg)
    if socks:
        a("# --------------------------------------------------- stale sockets --")
        a("# QEMU binds these and will not unlink a leftover file first, so an")
        a("# unclean exit would break the next launch with EADDRINUSE.")
        for sk in socks:
            a(f'if [[ -e {shlex.quote(sk)} ]]; then')
            a(f'    if fuser {shlex.quote(sk)} >/dev/null 2>&1; then')
            a(f'        log "{sk} is in use by a running process; is a VM already up?"')
            a("        exit 1")
            a("    fi")
            a(f'    log "removing stale socket {sk}"')
            a(f'    rm -f {shlex.quote(sk)}')
            a("fi")
        a("")

    ram = next((o for o in cfg.objects if o.get("id") == "pc.ram"), None)
    mp = (ram or {}).get("mem-path")
    if mp and cfg.profile != "macos":
        a("# -------------------------------------------------- hugepage dir --")
        # libvirt made this per-domain directory on the hugetlbfs mount and
        # removed it afterwards. QEMU will not create it itself.
        psz = f"{psize // 1024**3}G" if psize >= 1024 ** 3 else f"{psize // 1024 // 1024}M"
        a(f'MEM_PATH={shlex.quote(mp)}')
        a('if [[ ! -d "$MEM_PATH" ]]; then')
        a('    log "creating $MEM_PATH"')
        a('    mkdir -p "$MEM_PATH" || { log "could not create $MEM_PATH"; exit 1; }')
        a("fi")
        # If the path is not already on hugetlbfs, mount a dedicated one there.
        # Many hosts (this custom install included) have no persistent hugetlbfs
        # mount, so the guest would silently get ordinary pages. A private mount
        # per launch is self-contained and torn down again by the revert hook.
        a('if ! findmnt -no FSTYPE -T "$MEM_PATH" | grep -q hugetlbfs; then')
        a(f'    log "mounting hugetlbfs at $MEM_PATH (pagesize {psz})"')
        a(f'    mount -t hugetlbfs -o pagesize={psz} hugetlbfs "$MEM_PATH" \\')
        a('        || { log "could not mount hugetlbfs at $MEM_PATH"; exit 1; }')
        a("fi")
        a('log "mem-path $MEM_PATH is on $(findmnt -no FSTYPE -T "$MEM_PATH")"')
        a("")

    net = cfg.data.get("network") or {}
    if net.get("mode") == "tap" and net.get("ifname"):
        a("# ------------------------------------------------------ networking --")
        # The command line references this tap by name, so it has to exist and
        # be on the bridge before QEMU opens it.
        a(f'TAP={shlex.quote(net["ifname"])}')
        a(f'BRIDGE={shlex.quote(net.get("bridge") or "")}')
        a('if ip link show "$TAP" >/dev/null 2>&1; then')
        a('    log "reusing existing tap $TAP"')
        a("else")
        a('    log "creating tap $TAP"')
        a('    ip tuntap add dev "$TAP" mode tap || { log "tap creation failed"; exit 1; }')
        a("fi")
        a('if [[ -n "$BRIDGE" ]]; then')
        a('    if ! ip link show "$BRIDGE" >/dev/null 2>&1; then')
        a('        log "bridge $BRIDGE does not exist"')
        a("        exit 1")
        a("    fi")
        a('    ip link set "$TAP" master "$BRIDGE" || { log "could not enslave $TAP to $BRIDGE"; exit 1; }')
        a("fi")
        a('ip link set "$TAP" up || { log "could not bring $TAP up"; exit 1; }')
        a('log "tap $TAP up on ${BRIDGE:-no bridge}"')
        a("")

    tpm = _tpm(cfg)
    if tpm:
        a("# ---------------------------------------------------------- swtpm --")
        # Before the display teardown on purpose. QEMU connects to this socket
        # at startup, and if it is missing QEMU exits immediately -- which,
        # when the desktop is already gone, means a black screen and no way to
        # read the error.
        a(f'SWTPM={shlex.quote(tpm["binary"])}')
        a(f'TPM_SOCK={shlex.quote(tpm["sock"])}')
        a(f'TPM_STATE={shlex.quote(tpm["state"])}')
        a('log "starting swtpm on $TPM_SOCK"')
        a('if [[ ! -x "$SWTPM" ]]; then log "swtpm not executable: $SWTPM"; exit 1; fi')
        a('if [[ ! -d "$TPM_STATE" ]]; then log "TPM state dir missing: $TPM_STATE"; exit 1; fi')
        a('mkdir -p "$(dirname "$TPM_SOCK")"')
        a('if [[ -S "$TPM_SOCK" ]]; then')
        a('    log "stale socket present, removing"')
        a('    pkill -f "swtpm.*$TPM_SOCK" 2>/dev/null || true')
        a('    rm -f "$TPM_SOCK"')
        a("fi")
        a('"$SWTPM" socket --daemon --tpm2 \\')
        a('    --tpmstate dir="$TPM_STATE",mode=0600 \\')
        a('    --ctrl type=unixio,path="$TPM_SOCK",mode=0600 \\')
        a(f'    --pid file={shlex.quote(os.path.join(RUN_DIR, "swtpm.pid"))} \\')
        a(f'    --log file={shlex.quote(os.path.join(RUN_DIR, "swtpm.log"))},level=1 \\')
        a('    --terminate')
        a('for _ in $(seq 1 50); do [[ -S "$TPM_SOCK" ]] && break; sleep 0.1; done')
        a('if [[ ! -S "$TPM_SOCK" ]]; then')
        a('    log "swtpm never created $TPM_SOCK; see run/swtpm.log"')
        a("    exit 1")
        a("fi")
        a('log "swtpm ready (pid $(cat ' + shlex.quote(os.path.join(RUN_DIR, "swtpm.pid")) + ' 2>/dev/null))"')
        a("")

    if slots:
        a("# ------------------------------------------------------ gpu handoff --")
        a("# Past this point the desktop is gone. Everything above can fail safely.")
        # The marker is what tells revert.sh that there is something to undo.
        # Without it revert would rip the GPU away from a desktop that start.sh
        # never touched, turning an early, harmless abort into a black screen.
        a(f'mkdir -p {shlex.quote(RUN_DIR)}')
        a(f'touch {shlex.quote(os.path.join(RUN_DIR, ".handover"))}')
        a('log "stopping display manager"')
        a('systemctl stop "$DM_SERVICE" || true')
        a("sleep 1")
        a("killall -9 kwin_x11 kwin_wayland plasmashell Xorg Xwayland gnome-shell picom 2>/dev/null || true")
        a("systemctl stop nvidia-persistenced.service nvidia-powerd.service 2>/dev/null || true")
        a("fuser -k /dev/nvidia* 2>/dev/null || true")
        a("sleep 1")
        a('log "unbinding consoles and framebuffer"')
        a("echo 0 > /sys/class/vtconsole/vtcon0/bind 2>/dev/null || true")
        a("echo 0 > /sys/class/vtconsole/vtcon1/bind 2>/dev/null || true")
        a("echo efi-framebuffer.0 > /sys/bus/platform/drivers/efi-framebuffer/unbind 2>/dev/null || true")
        a("sleep 2")
        a('log "unloading NVIDIA modules"')
        a("modprobe -r nvidia_drm nvidia_modeset nvidia_uvm nvidia 2>/dev/null || true")
        a("modprobe -r nouveau 2>/dev/null || true")
        a("sleep 1")
        a('log "loading vfio"')
        a("modprobe vfio || true")
        a("modprobe vfio_iommu_type1 || true")
        a("modprobe vfio-pci || true")
        a("for _ in $(seq 1 50); do [[ -e /dev/vfio/vfio ]] && break; sleep 0.1; done")
        a('[[ -e /dev/vfio/vfio ]] || { log "/dev/vfio/vfio never appeared"; exit 1; }')
        a("")
        # Plain sysfs rather than virsh nodedev-detach: this app does not depend
        # on libvirt being installed or running.
        for slot in slots:
            a(f'log "binding {slot} to vfio-pci"')
            a(f"if [[ -e /sys/bus/pci/devices/{slot}/driver ]]; then")
            a(f"    echo {slot} > /sys/bus/pci/devices/{slot}/driver/unbind 2>/dev/null || true")
            a("fi")
            a(f"echo vfio-pci > /sys/bus/pci/devices/{slot}/driver_override")
            a(f"echo {slot} > /sys/bus/pci/drivers_probe 2>/dev/null || true")
            a(f'DRV=$(basename "$(readlink -f /sys/bus/pci/devices/{slot}/driver 2>/dev/null)" 2>/dev/null)')
            a(f'if [[ "$DRV" != "vfio-pci" ]]; then')
            a(f'    log "{slot} bound to ${{DRV:-nothing}}, not vfio-pci"')
            a("    exit 1")
            a("fi")
        a("")

    a('log "start hook complete"')
    a("exit 0")
    return "\n".join(L) + "\n"


def build_revert(cfg, reboot_after=True):
    """Everything after QEMU exits."""
    slots = _gpu_slots(cfg)
    tpm = _tpm(cfg)
    L = []
    a = L.append
    a("#!/usr/bin/env bash")
    a("#")
    a("# vmstart_2 revert hook. Generated from the config, then yours to edit.")
    a("# Called by launch.sh once QEMU exits, and also if the start hook fails")
    a("# after the display was already taken down.")
    a("#")
    a("#   $1 = 'ok'     the guest ran and shut down normally")
    a("#        'failed' QEMU never started, or died during startup")
    a("#")
    a("set -uo pipefail")
    a("")
    a('REASON="${1:-ok}"')
    a('DM_SERVICE="${DM_SERVICE:-sddm.service}"')
    a('NO_REBOOT="${NO_REBOOT:-/etc/libvirt/hooks/NO_REBOOT_AFTER_VM}"')
    a('log() { echo "[$(date +%H:%M:%S)] [revert] $*"; }')
    a("")

    if reboot_after:
        # Request the normal host reboot before cleanup can rebind the GPU or
        # consoles. This hook already runs as root under vmstart2-vm.service.
        a("# Normal guest shutdown: reboot before restoring any host devices.")
        a('if [[ "$REASON" == "ok" && ! -e "$NO_REBOOT" ]]; then')
        a('    log "guest shut down normally; rebooting host now"')
        a("    exec systemctl reboot")
        a("fi")
        a("")

    for sk in _server_sockets(cfg):
        a(f'rm -f {shlex.quote(sk)} 2>/dev/null || true')

    # Tear down the private hugetlbfs the start hook mounted for the guest's
    # RAM. Only unmount if this path is its OWN mountpoint (mountpoint -q is
    # false for a subdir of a pre-existing hugetlbfs, which we must not touch).
    ram = next((o for o in cfg.objects if o.get("id") == "pc.ram"), None)
    mp = (ram or {}).get("mem-path")
    if mp and cfg.profile != "macos":
        a("# --------------------------------------------------- hugepage mount --")
        a(f'MEM_PATH={shlex.quote(mp)}')
        a('if mountpoint -q "$MEM_PATH" 2>/dev/null; then')
        a('    log "unmounting hugetlbfs at $MEM_PATH"')
        a('    umount "$MEM_PATH" 2>/dev/null || true')
        a("fi")
        a("")

    net = cfg.data.get("network") or {}
    if net.get("mode") == "tap" and net.get("ifname"):
        a("# ------------------------------------------------------ networking --")
        a(f'TAP={shlex.quote(net["ifname"])}')
        a('if ip link show "$TAP" >/dev/null 2>&1; then')
        a('    log "removing tap $TAP"')
        a('    ip link set "$TAP" down 2>/dev/null || true')
        a('    ip tuntap del dev "$TAP" mode tap 2>/dev/null || true')
        a("fi")
        a("")

    if tpm:
        a("# ---------------------------------------------------------- swtpm --")
        a(f'TPM_SOCK={shlex.quote(tpm["sock"])}')
        a('if [[ -S "$TPM_SOCK" ]]; then')
        a('    log "stopping swtpm"')
        a('    pkill -f "swtpm.*$TPM_SOCK" 2>/dev/null || true')
        a('    rm -f "$TPM_SOCK"')
        a("fi")
        a("")

    # --------------------------------------------------------------------
    # Above the handover gate on purpose. The start hook writes
    # sched_rt_runtime_us long before it touches the display, so a start that
    # aborts in between never reaches the gate -- and that is exactly the run
    # that comes back to a live desktop with RT throttling still off.
    #
    # Guarded on the file rather than on the config: whether the value was
    # changed at all is start.sh's decision, and start.sh is the user's to
    # edit once it is generated.
    a("# ------------------------------------------------------- scheduling --")
    a(f'RT_SAVED={shlex.quote(RT_SAVED)}')
    a('if [[ -s "$RT_SAVED" ]]; then')
    a('    RT_WAS=$(cat "$RT_SAVED")')
    a('    log "restoring sched_rt_runtime_us to $RT_WAS"')
    a('    echo "$RT_WAS" > /proc/sys/kernel/sched_rt_runtime_us 2>/dev/null || true')
    a('    rm -f "$RT_SAVED"')
    a("fi")
    a("")

    marker = os.path.join(RUN_DIR, ".handover")
    a(f'HANDOVER={shlex.quote(marker)}')
    a('if [[ ! -e "$HANDOVER" ]]; then')
    # start.sh aborts before the display teardown for every failure it can
    # detect. In that case the desktop and the GPU are untouched and there is
    # nothing here to undo -- doing it anyway is what breaks a working session.
    a('    log "start hook never reached the GPU handover; nothing to restore"')
    a('    exit 0')
    a("fi")
    a('rm -f "$HANDOVER"')
    a("")

    # Only failed starts and explicit desktop-restore requests reach this path.
    a("# ------------------------------------------------- restore the host --")
    a('log "rebinding GPU to host drivers"')
    for slot in slots:
        # Only take a device back off vfio-pci. If it is on nvidia it is
        # driving the host display right now.
        a(f'CUR=$(basename "$(readlink -f /sys/bus/pci/devices/{slot}/driver 2>/dev/null)" 2>/dev/null)')
        a(f'if [[ "$CUR" == "vfio-pci" ]]; then')
        a(f'    echo "" > /sys/bus/pci/devices/{slot}/driver_override 2>/dev/null || true')
        a(f'    echo {slot} > /sys/bus/pci/devices/{slot}/driver/unbind 2>/dev/null || true')
        a("else")
        a(f'    log "  {slot} is on ${{CUR:-nothing}}, not vfio-pci; leaving it alone"')
        a("fi")
    a("sleep 1")
    for slot in slots:
        a(f'echo {slot} > /sys/bus/pci/drivers_probe 2>/dev/null || true')
    a("echo 1 > /sys/bus/pci/rescan 2>/dev/null || true")
    a("sleep 1")
    a('log "loading NVIDIA modules"')
    a("modprobe nvidia 2>/dev/null || true")
    a("modprobe nvidia_modeset 2>/dev/null || true")
    a("modprobe nvidia_uvm 2>/dev/null || true")
    a("modprobe nvidia_drm 2>/dev/null || true")
    a("sleep 1")
    a('log "rebinding consoles"')
    a("echo 1 > /sys/class/vtconsole/vtcon0/bind 2>/dev/null || true")
    a("echo 1 > /sys/class/vtconsole/vtcon1/bind 2>/dev/null || true")
    for slot in slots:
        a(f'DRV=$(basename "$(readlink -f /sys/bus/pci/devices/{slot}/driver 2>/dev/null)" 2>/dev/null)')
        a(f'log "  {slot} -> ${{DRV:-unbound}}"')
    a("")

    a("# ------------------------------------------------------- what next --")
    # A failed start means the user has never seen an error message: the
    # desktop went away before QEMU printed anything. Rebooting there destroys
    # the only copy of why it failed. Bring the display back instead.
    a('if [[ "$REASON" != "ok" ]]; then')
    a('    log "the guest never ran; restoring the display so the error is readable"')
    a('    systemctl start "$DM_SERVICE" 2>/dev/null || true')
    a('    log "see the launch log for what failed"')
    a("    exit 0")
    a("fi")
    a("")
    if reboot_after:
        a('log "$NO_REBOOT present; restarting the display manager instead"')
    a('systemctl start "$DM_SERVICE" 2>/dev/null || true')
    a('log "revert hook complete"')
    a("exit 0")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------ hook storage ---
def _sha(text):
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()


def _stamps():
    if os.path.isfile(STAMP):
        try:
            return json.load(open(STAMP))
        except Exception:
            pass
    return {}


def hook_state(cfg, pinning, reboot_after=True):
    """For each hook: does it exist, and has the user edited it?

    'Edited' means the file no longer matches the text vmstart_2 last wrote.
    That is the whole reason a stamp file exists: without it, regenerating
    would silently throw away hand-written changes.
    """
    st = _stamps()
    out = {}
    for key, path, fresh in (("start", START, build_start(cfg, pinning)),
                             ("revert", REVERT, build_revert(cfg, reboot_after))):
        exists = os.path.isfile(path)
        cur = open(path).read() if exists else ""
        out[key] = {
            "path": path,
            "exists": exists,
            "current": cur,
            "generated": fresh,
            "edited": exists and _sha(cur) != st.get(key, ""),
            "stale": exists and _sha(cur) == st.get(key, "") and cur != fresh,
        }
    return out


def write_hooks(cfg, pinning, reboot_after=True, force=False, keys=None):
    """Create the hooks. Never clobbers a hand-edited file unless force.

    keys limits which hooks are touched. force applies only to those, so
    regenerating one hook cannot quietly rewrite the other -- which it did once,
    destroying a hand edit in start.sh while the user was regenerating revert.sh.
    """
    os.makedirs(RUN_DIR, exist_ok=True)
    st = _stamps()
    state = hook_state(cfg, pinning, reboot_after)
    written = []
    for key in (keys or ("start", "revert")):
        s = state[key]
        if s["exists"] and s["edited"] and not force:
            continue
        if s["exists"] and not force and not s["stale"]:
            continue
        with open(s["path"], "w") as f:
            f.write(s["generated"])
        # 0775 so the file can be edited without sudo and still executed.
        os.chmod(s["path"], 0o775)
        st[key] = _sha(s["generated"])
        written.append(s["path"])
    with open(STAMP, "w") as f:
        json.dump(st, f, indent=2)
    return written


def save_hook(key, text, generated=False):
    """Write a hook.

    generated=True stamps it as vmstart_2's own output, so it reads as
    'matches config' rather than 'edited by you'. Anything the user typed must
    leave the stamp alone or their edit stops being recognised as theirs.
    """
    path = START if key == "start" else REVERT
    os.makedirs(RUN_DIR, exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    os.chmod(path, 0o775)
    if generated:
        st = _stamps()
        st[key] = _sha(text)
        with open(STAMP, "w") as f:
            json.dump(st, f, indent=2)
    return path


# ------------------------------------------------------------------ script ---
def build_script(cfg, pinning, standalone=True, reboot_after=True):
    """The generated part: banner, hooks, QEMU, post-start pinning.

    Only this file is rewritten on every launch, because only this part is
    derived from the config. The hooks it calls are the user's.
    """
    argv = cfg.to_argv(standalone)
    binary = argv[0]

    L = []
    a = L.append
    a("#!/usr/bin/env bash")
    a("#")
    a("# Generated by vmstart_2 on every launch. Do not edit: change the config,")
    a("# or edit run/start.sh and run/revert.sh, which this only calls.")
    a("set -uo pipefail")
    a("")
    a(f"LOG={shlex.quote(LOG)}")
    a(f"START={shlex.quote(START)}")
    a(f"REVERT={shlex.quote(REVERT)}")
    a('exec > >(tee -a "$LOG") 2>&1')
    a('log() { echo "[$(date +%H:%M:%S)] $*"; }')
    a("")
    # The banner is what makes the log readable across runs: one obvious marker
    # per launch, so a failure can be traced to the attempt that produced it.
    a('echo ""')
    a('echo "=============== VM STARTED $(date "+%d %m %y %H:%M") ==========================="')
    a('log "config: $(hostname) | $(uname -r)"')
    a("")
    L.extend(_mac_memory_prepare(cfg))
    L.extend(_mac_memory_guard(cfg))
    a("REVERTED=0")
    a("do_revert() {")
    a('    [[ "$REVERTED" == 1 ]] && return')
    a("    REVERTED=1")
    if _mac_temporary_memory(cfg):
        a('    mac_hp_release')  # Revert may immediately reboot the host.
    a('    if [[ -x "$REVERT" ]]; then')
    a('        bash "$REVERT" "${1:-ok}"')
    a("    else")
    a('        log "revert hook missing: $REVERT"')
    a("    fi")
    a("}")
    a("")
    a("# ------------------------------------------------------------- start --")
    a('if [[ ! -x "$START" ]]; then')
    a('    log "start hook missing: $START"')
    a('    echo "=============== VM ABORTED  $(date "+%d %m %y %H:%M") ==========================="')
    a("    exit 1")
    a("fi")
    a('if ! bash "$START"; then')
    a('    log "start hook failed"')
    a("    do_revert failed")
    a('    echo "=============== VM ABORTED  $(date "+%d %m %y %H:%M") ==========================="')
    a("    exit 1")
    a("fi")
    a("")
    a("# -------------------------------------------------------------- qemu --")
    a('log "starting QEMU"')
    a("")
    a(f"{shlex.quote(binary)} \\")
    i, lines = 1, []
    while i < len(argv):
        arg = argv[i]
        if arg.startswith("-") and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            lines.append(f"  {arg} {shlex.quote(argv[i + 1])}")
            i += 2
        else:
            lines.append(f"  {arg}")
            i += 1
    a(" \\\n".join(lines) + " &")
    a("QEMU_PID=$!")
    a('log "QEMU pid $QEMU_PID"')
    a("")

    if pinning.get("vcpupin"):
        nvcpu = len(pinning["vcpupin"])
        a("# ----------------------------------------------------------- pinning --")
        a('vcpu_tids() {')
        a('    grep -l "^Name:.*CPU " /proc/$QEMU_PID/task/*/status 2>/dev/null \\')
        a('        | sed "s|/proc/$QEMU_PID/task/||; s|/status||" \\')
        a('        | while read -r t; do')
        a('              n=$(sed -n "s/^Name:\\s*CPU \\([0-9]*\\).*/\\1/p" \\')
        a('                    /proc/$QEMU_PID/task/$t/status 2>/dev/null)')
        a('              [[ -n "$n" ]] && echo "$n $t"')
        a('          done | sort -n | awk "{print \\$2}"')
        a("}")
        a("")
        # Counting /proc/PID/task is not enough. The iothreads and the vfio
        # worker threads push the total past the target before a single vCPU
        # thread exists, so a count-based wait returns while vcpu_tids is still
        # empty -- and the emulator pass then pins every thread QEMU owns,
        # including the vCPUs that are about to be created.
        a(f'log "waiting for {nvcpu} named vCPU threads"')
        a("VCPU_TIDS=()")
        a("for _ in $(seq 1 600); do")
        a("    mapfile -t VCPU_TIDS < <(vcpu_tids)")
        a(f'    [[ "${{#VCPU_TIDS[@]}}" -ge {nvcpu} ]] && break')
        a('    kill -0 "$QEMU_PID" 2>/dev/null || break')
        a("    sleep 0.1")
        a("done")
        a('if ! kill -0 "$QEMU_PID" 2>/dev/null; then')
        a('    log "QEMU exited during startup"')
        a("    do_revert failed")
        a('    echo "=============== VM ABORTED  $(date "+%d %m %y %H:%M") ==========================="')
        a("    exit 1")
        a("fi")
        a("")
        a(f'if [[ "${{#VCPU_TIDS[@]}}" -lt {nvcpu} ]]; then')
        # Refusing to pin is the safe failure. An unpinned guest is merely
        # slower; a guest whose vCPUs all land on the emulator's two host CPUs
        # under SCHED_FIFO with RT throttling disabled makes no forward
        # progress at all, which looks exactly like a hung VM.
        a(f'    log "only ${{#VCPU_TIDS[@]}} of {nvcpu} vCPU threads found; SKIPPING ALL PINNING"')
        a('    log "the guest runs unpinned rather than risk being stranded"')
        a("else")
        a(f'    log "found ${{#VCPU_TIDS[@]}} vCPU threads"')

        vs = pinning.get("vcpusched", {})
        for e in pinning["vcpupin"]:
            v, cpuset = e["vcpu"], e["cpuset"]
            a(f'    taskset -pc {cpuset} "${{VCPU_TIDS[{v}]}}" >/dev/null '
              f'|| log "pin vcpu {v} failed"')
            if vs.get("scheduler") in ("fifo", "rr"):
                flag = "-f" if vs["scheduler"] == "fifo" else "-r"
                a(f'    chrt {flag} -p {vs.get("priority", 1)} '
                  f'"${{VCPU_TIDS[{v}]}}" >/dev/null || true')

        # --- iothreads ------------------------------------------------
        # Each -object iothread gets its own cpuset and its own policy, which
        # is the whole point of having named them. They are claimed here,
        # before the emulator sweep, and the sweep then skips them: without
        # that it pinned every non-vCPU thread to the emulator cpuset and the
        # I/O thread settings did nothing at all.
        iothreads = _iothread_pins(cfg, pinning)
        if iothreads:
            ios = pinning.get("iothreadsched", {})
            a("")
            a("    # QEMU names an iothread's thread 'IO <id>', but only because")
            a("    # the command line carries -name debug-threads=on. The name is")
            a("    # set in full or not at all: pthread_setname_np refuses")
            a("    # anything over 15 characters rather than truncating, so an id")
            a("    # longer than 12 leaves the thread called qemu-system-x86 and")
            a("    # unfindable here. Preflight warns about that case.")
            a("    iothread_tid() {")
            a('        grep -l "^Name:[[:space:]]*IO $1$" \\')
            a('            /proc/$QEMU_PID/task/*/status 2>/dev/null \\')
            a('            | head -1 | sed "s|/proc/$QEMU_PID/task/||; s|/status||"')
            a("    }")
            a('    log "pinning I/O threads"')
            a('    IOTHREAD_TIDS=""')
            for iot_id, cpuset in iothreads:
                a(f'    TID=$(iothread_tid {shlex.quote(iot_id)})')
                a('    if [[ -n "$TID" ]]; then')
                a('        IOTHREAD_TIDS="$IOTHREAD_TIDS $TID"')
                a(f'        taskset -pc {cpuset} "$TID" >/dev/null 2>&1 '
                  f'|| log "  pin {iot_id} failed"')
                if ios.get("scheduler") in ("fifo", "rr"):
                    flag = "-f" if ios["scheduler"] == "fifo" else "-r"
                    a(f'        chrt {flag} -p {ios.get("priority", 1)} '
                      f'"$TID" >/dev/null 2>&1 || true')
                a(f'        log "  {iot_id} -> tid $TID, cpu {cpuset}"')
                a("    else")
                # Not fatal: the thread is missing only if QEMU dropped the
                # object, and the emulator sweep below covers whatever is
                # actually there.
                a(f'        log "  {iot_id}: no thread by that name; left to the emulator pass"')
                a("    fi")

        emu = pinning.get("emulatorpin")
        if emu:
            a("")
            a("    # Everything that is not one of the vCPU or I/O threads")
            a("    # identified above. Matched against those TID lists rather than")
            a("    # against the thread name, so a thread QEMU has not named yet")
            a("    # cannot be mistaken for an emulator thread and pinned on top")
            a("    # of them.")
            a(f'    log "pinning emulator threads to {emu}"')
            a('    IS_PINNED=" ${VCPU_TIDS[*]} '
              + ('${IOTHREAD_TIDS} ' if iothreads else '') + '"')
            a("    for t in /proc/$QEMU_PID/task/*; do")
            a('        tid=$(basename "$t")')
            a('        [[ "$IS_PINNED" == *" $tid "* ]] && continue')
            a(f'        taskset -pc {emu} "$tid" >/dev/null 2>&1 || true')
            es = pinning.get("emulatorsched", {})
            if es.get("scheduler") in ("fifo", "rr"):
                flag = "-f" if es["scheduler"] == "fifo" else "-r"
                a(f'        chrt {flag} -p {es.get("priority", 1)} '
                  f'"$tid" >/dev/null 2>&1 || true')
            a("    done")
        a("fi")
        a("")

    a('log "VM running"')
    a("")
    capture = cfg.profile == "macos" and cfg.data.get("performance", {}).get("capture", False)
    if capture:
        owner = os.stat(cfg.root if os.path.isdir(cfg.root) else os.path.expanduser("~"))
        recorder = [sys.executable, os.path.join(APP_DIR, "scripts", "mac_performance_capture.py"),
                    "--owner-uid", str(owner.st_uid), "--owner-gid", str(owner.st_gid),
                    "--expected-pins", json.dumps({str(p["vcpu"]): p["cpuset"]
                                                    for p in pinning.get("vcpupin", [])})]
        for device in cfg.devices:
            if device.get("driver") == "vfio-pci" and not device.get("_disabled"):
                recorder += ["--pci", device["host"]]
        a(shlex.join(recorder) + ' --pid "$QEMU_PID" &')
        a("PERFORMANCE_PID=$!")
        a("")
    # Belt and braces for the -no-shutdown class of problem: if the guest stops
    # but QEMU stays alive, ask it to quit over QMP, then insist. Without this
    # the wait below never returns and the GPU is held forever, which looks
    # exactly like a hung host.
    a("watch_shutdown() {")
    a('    local qmp="%s"' % _qmp_path(cfg, standalone))
    a("    while kill -0 \"$QEMU_PID\" 2>/dev/null; do")
    a("        sleep 2")
    a('        [[ -S "$qmp" ]] || continue')
    a('        st=$(printf \'{"execute":"qmp_capabilities"}\\n{"execute":"query-status"}\\n\' \\')
    a('             | timeout 5 socat - "UNIX-CONNECT:$qmp" 2>/dev/null | tail -1)')
    a('        case "$st" in')
    a('            *\'"status": "shutdown"\'*|*\'"status": "guest-panicked"\'*)')
    a('                log "guest stopped but QEMU is still alive; asking it to quit"')
    a('                printf \'{"execute":"qmp_capabilities"}\\n{"execute":"quit"}\\n\' \\')
    a('                    | timeout 5 socat - "UNIX-CONNECT:$qmp" >/dev/null 2>&1')
    a("                sleep 5")
    a('                kill -0 "$QEMU_PID" 2>/dev/null || return')
    a('                log "QEMU ignored quit; terminating"')
    a('                kill -TERM "$QEMU_PID" 2>/dev/null')
    a("                sleep 5")
    a('                kill -KILL "$QEMU_PID" 2>/dev/null')
    a("                return")
    a("                ;;")
    a("        esac")
    a("    done")
    a("}")
    a('if command -v socat >/dev/null 2>&1; then')
    a("    watch_shutdown &")
    a("    WATCHER=$!")
    a("else")
    a('    log "socat not installed; cannot watch for a stuck shutdown"')
    a("    WATCHER=")
    a("fi")
    a("")
    a('wait "$QEMU_PID"')
    a("RC=$?")
    if capture:
        a('if jobs -pr | grep -Fxq "$PERFORMANCE_PID"; then kill "$PERFORMANCE_PID" 2>/dev/null || true; fi')
        a('wait "$PERFORMANCE_PID" 2>/dev/null || true')
    a('[[ -n "${WATCHER:-}" ]] && kill "$WATCHER" 2>/dev/null')
    a('log "QEMU exited with $RC"')
    a('echo "=============== VM STOPPED  $(date "+%d %m %y %H:%M")  rc=$RC ================="')
    a('do_revert "$([[ "$RC" == 0 ]] && echo ok || echo failed)"')
    a("exit $RC")
    return "\n".join(L) + "\n"


def write_script(cfg, pinning, standalone=True, reboot_after=True):
    os.makedirs(RUN_DIR, exist_ok=True)
    write_hooks(cfg, pinning, reboot_after=reboot_after)
    text = build_script(cfg, pinning, standalone, reboot_after)
    with open(SCRIPT, "w") as f:
        f.write(text)
    os.chmod(SCRIPT, 0o775)
    return SCRIPT, text


def launch(cfg, pinning, **kw):
    """Write the scripts and hand them to systemd as a transient unit.

    systemd-run rather than a child process: this GUI dies with the display
    manager the start hook is about to stop, and a child would go with it.
    """
    path, _ = write_script(cfg, pinning, **kw)
    unit = "vmstart2-vm"
    subprocess.run(["sudo", "-n", "systemctl", "reset-failed", unit],
                   capture_output=True)
    command = ["sudo", "-n", "systemd-run", "--unit", unit,
         "--description=vmstart_2 guest",
         "--property=KillMode=mixed",
         "--property=TimeoutStopSec=120",
         "--service-type=simple"]
    if _mac_temporary_memory(cfg):
        # Runs after the service's QEMU children stop, including an interrupted
        # launch. The helper refuses cleanup if another lease owner is alive.
        cleanup = shlex.join([sys.executable, os.path.join(APP_DIR, "lib", "mac_hugepages.py"), "--release"])
        command.append("--property=ExecStopPost=" + cleanup)
    command.extend(["/usr/bin/env", "bash", path])
    r = subprocess.run(command, capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip(), path


# ----------------------------------------------------------------- dry run ---
TESTRUN = os.path.join(RUN_DIR, "testrun.sh")


def build_testrun(cfg, standalone=True):
    """A launch that proves everything except the GPU handoff.

    Same command line, minus the vfio-pci and usb-host devices, started paused
    with a QMP socket and immediately quit. That exercises every backend that
    can fail -- blockdevs, TPM, tap, hugepages, SMBIOS, ACPI -- while the
    desktop is still up, so a mistake costs a few seconds instead of a launch
    attempt and a hard reset.

    usb-host is dropped too: grabbing the keyboard and mouse away from the
    host mid-test would be its own emergency.
    """
    argv = cfg.to_argv(standalone)
    keep, skipped = [argv[0]], []
    i = 1
    while i < len(argv):
        flag = argv[i]
        val = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("-") else None
        step = 2 if val is not None else 1
        if flag == "-device" and val and ('"vfio-pci"' in val or '"usb-host"' in val):
            try:
                skipped.append(json.loads(val).get("id", "?"))
            except Exception:
                skipped.append("?")
            i += step
            continue
        if flag in ("-qmp", "-mon", "-chardev") and val and "charmonitor" in str(val):
            i += step          # the monitor is replaced by stdio below
            continue
        if flag == "-qmp":
            i += step
            continue
        keep.append(flag)
        if val is not None:
            keep.append(val)
        i += step
    keep += ["-S", "-qmp", "stdio"]

    ram = next((o for o in cfg.objects if o.get("id") == "pc.ram"), None)
    mp = (ram or {}).get("mem-path")
    net = cfg.data.get("network") or {}
    tpm = _tpm(cfg)

    pages, psize, sysfs = _hugepages(cfg)

    L = ["#!/usr/bin/env bash",
         "# Generated by vmstart_2. Non-destructive test: no GPU, no USB, paused.",
         "set -uo pipefail",
         'log() { echo "[test] $*"; }',
         "RC=0", ""]
    L.extend(_mac_memory_prepare(cfg))
    L.extend(_mac_memory_guard(cfg))
    # Mac allocation, when explicitly selected, uses its journaled helper.
    manage_memory = cfg.profile != "macos"
    a = L.append
    if pages and manage_memory:
        # The pool has to be filled here too, or the test fails on
        # "unable to map backing store for guest RAM" for a reason the real
        # launch would not have hit. Whatever was there before is put back on
        # the way out, so running the test does not leave 32 GiB pinned.
        a(f'POOL={shlex.quote(sysfs)}')
        a('POOL_WAS=$(cat "$POOL" 2>/dev/null || echo 0)')
    if mp and manage_memory:
        # Declared before the trap: set -u would abort cleanup on an unset name
        # if the run failed before the mount was attempted.
        a("TEST_MOUNTED_HUGETLBFS=0")
    a("cleanup() {")
    if _mac_temporary_memory(cfg):
        a("    mac_hp_release")
    if mp and manage_memory:
        # Unmount before shrinking the pool: a live hugetlbfs holds its pages,
        # so the pool would refuse to go back down and leave RAM reserved.
        a('    if [[ "$TEST_MOUNTED_HUGETLBFS" == 1 ]]; then')
        a(f'        log "unmounting hugetlbfs at {mp}"')
        a(f'        umount {shlex.quote(mp)} 2>/dev/null || true')
        a("    fi")
    if pages and manage_memory:
        a('    if [[ -w "$POOL" ]]; then')
        a('        log "restoring hugepage pool to $POOL_WAS"')
        a('        echo "$POOL_WAS" > "$POOL" 2>/dev/null || true')
        a("    fi")
    if net.get("ifname"):
        a(f'    ip link set {shlex.quote(net["ifname"])} down 2>/dev/null || true')
        a(f'    ip tuntap del dev {shlex.quote(net["ifname"])} mode tap 2>/dev/null || true')
    if tpm:
        a(f'    pkill -f "swtpm.*{tpm["sock"]}" 2>/dev/null || true')
        a(f'    rm -f {shlex.quote(tpm["sock"])} 2>/dev/null || true')
    a('    log "cleaned up"')
    a("}")
    a("trap cleanup EXIT")
    a("")
    if pages and manage_memory:
        human = f"{psize // 1024 // 1024} MiB" if psize < 1024 ** 3 else f"{psize // 1024 ** 3} GiB"
        a('if [[ ! -w "$POOL" ]]; then')
        a(f'    log "no {human} hugepage pool at $POOL"')
        a("    exit 1")
        a("fi")
        a(f'if [[ "$POOL_WAS" -lt {pages} ]]; then')
        a(f'    log "allocating {pages} x {human} ({pages * psize // 1024**3} GiB)"')
        a(f'    echo {pages} > "$POOL"')
        a('    sync; echo 3 > /proc/sys/vm/drop_caches')
        a(f'    echo {pages} > "$POOL"')
        a("fi")
        a('GOT=$(cat "$POOL")')
        a(f'if [[ "$GOT" -lt {pages} ]]; then')
        a(f'    log "only got $GOT of {pages} hugepages; host too fragmented"')
        a("    exit 1")
        a("fi")
        a('log "hugepages ok: $GOT"')

    if mp and manage_memory:
        a(f'mkdir -p {shlex.quote(mp)} || {{ log "cannot create {mp}"; exit 1; }}')
        # The start hook mounts a hugetlbfs here when the host has no persistent
        # one, and the test has to do the same or it is not testing the launch.
        # Without it QEMU maps guest RAM out of whatever ordinary filesystem the
        # path happens to sit on -- tmpfs, on this host -- so the reserved pool
        # goes unused and the box pays for the guest's memory twice. prealloc
        # then touches every page and the OOM killer takes QEMU with SIGKILL,
        # which reads as an unexplained exit 137.
        psz = (f"{psize // 1024**3}G" if psize and psize >= 1024 ** 3
               else f"{(psize or 2 * 1024**2) // 1024 // 1024}M")
        a(f'if ! findmnt -no FSTYPE -T {shlex.quote(mp)} | grep -q hugetlbfs; then')
        a(f'    log "mounting hugetlbfs at {mp} (pagesize {psz})"')
        a(f'    mount -t hugetlbfs -o pagesize={psz} hugetlbfs {shlex.quote(mp)} \\')
        a(f'        || {{ log "could not mount hugetlbfs at {mp}"; exit 1; }}')
        a('    TEST_MOUNTED_HUGETLBFS=1')
        a("fi")
    if net.get("ifname"):
        tap, br = net["ifname"], net.get("bridge") or ""
        a(f'if ! ip link show {shlex.quote(tap)} >/dev/null 2>&1; then')
        a(f'    ip tuntap add dev {shlex.quote(tap)} mode tap || {{ log "tap failed"; exit 1; }}')
        a("fi")
        if br:
            a(f'ip link set {shlex.quote(tap)} master {shlex.quote(br)} || {{ log "bridge failed"; exit 1; }}')
        a(f'ip link set {shlex.quote(tap)} up || {{ log "link up failed"; exit 1; }}')
        a(f'log "tap {tap} ready"')
    if tpm:
        a(f'mkdir -p "$(dirname {shlex.quote(tpm["sock"])})"')
        a(f'rm -f {shlex.quote(tpm["sock"])}')
        a(f'{shlex.quote(tpm["binary"])} socket --daemon --tpm2 \\')
        a(f'    --tpmstate dir={shlex.quote(tpm["state"])},mode=0600 \\')
        a(f'    --ctrl type=unixio,path={shlex.quote(tpm["sock"])},mode=0600 --terminate \\')
        a(f'    || {{ log "swtpm failed to start"; exit 1; }}')
        a(f'for _ in $(seq 1 50); do [[ -S {shlex.quote(tpm["sock"])} ]] && break; sleep 0.1; done')
        a(f'[[ -S {shlex.quote(tpm["sock"])} ]] || {{ log "swtpm socket never appeared"; exit 1; }}')
        a('log "swtpm ready"')
    a("")
    if skipped:
        a(f'log "not tested (needs the display torn down): {", ".join(skipped)}"')
    a('log "starting QEMU paused"')
    a('printf \'{"execute":"qmp_capabilities"}\\n{"execute":"query-status"}\\n{"execute":"quit"}\\n\' | \\')
    a("  " + " ".join(shlex.quote(x) for x in keep))
    a("RC=$?")
    a('log "QEMU exited with $RC"')
    a("exit $RC")
    return "\n".join(L) + "\n", skipped


def test_run(cfg, standalone=True, timeout=120):
    """Write and execute the non-destructive test. Returns (ok, output)."""
    os.makedirs(RUN_DIR, exist_ok=True)
    text, skipped = build_testrun(cfg, standalone)
    with open(TESTRUN, "w") as f:
        f.write(text)
    os.chmod(TESTRUN, 0o775)
    try:
        r = subprocess.run(["sudo", "-n", "bash", TESTRUN],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["sudo", "-n", "pkill", "-f", TESTRUN], capture_output=True)
        return False, f"test timed out after {timeout}s"
    out = (r.stdout + r.stderr).strip()
    return r.returncode == 0, out


# --------------------------------------------------------------------- log ---
def read_log(max_bytes=400000):
    if not os.path.isfile(LOG):
        return ""
    size = os.path.getsize(LOG)
    with open(LOG, errors="replace") as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
            f.readline()          # drop the partial line
        return f.read()


def clear_log():
    os.makedirs(RUN_DIR, exist_ok=True)
    with open(LOG, "w"):
        pass
    return LOG
