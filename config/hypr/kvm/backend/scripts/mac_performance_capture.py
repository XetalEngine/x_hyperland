#!/usr/bin/env python3
"""Read-only Linux/QEMU measurements. Writes private reports, never host settings.

Invoked by the Mac launcher after CPU pinning, or manually with --pid. No QMP
commands, perf tracing, signals, sysctl writes or guest disk access are used.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
PROC = Path("/proc")
SYS = Path("/sys")


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError as exc:
        return {"unavailable": str(exc)}


def command(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return {"argv": args, "exit": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"argv": args, "unavailable": str(exc)}


def cpu_set(text):
    result = set()
    for part in str(text).split(","):
        if not part.strip():
            continue
        bounds = part.split("-")
        start, end = int(bounds[0]), int(bounds[-1])
        result.update(range(start, end + 1))
    return result


def parse_smaps(text):
    """Keep per-VMA page evidence: KernelPageSize alone does not prove THP."""
    mappings, current = [], None
    for line in text.splitlines():
        if re.match(r"^[0-9a-f]+-[0-9a-f]+ ", line):
            current = {"mapping": line}
            mappings.append(current)
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            if key in {"Size", "Rss", "Pss", "Anonymous", "AnonHugePages", "ShmemPmdMapped",
                       "FilePmdMapped", "Shared_Hugetlb", "Private_Hugetlb", "KernelPageSize",
                       "MMUPageSize", "Swap", "Locked"}:
                current[key + "_kB"] = int(value.split()[0])
            elif key in {"THPeligible", "VmFlags"}:
                current[key] = value.strip()
    keys = ("Size", "Rss", "AnonHugePages", "ShmemPmdMapped", "FilePmdMapped",
            "Shared_Hugetlb", "Private_Hugetlb", "Swap", "Locked")
    totals = {key + "_kB": sum(m.get(key + "_kB", 0) for m in mappings) for key in keys}
    large = [m for m in mappings if m.get("Size_kB", 0) >= 1024**2 or
             m.get("Shared_Hugetlb_kB", 0) or m.get("Private_Hugetlb_kB", 0)]
    return {"process_totals": totals, "large_or_hugetlb_mappings": large,
            "note": "Process totals include QEMU overhead. Match large mappings to guest RAM. "
                    "THPeligible is eligibility, not allocated coverage; DirectMap1G is not guest RAM. "
                    "smaps does not prove the KVM nested page-table leaf size."}


def proc_stat(text):
    tail = text[text.rfind(")") + 2:].split()
    return {"ticks": int(tail[11]) + int(tail[12]), "start": int(tail[19]),
            "last_cpu": int(tail[36]), "minor_faults": int(tail[7]), "major_faults": int(tail[9])}


def threads(pid, expected):
    rows = []
    for task in sorted((PROC / str(pid) / "task").glob("*")):
        try:
            status = dict(line.split(":", 1) for line in (task / "status").read_text().splitlines() if ":" in line)
            stat = proc_stat((task / "stat").read_text())
            name = status["Name"].strip()
            row = dict(tid=int(task.name), name=name, **stat,
                       allowed=status["Cpus_allowed_list"].strip(),
                       voluntary=int(status.get("voluntary_ctxt_switches", "0")),
                       involuntary=int(status.get("nonvoluntary_ctxt_switches", "0")))
            match = re.fullmatch(r"CPU (\d+)/KVM", name)
            if match:
                row["vcpu"] = int(match[1])
                want = expected.get(match[1])
                if want is not None:
                    row["expected"] = want
                    row["affinity_matches"] = cpu_set(want) == cpu_set(row["allowed"])
            schedstat = read(task / "schedstat")
            if isinstance(schedstat, str):
                values = schedstat.split()
                if len(values) >= 3:
                    row["schedstat"] = dict(runtime_ns=int(values[0]), runqueue_wait_ns=int(values[1]),
                                             timeslices=int(values[2]))
            rows.append(row)
        except (OSError, ValueError, KeyError, IndexError):
            continue  # A transient worker may disappear while reading it.
    return rows


def thread_deltas(before, after, seconds):
    old = {(r["tid"], r["start"]): r for r in before}
    hz = os.sysconf("SC_CLK_TCK")
    for row in after:
        prev = old.get((row["tid"], row["start"]))
        if prev and seconds > 0:
            row["cpu_percent_one_logical_cpu"] = round(100 * (row["ticks"] - prev["ticks"]) / hz / seconds, 2)
            row["involuntary_delta"] = row["involuntary"] - prev["involuntary"]


def gpu_state(slots):
    result = {}
    for slot in slots:
        if not re.fullmatch(r"[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]", slot):
            raise ValueError("Invalid PCI slot")
        p = SYS / "bus/pci/devices" / slot
        values = {name: read(p / name) for name in ("current_link_speed", "current_link_width",
                   "max_link_speed", "max_link_width", "resource", "numa_node", "power/runtime_status")}
        values["driver"] = (p / "driver").resolve().name
        irqs = {}
        for irq in (p / "msi_irqs").glob("*"):
            irqs[irq.name] = read(PROC / "irq" / irq.name / "effective_affinity_list")
        values["irq_effective_affinity"] = irqs
        result[slot] = values
    return result


def host_snapshot():
    files = ["/proc/cmdline", "/proc/meminfo", "/proc/sys/vm/overcommit_memory", "/proc/sys/vm/overcommit_ratio",
             "/proc/sys/kernel/sched_schedstats", "/proc/self/mounts", "/sys/kernel/mm/transparent_hugepage/enabled",
             "/sys/kernel/mm/transparent_hugepage/defrag", "/sys/kernel/mm/ksm/run", "/sys/devices/system/cpu/isolated",
             "/sys/devices/system/cpu/nohz_full", "/sys/devices/system/cpu/cpufreq/boost", "/sys/devices/system/cpu/amd_pstate/status"]
    files.extend(str(p) for p in (SYS / "kernel/mm/hugepages").glob("*/*") if p.name in
                 {"nr_hugepages", "free_hugepages", "resv_hugepages", "surplus_hugepages", "nr_overcommit_hugepages"})
    files.extend(str(p) for p in (SYS / "devices/system/cpu/cpufreq").glob("policy*/*") if p.name in
                 {"scaling_governor", "scaling_min_freq", "scaling_max_freq", "energy_performance_preference"})
    for module in ("kvm", "kvm_amd", "vfio_pci", "vfio_iommu_type1"):
        files.extend(str(p) for p in (SYS / "module" / module / "parameters").glob("*"))
    topology = {}
    for p in sorted((SYS / "devices/system/cpu").glob("cpu[0-9]*")):
        topology[p.name] = {"siblings": read(p / "topology/thread_siblings_list"),
                            "l3_size": read(p / "cache/index3/size"),
                            "l3_shared": read(p / "cache/index3/shared_cpu_list")}
    return {"time_utc": datetime.now(timezone.utc).isoformat(), "files": {f: read(f) for f in files},
            "topology": topology, "supports_1GiB": "pdpe1gb" in str(read(PROC / "cpuinfo")).split(),
            "lscpu": command(["lscpu", "-e=CPU,CORE,SOCKET,NODE,CACHE"]),
            "numa": command(["numactl", "--hardware"])}


def sample(pid, expected, slots, memory=True):
    p = PROC / str(pid)
    data = {"time_utc": datetime.now(timezone.utc).isoformat(), "monotonic": time.monotonic(),
            "threads": threads(pid, expected), "gpu": gpu_state(slots),
            "host_cpu_counters": read(PROC / "stat"), "host_meminfo": read(PROC / "meminfo"),
            "pressure": {k: read(PROC / "pressure" / k) for k in ("cpu", "memory", "io")},
            "process_io": read(p / "io"), "interrupt_counters": read(PROC / "interrupts")}
    if memory:
        smaps = read(p / "smaps")
        data["memory"] = parse_smaps(smaps) if isinstance(smaps, str) else smaps
        data["numa_maps"] = read(p / "numa_maps")
    return data


def capture(pid, directory, seconds, interval, expected, slots, owner=None):
    proc = PROC / str(pid)
    identity = proc_stat((proc / "stat").read_text())["start"]
    argv = (proc / "cmdline").read_bytes().decode(errors="replace").rstrip("\0").split("\0")
    if not argv or not Path(argv[0]).name.startswith("qemu-system-"):
        raise ValueError("The selected PID is not QEMU")
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    def own_reports():
        if owner and os.geteuid() == 0:
            for item in [directory, *directory.iterdir()]:
                os.chown(item, *owner, follow_symlinks=False)
    (directory / "host.json").write_text(json.dumps(host_snapshot(), indent=2) + "\n")
    (directory / "qemu-argv.json").write_text(json.dumps(argv, indent=2) + "\n")
    (directory / "expected-pins.json").write_text(json.dumps(expected, indent=2) + "\n")
    own_reports()
    print(f"Mac performance report: {directory}", flush=True)
    end = time.monotonic() + seconds
    previous, index = None, 0
    stop = False

    def stopping(_signal, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, stopping)
    signal.signal(signal.SIGINT, stopping)
    with (directory / "samples.jsonl").open("w", buffering=1) as output:
        own_reports()
        while not stop:
            try:
                if proc_stat((proc / "stat").read_text())["start"] != identity:
                    break  # Never follow a reused PID.
                row = sample(pid, expected, slots, memory=index % 6 == 0)
            except (FileNotFoundError, ProcessLookupError):
                break
            if previous:
                thread_deltas(previous["threads"], row["threads"], row["monotonic"] - previous["monotonic"])
            output.write(json.dumps(row, separators=(",", ":")) + "\n")
            output.flush()
            previous, index = row, index + 1
            if time.monotonic() >= end:
                break
            time.sleep(min(interval, max(0, end - time.monotonic())))
    (directory / "finished.json").write_text(json.dumps({"samples": index, "stopped": stop,
                              "time_utc": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n")
    own_reports()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--seconds", type=float, default=1800)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--expected-pins", default="{}")
    parser.add_argument("--pci", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--owner-uid", type=int)
    parser.add_argument("--owner-gid", type=int)
    args = parser.parse_args()
    if args.snapshot:
        print(json.dumps(host_snapshot(), indent=2))
        return
    if not args.pid or args.seconds < 0 or not 1 <= args.interval <= 60:
        parser.error("--pid is required; seconds must be nonnegative and interval must be 1–60 seconds")
    directory = args.output or ROOT / "macos/performance/reports" / (
        datetime.now().strftime("run-%Y%m%d-%H%M%S-") + str(args.pid))
    os.umask(0o077)
    owner = (args.owner_uid, args.owner_gid) if args.owner_uid is not None and args.owner_gid is not None else None
    capture(args.pid, directory, args.seconds, args.interval, json.loads(args.expected_pins), args.pci, owner)


if __name__ == "__main__":
    main()
