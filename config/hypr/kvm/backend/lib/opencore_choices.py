"""Named OpenCore security choices; retain unknown values instead of coercing them.

SIP flags: https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/csr.h
ROM and SecureBootModel: OpenCorePkg/Docs/Configuration.tex.
"""

SIP_CHOICES = (
    ("SIP protections enabled", bytes.fromhex("00000000")),
    ("Driver permissions + unsigned system volume", bytes.fromhex("430a0000")),
    ("Driver permissions; keep system-volume verification", bytes.fromhex("43020000")),
)
SIP_PERMISSIONS = (
    "untrusted kernel extensions", "unrestricted filesystem access", "task debugging",
    "kernel debugging", "Apple-internal features", "unrestricted DTrace",
    "unrestricted NVRAM access", "device configuration changes", "any Recovery OS",
    "unapproved kernel extensions", "executable-policy overrides",
    "an unauthenticated system volume", "research guests",
)
SECURE_BOOT_CHOICES = (
    ("Disabled — custom driver compatibility", "Disabled",
     "Apple Secure Boot verification is disabled. The working custom NVIDIA setup uses this. This is separate from SIP and host UEFI Secure Boot."),
    ("Default — OpenCore model policy", "Default",
     "Use this OpenCore version's default Apple Secure Boot model policy. Enabling verification can prevent custom drivers or modified macOS installations from booting."),
    ("x86legacy — virtual machine / non-T2 Mac", "x86legacy",
     "Use the non-T2 / VM Apple Secure Boot model (macOS 11.0.1 or newer). Requires a compatible installation and security configuration."),
)


def sip_description(value):
    if value is None:
        return "No SIP override is stored in this image. The existing NVRAM / macOS policy is retained."
    if not isinstance(value, bytes) or len(value) != 4:
        return "This existing value is not four bytes. Correct it in Advanced OpenCore settings before applying."
    mask = int.from_bytes(value, "little")
    allowed = [name for bit, name in enumerate(SIP_PERMISSIONS) if mask & (1 << bit)]
    if mask >> len(SIP_PERMISSIONS):
        allowed.append("additional flags not described by this editor")
    text = "No SIP exceptions are requested." if mask == 0 else "Permits: " + "; ".join(allowed) + "."
    return (text + f" Stored bytes: {value.hex()} (mask 0x{mask:X}). "
            "Change only for a specific driver or system modification; enabling protections can stop an installed custom driver from loading.")


def rom_address(value):
    return value.hex(":").upper() if isinstance(value, bytes) else str(value)
