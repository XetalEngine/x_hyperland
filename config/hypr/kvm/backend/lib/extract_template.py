#!/usr/bin/env python3
"""Turn a captured QEMU argv into the structured template vmstart_2 edits.

Run against the raw argv captured from /proc/<pid>/cmdline of the live domain,
so the template is exactly what libvirt actually launched rather than a
re-derivation from XML that might drift.

    extract_template.py win10-argv-raw.txt template.json
"""

import json
import sys
from collections import OrderedDict


def load_argv(path):
    return [l.rstrip("\n") for l in open(path) if l.rstrip("\n") != ""]


def pair_up(args):
    """Yield (flag, value) with value None for standalone flags."""
    i = 1  # skip argv[0]
    while i < len(args):
        a = args[i]
        if a.startswith("-"):
            if i + 1 < len(args) and not args[i + 1].startswith("-"):
                yield a, args[i + 1]
                i += 2
            else:
                yield a, None
                i += 1
        else:
            i += 1


def parse_kv(s):
    """'a=b,c=d' or 'host,migratable=off' -> (positional_list, OrderedDict)."""
    pos, kv = [], OrderedDict()
    depth = 0
    cur = ""
    parts = []
    for ch in s:
        if ch in "[{(":
            depth += 1
        elif ch in "]})":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        parts.append(cur)
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            kv[k] = v
        elif p:
            pos.append(p)
    return pos, kv


def main():
    args = load_argv(sys.argv[1])
    t = OrderedDict()
    t["_meta"] = {
        "source": "captured from live /proc/<pid>/cmdline",
        "binary": args[0],
        "argc": len(args),
    }

    devices, blockdevs, objects, acpitables, globals_, chardevs = [], [], [], [], [], []
    simple = OrderedDict()
    order = []   # exact emission sequence, so the generator can reproduce input

    buckets = {"device": devices, "blockdev": blockdevs, "object": objects,
               "acpitable": acpitables, "global": globals_, "chardev": chardevs}

    for flag, val in pair_up(args):
        f = flag.lstrip("-")
        if f in buckets:
            buckets[f].append(val)
            order.append([f, len(buckets[f]) - 1])
        else:
            # later occurrences would overwrite; none of these repeat
            simple[f] = val
            order.append([f, None])

    def as_json_list(items):
        out = []
        for it in items:
            s = it.strip()
            if s.startswith("{"):
                try:
                    out.append(json.loads(s))
                    continue
                except json.JSONDecodeError:
                    pass
            pos, kv = parse_kv(s)
            out.append({"_raw": s, "_positional": pos, **kv})
        return out

    t["order"] = order
    t["simple"] = simple
    t["objects"] = as_json_list(objects)
    t["blockdevs"] = as_json_list(blockdevs)
    t["devices"] = as_json_list(devices)
    t["chardevs"] = as_json_list(chardevs)
    t["globals"] = globals_
    t["acpitables"] = acpitables

    # Break out the structured bits the UI edits directly
    machine_pos, machine_kv = parse_kv(simple.get("machine", ""))
    cpu_pos, cpu_kv = parse_kv(simple.get("cpu", ""))
    smp_pos, smp_kv = parse_kv(simple.get("smp", ""))
    t["machine"] = {"type": machine_pos[0] if machine_pos else "", "opts": machine_kv}
    t["cpu"] = {"model": cpu_pos[0] if cpu_pos else "", "features": cpu_kv}
    t["smp"] = {"vcpus": smp_pos[0] if smp_pos else smp_kv.get("cpus", ""), "topology": smp_kv}

    json.dump(t, open(sys.argv[2], "w"), indent=2)

    print(f"  simple flags : {len(simple)}")
    print(f"  objects      : {len(objects)}")
    print(f"  blockdevs    : {len(blockdevs)}")
    print(f"  devices      : {len(devices)}")
    print(f"  chardevs     : {len(chardevs)}")
    print(f"  globals      : {len(globals_)}")
    print(f"  acpitables   : {len(acpitables)}")
    print(f"  cpu features : {len(cpu_kv)}")


if __name__ == "__main__":
    sys.exit(main())
