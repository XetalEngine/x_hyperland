"""Boot argument descriptions and a lossless draft for the Mac editor.

References: Apple XNU osfmk/kern/debug.h; OpenCore Configuration (NVRAM);
acidanthera/RestrictEvents README; nullmoth/nvidia-macos-driver docs/HOW-IT-WORKS.md
and kexts/NVRM/{NVRM.cpp,accel/nvrm-accel.cpp}. Driver options require that driver.
"""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Argument:
    key: str
    default: str | None
    description: str
    kind: str = "text"


CATALOG = (
    Argument("-v", None, "Show macOS startup messages instead of the usual boot screen. This switch has no value."),
    Argument("keepsyms", "1", "Keep symbol names in kernel panic reports to make crashes easier to diagnose. 1 enables this; 0 disables it.", "bool"),
    Argument("debug", "0x100", "Kernel debugging bitmask. 0x100 is the legacy panic-screen flag (marked obsolete in newer XNU); it is kept for existing setups, not a speed setting.", "mask"),
    Argument("revpatch", "sbvmm", "RestrictEvents patches, separated by commas. sbvmm uses the virtual-machine Secure Boot model for software updates on unsupported Mac models. Requires RestrictEvents.kext."),
    Argument("nvfb", "1", "Start the NullMoth NVIDIA framebuffer, which drives the display. 1 enables it; 0 disables it. Requires the installed NullMoth driver.", "bool"),
    Argument("nvaccel", "1", "Start the NullMoth NVIDIA accelerator used for GPU rendering. 1 enables it; 0 disables it. Requires the installed NullMoth driver.", "bool"),
    Argument("nvfbheads", "4", "Number of display heads exposed by the NullMoth driver (1–4). This does not set the screen resolution.", "heads"),
    Argument("-nvkmsnosmooth", None, "Disable the NullMoth driver's smooth display takeover during startup. Used by this driver's setup instructions. This switch has no value."),
    Argument("amfi_get_out_of_my_way", "0x1", "Relax AMFI code-signing enforcement for the NullMoth driver setup. 0x1 enables this override. It reduces macOS security checks; it is not a performance setting.", "mask"),
    Argument("amfi", "0x80", "AMFI policy bitmask. The NullMoth setup uses 0x80 to relax validation so its graphics bundle can load. Changing this can prevent the driver from loading.", "mask"),
    Argument("ipc_control_port_options", "0", "Control macOS task-port restrictions. The NullMoth setup uses 0 to relax these restrictions for driver compatibility; changing this affects security and driver operation.", "mask"),
    Argument("-nvaccelnoheadless", None, "Disable the NullMoth driver's headless-GPU fallback while waiting for a display. This is used by the working RTX 4090 display setup. This switch has no value."),
    Argument("nvrmsettle", "10000", "Override the NullMoth startup settling delay in milliseconds (10000 = 10 seconds). Uncheck to use the driver's default. Too short a delay can cause a black screen.", "delay"),
)
SPECS = {arg.key: arg for arg in CATALOG}


def tokens(text):
    """Yield (separator, raw token), retaining quotes, whitespace and escapes.

    These are not shell commands. In particular, never shell-split/requote values
    or expand anything. Unbalanced quoting is kept in one opaque final token.
    """
    pos = 0
    while pos < len(text):
        start = pos
        while pos < len(text) and text[pos].isspace():
            pos += 1
        separator = text[start:pos]
        start, quote = pos, None
        while pos < len(text):
            char = text[pos]
            if char == "\\" and pos + 1 < len(text):
                pos += 2
                continue
            if quote:
                if char == quote:
                    quote = None
            elif char in "\"'":
                quote = char
            elif char.isspace():
                break
            pos += 1
        yield separator, text[start:pos]


@dataclass
class Entry:
    separator: str
    raw: str
    key: str
    value: str | None
    enabled: bool = True

    @property
    def spec(self):
        return SPECS.get(self.key)


class ArgumentsDraft:
    def __init__(self, text):
        self.entries = []
        for separator, raw in tokens(text):
            key, equals, value = raw.partition("=")
            self.entries.append(Entry(separator, raw, key, value if equals else None))
        present = {entry.key for entry in self.entries}
        for spec in CATALOG:
            if spec.key not in present:
                raw = spec.key + ("=" + spec.default if spec.default is not None else "")
                self.entries.append(Entry(" ", raw, spec.key, spec.default, False))

    def render(self):
        # Whitespace belonging to disabled rows stays put: untouched tokens
        # (including duplicate keys and quoted custom values) stay byte-for-byte.
        return "".join(e.separator + (e.raw if e.enabled else "") for e in self.entries).strip()

    @staticmethod
    def edited_token(entry, value):
        if value is None:
            return entry.key
        if not re.fullmatch(r"[A-Za-z0-9_.+\-]+", entry.key):
            raise ValueError("This argument's spelling is unusual. Edit it in Advanced OpenCore settings.")
        raw = entry.key + "=" + value
        pattern = r'''(?:[^\s"'\\]|\\.|"(?:\\.|[^"\\])*"|'[^']*')+'''
        if any(c in raw for c in "\x00\r\n") or not re.fullmatch(pattern, raw):
            raise ValueError(f"{entry.key}: enter one value; put values containing spaces in quotes.")
        spec = entry.spec
        # Preserve unfamiliar existing values until that row is actually edited.
        if spec and spec.kind != "text":
            try:
                number = int(value, 16 if value.lower().startswith("0x") else 10)
            except ValueError:
                raise ValueError(f"{entry.key}: enter a number" + (" in decimal or 0x hex." if spec.kind == "mask" else ".")) from None
            low, high = {"bool": (0, 1), "heads": (1, 4), "delay": (0, 999999), "mask": (0, 0xffffffff)}[spec.kind]
            if not low <= number <= high or (spec.kind == "delay" and not re.fullmatch(r"\d{1,6}", value)):
                raise ValueError(f"{entry.key}: use a value from {low} to {high}" + (" in decimal." if spec.kind == "delay" else "."))
        return raw
