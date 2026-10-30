#!/usr/bin/env python3
"""TPM identity tab for vmstart_2.

Every fixed property a TPM reports about itself, editable in one place, with a
one-click random value for each. Replaces having to hand-edit
tpm_real_dump.env and remember which script regenerates what.

The pipeline this drives is the existing one, not a new one:

    tpm_real_dump.env
        -> scripts/gen-tpm-vendor-identity-h.sh
        -> libtpms/src/tpm_vendor_identity.h
        -> rebuild libtpms + swtpm (xetaltpm.sh --no-tpm-dump)

The identity is compiled into libtpms, so nothing here takes effect until that
rebuild happens. The tab says so rather than letting you believe otherwise.
"""

import json
import os
import re
import subprocess
import time

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
                             QPushButton, QLineEdit, QScrollArea, QGridLayout,
                             QComboBox, QPlainTextEdit, QMessageBox, QFileDialog, QSplitter,
                             QCheckBox, QRadioButton, QButtonGroup)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont

import randomize
from uiutil import guard_all, sudo_command

MONO = "Monospace"

from portable import data_root
TPM_ROOT = str(data_root() / "tpm-workspace")

# (env key, label, kind, tooltip)
#   u32   - 32-bit value, shown as hex
#   ascii4- 32-bit value that is really four ASCII bytes ("AMD\0")
#   str   - free text baked into the JSON model name
#   dec   - plain decimal
FIELDS = [
    ("TPM_PT_MANUFACTURER", "Manufacturer", "ascii4",
     "TPM2_PT_MANUFACTURER. Four ASCII bytes identifying the vendor: AMD, INTC, "
     "IFX, STM, NTC. This is the single most checked TPM property."),
    ("TPM_IDENT_MODEL_JSON_TPM2", "Model (TPM 2.0)", "str",
     "Model name swtpm reports in its JSON capabilities, e.g. 'AMD fTPM'."),
    ("TPM_IDENT_MODEL_JSON_TPM12", "Model (TPM 1.2)", "str",
     "Model name for the 1.2 code path."),
    ("TPM_PT_VENDOR_STRING_1", "Vendor string 1", "ascii4",
     "TPM2_PT_VENDOR_STRING_1. Four more ASCII bytes; on a real AMD fTPM this "
     "repeats the manufacturer."),
    ("TPM_PT_VENDOR_STRING_2", "Vendor string 2", "ascii4", "Usually zero."),
    ("TPM_PT_VENDOR_STRING_3", "Vendor string 3", "ascii4", "Usually zero."),
    ("TPM_PT_VENDOR_STRING_4", "Vendor string 4", "ascii4", "Usually zero."),
    ("TPM_PT_FIRMWARE_VERSION_1", "Firmware version 1", "u32",
     "TPM2_PT_FIRMWARE_VERSION_1. High half of the firmware version; the value "
     "Windows shows in tpm.msc."),
    ("TPM_PT_FIRMWARE_VERSION_2", "Firmware version 2", "u32",
     "TPM2_PT_FIRMWARE_VERSION_2. Low half."),
    ("TPM_PT_VENDOR_TPM_TYPE", "Vendor TPM type", "u32",
     "TPM2_PT_VENDOR_TPM_TYPE. 1 on every discrete and firmware TPM seen so far."),
    ("TPM2_PT_LEVEL", "Spec level", "dec",
     "TPM2_PT_LEVEL. Specification level, 0 for TPM 2.0."),
    ("TPM2_PT_REVISION", "Spec revision", "u32",
     "TPM2_PT_REVISION. Spec revision times 100: 0x9F is 1.59."),
    ("TPM2_PT_YEAR", "Spec year", "dec",
     "TPM2_PT_YEAR. Year of the spec revision, e.g. 2020."),
    ("TPM2_PT_DAY_OF_YEAR", "Spec day of year", "dec",
     "TPM2_PT_DAY_OF_YEAR. Day within that year, 1-366."),
    ("TPM2_PT_PS_FAMILY_INDICATOR", "Platform family", "dec",
     "TPM2_PT_PS_FAMILY_INDICATOR. Platform-specific family, 1 for PC Client."),
    ("TPM2_PT_PS_LEVEL", "Platform level", "dec", "TPM2_PT_PS_LEVEL."),
    ("TPM2_PT_PS_REVISION", "Platform revision", "u32",
     "TPM2_PT_PS_REVISION. 0x105 is PC Client profile 1.05."),
    ("TPM2_PT_PS_YEAR", "Platform year", "dec", "TPM2_PT_PS_YEAR."),
    ("TPM2_PT_PS_DAY_OF_YEAR", "Platform day of year", "dec", "TPM2_PT_PS_DAY_OF_YEAR."),
]

# Fields defined by the TPM specification rather than by the vendor. A real
# part cannot report anything else here, so randomising them produces a device
# that claims, say, spec revision 292270 -- a far louder signal than the value
# they replaced. Regenerate leaves them alone and says why.
STRUCTURAL = {
    "TPM_PT_VENDOR_TPM_TYPE", "TPM2_PT_LEVEL", "TPM2_PT_REVISION",
    "TPM2_PT_YEAR", "TPM2_PT_DAY_OF_YEAR", "TPM2_PT_PS_FAMILY_INDICATOR",
    "TPM2_PT_PS_LEVEL", "TPM2_PT_PS_REVISION", "TPM2_PT_PS_YEAR",
    "TPM2_PT_PS_DAY_OF_YEAR",
}

# Four-byte vendor codes that belong to real TPM makers. A manufacturer field
# is checked against lists like this, so a random one fails where an unchanged
# one would have passed.
REAL_VENDORS = [
    ("0x414D4400", "AMD"), ("0x494E5443", "INTC"), ("0x49465800", "IFX"),
    ("0x53544D20", "STM"), ("0x4E544300", "NTC"), ("0x4252434D", "BRCM"),
    ("0x4D534654", "MSFT"), ("0x54584E00", "TXN"), ("0x534D5343", "SMSC"),
]

# Identities that match real hardware. Values are what those parts actually
# report, so a guest checking them sees a coherent device rather than a
# plausible-looking mixture.
PRESETS = {
    "AMD fTPM (Raphael/Granite Ridge)": {
        "TPM_PT_MANUFACTURER": "0x414D4400", "TPM_IDENT_MODEL_JSON_TPM2": "AMD fTPM",
        "TPM_IDENT_MODEL_JSON_TPM12": "AMD",
        "TPM_PT_VENDOR_STRING_1": "0x414D4400", "TPM_PT_VENDOR_STRING_2": "0x0",
        "TPM_PT_VENDOR_STRING_3": "0x0", "TPM_PT_VENDOR_STRING_4": "0x0",
        "TPM_PT_FIRMWARE_VERSION_1": "0x6001F", "TPM_PT_FIRMWARE_VERSION_2": "0x6",
        "TPM_PT_VENDOR_TPM_TYPE": "0x1", "TPM2_PT_LEVEL": "0",
        "TPM2_PT_REVISION": "0x9F", "TPM2_PT_YEAR": "2020",
        "TPM2_PT_DAY_OF_YEAR": "170", "TPM2_PT_PS_FAMILY_INDICATOR": "1",
        "TPM2_PT_PS_LEVEL": "0", "TPM2_PT_PS_REVISION": "0x105",
        "TPM2_PT_PS_YEAR": "2020", "TPM2_PT_PS_DAY_OF_YEAR": "170",
    },
    "Intel PTT (firmware TPM)": {
        "TPM_PT_MANUFACTURER": "0x494E5443", "TPM_IDENT_MODEL_JSON_TPM2": "Intel PTT",
        "TPM_IDENT_MODEL_JSON_TPM12": "INTC",
        "TPM_PT_VENDOR_STRING_1": "0x494E5443", "TPM_PT_VENDOR_STRING_2": "0x0",
        "TPM_PT_VENDOR_STRING_3": "0x0", "TPM_PT_VENDOR_STRING_4": "0x0",
        "TPM_PT_FIRMWARE_VERSION_1": "0x600", "TPM_PT_FIRMWARE_VERSION_2": "0x1D000C",
        "TPM_PT_VENDOR_TPM_TYPE": "0x1", "TPM2_PT_LEVEL": "0",
        "TPM2_PT_REVISION": "0x8A", "TPM2_PT_YEAR": "2016",
        "TPM2_PT_DAY_OF_YEAR": "303", "TPM2_PT_PS_FAMILY_INDICATOR": "1",
        "TPM2_PT_PS_LEVEL": "0", "TPM2_PT_PS_REVISION": "0x100",
        "TPM2_PT_PS_YEAR": "2016", "TPM2_PT_PS_DAY_OF_YEAR": "303",
    },
    "Infineon SLB9665 (discrete)": {
        "TPM_PT_MANUFACTURER": "0x49465800", "TPM_IDENT_MODEL_JSON_TPM2": "SLB9665",
        "TPM_IDENT_MODEL_JSON_TPM12": "IFX",
        "TPM_PT_VENDOR_STRING_1": "0x534C4239", "TPM_PT_VENDOR_STRING_2": "0x36363500",
        "TPM_PT_VENDOR_STRING_3": "0x0", "TPM_PT_VENDOR_STRING_4": "0x0",
        "TPM_PT_FIRMWARE_VERSION_1": "0x50028", "TPM_PT_FIRMWARE_VERSION_2": "0x1F",
        "TPM_PT_VENDOR_TPM_TYPE": "0x1", "TPM2_PT_LEVEL": "0",
        "TPM2_PT_REVISION": "0x8A", "TPM2_PT_YEAR": "2016",
        "TPM2_PT_DAY_OF_YEAR": "303", "TPM2_PT_PS_FAMILY_INDICATOR": "1",
        "TPM2_PT_PS_LEVEL": "0", "TPM2_PT_PS_REVISION": "0x100",
        "TPM2_PT_PS_YEAR": "2016", "TPM2_PT_PS_DAY_OF_YEAR": "303",
    },
    "STMicroelectronics ST33 (discrete)": {
        "TPM_PT_MANUFACTURER": "0x53544D20", "TPM_IDENT_MODEL_JSON_TPM2": "ST33TPHF20",
        "TPM_IDENT_MODEL_JSON_TPM12": "STM",
        "TPM_PT_VENDOR_STRING_1": "0x53543333", "TPM_PT_VENDOR_STRING_2": "0x48544620",
        "TPM_PT_VENDOR_STRING_3": "0x0", "TPM_PT_VENDOR_STRING_4": "0x0",
        "TPM_PT_FIRMWARE_VERSION_1": "0x10048", "TPM_PT_FIRMWARE_VERSION_2": "0x0",
        "TPM_PT_VENDOR_TPM_TYPE": "0x1", "TPM2_PT_LEVEL": "0",
        "TPM2_PT_REVISION": "0x8A", "TPM2_PT_YEAR": "2016",
        "TPM2_PT_DAY_OF_YEAR": "303", "TPM2_PT_PS_FAMILY_INDICATOR": "1",
        "TPM2_PT_PS_LEVEL": "0", "TPM2_PT_PS_REVISION": "0x100",
        "TPM2_PT_PS_YEAR": "2016", "TPM2_PT_PS_DAY_OF_YEAR": "303",
    },
}


FIELDS_ORDER = [k for k, _l, _kd, _t in FIELDS]

# Which #define in tpm_vendor_identity.h each field ends up as. The spec and
# platform values are not in tpm_real_dump.env at all -- the generator defaults
# them -- so without this they would read back as blank and get written out as
# zero, quietly flattening a correct identity.
HEADER_KEYS = {
    "TPM_PT_MANUFACTURER": "TPM_IDENT_MANUFACTURER_U32",
    "TPM_PT_VENDOR_STRING_1": None,
    "TPM_PT_FIRMWARE_VERSION_1": "TPM_IDENT_FIRMWARE_V1",
    "TPM_PT_FIRMWARE_VERSION_2": "TPM_IDENT_FIRMWARE_V2",
    "TPM_PT_VENDOR_TPM_TYPE": "TPM_IDENT_VENDOR_TPM_TYPE",
    "TPM2_PT_LEVEL": "TPM_IDENT_SPEC_LEVEL",
    "TPM2_PT_REVISION": "TPM_IDENT_SPEC_VERSION",
    "TPM2_PT_YEAR": "TPM_IDENT_SPEC_YEAR",
    "TPM2_PT_DAY_OF_YEAR": "TPM_IDENT_SPEC_DAY_OF_YEAR",
    "TPM2_PT_PS_FAMILY_INDICATOR": "TPM_IDENT_PLATFORM_FAMILY",
    "TPM2_PT_PS_LEVEL": "TPM_IDENT_PLATFORM_LEVEL",
    "TPM2_PT_PS_REVISION": "TPM_IDENT_PLATFORM_REVISION",
    "TPM2_PT_PS_YEAR": "TPM_IDENT_PLATFORM_YEAR",
    "TPM2_PT_PS_DAY_OF_YEAR": "TPM_IDENT_PLATFORM_DAY_OF_YEAR",
    "TPM_IDENT_MODEL_JSON_TPM2": "TPM_IDENT_MODEL_JSON_TPM2",
    "TPM_IDENT_MODEL_JSON_TPM12": "TPM_IDENT_MODEL_JSON_TPM12",
}


def _parse_header(path):
    """Current values straight out of tpm_vendor_identity.h."""
    out = {}
    if not os.path.isfile(path):
        return out
    for line in open(path):
        m = re.match(r"#define\s+(\S+)\s+(.+)$", line.strip())
        if not m:
            continue
        name, val = m.group(1), m.group(2).strip()
        val = re.sub(r"^\((.*)\)$", r"\1", val).strip()
        val = re.sub(r"[uU]$", "", val)
        out[name] = val.strip('"')
    return out


def _to_ascii(value):
    """0x414D4400 -> 'AMD\\0' rendered readably."""
    try:
        n = int(str(value), 0)
    except (ValueError, TypeError):
        return ""
    out = []
    for shift in (24, 16, 8, 0):
        b = (n >> shift) & 0xFF
        out.append(chr(b) if 32 <= b < 127 else ("\\0" if b == 0 else f"\\x{b:02x}"))
    return "".join(out)


def _from_ascii(text):
    """'AMD' -> 0x414D4400, padded with NULs to four bytes."""
    raw = text.encode("latin-1", errors="replace")[:4]
    raw = raw + b"\0" * (4 - len(raw))
    return "0x%08X" % int.from_bytes(raw, "big")


class TpmTab(QScrollArea):
    changed = pyqtSignal()
    checks_changed = pyqtSignal()

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.widgets = {}
        self.setWidgetResizable(True)
        if cfg.profile == "macos" and not cfg.simple.get("tpmdev"):
            body = QWidget()
            layout = QVBoxLayout(body)
            note = QLabel("This Mac profile uses Apple SMC and OpenCore. No TPM is configured.")
            note.setWordWrap(True)
            layout.addWidget(note)
            layout.addStretch()
            self.setWidget(body)
            return
        self._build()
        self.load_env()
        self.state_dir.setText(self._state_path())
        self.check_attestation()
        guard_all(self)

    # -------------------------------------------------------------- paths ---
    def paths(self):
        t = self.cfg.data.setdefault("tools", {})
        root = t.setdefault("tpm_root", TPM_ROOT)
        return {
            "root": root,
            "env": os.path.join(root, "tpm_real_dump.env"),
            "gen": os.path.join(root, "scripts", "gen-tpm-vendor-identity-h.sh"),
            "dump": os.path.join(root, "scripts", "dump-real-tpm.sh"),
            "header": os.path.join(root, "libtpms", "src", "tpm_vendor_identity.h"),
            "build": os.path.join(root, "xetaltpm.sh"),
        }

    # -------------------------------------------------------------- build ---
    def _build(self):
        w = QWidget()
        self.setWidget(w)
        outer = QVBoxLayout(w)

        # Keep the action that makes edited values effective above the fields.
        self.identity_actions = QWidget()
        actions = QHBoxLayout(self.identity_actions)
        actions.setContentsMargins(0, 0, 0, 0)
        self.btn_apply_identity = QPushButton("Apply TPM Identity (rebuild)")
        self.btn_apply_identity.setObjectName("accent")
        self.btn_apply_identity.setToolTip(
            "Save the identity, regenerate the header and rebuild libtpms + swtpm. "
            "Takes several minutes; shut down the VM first.")
        self.btn_apply_identity.clicked.connect(self._rebuild)
        actions.addWidget(self.btn_apply_identity)
        for text, slot, tip in (
                ("Save to .env only", self.save_env,
                 "Save the edited identity without rebuilding or applying it."),
                ("Generate header only", self._regen_header,
                 "Save the identity and regenerate its header. A rebuild is still required.")):
            button = QPushButton(text)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch()
        outer.addWidget(self.identity_actions)
        head = QLabel(
            "Apply TPM Identity rebuilds the emulated TPM for the next VM launch. "
            "Shut down the VM before applying. Keys and NV state have their own actions below.")
        head.setWordWrap(True)
        outer.addWidget(head)

        self._source_grid = QGridLayout()
        self._source_grid.setContentsMargins(0, 0, 0, 0)
        self._source_grid.setHorizontalSpacing(12)
        outer.addLayout(self._source_grid)
        self._body_grid = QGridLayout()
        self._body_grid.setContentsMargins(0, 0, 0, 0)
        self._body_grid.setSpacing(12)
        outer.addLayout(self._body_grid)
        outer.addStretch(1)

        # ---- which TPM the guest actually gets --------------------------------
        bbox = QGroupBox("0. Which TPM the guest gets")
        bg = QGridLayout(bbox)
        bg.setContentsMargins(8, 4, 8, 6)
        bg.setVerticalSpacing(3)

        self.rb_emulated = QRadioButton("Emulated (swtpm)")
        self.rb_emulated.setToolTip(
            "The software TPM, with the identity built below. This is the normal "
            "choice: the guest gets its own chip with its own state.")
        self.rb_passthrough = QRadioButton("Passthrough (this machine's real TPM)")
        self.rb_passthrough.setToolTip(
            "Hand the guest the physical chip. Everything below stops applying: "
            "the guest reports the real hardware, not the identity in section 2.")
        self.backend_group = QButtonGroup(self)
        self.backend_group.addButton(self.rb_emulated)
        self.backend_group.addButton(self.rb_passthrough)
        bg.addWidget(self.rb_emulated, 0, 0, 1, 2)
        bg.addWidget(self.rb_passthrough, 0, 2, 1, 2)

        self.pt_path = QLineEdit()
        self.pt_path.setToolTip("Host TPM character device handed to the guest.")
        self.pt_cancel = QLineEdit()
        self.pt_cancel.setToolTip(
            "Sysfs node QEMU writes to in order to cancel a command. A CRB "
            "firmware TPM exposes none, and /dev/null makes cancellation a "
            "no-op, which is what QEMU needs to start at all.")
        bg.addWidget(QLabel("path:"), 2, 0)
        bg.addWidget(self.pt_path, 2, 1)
        bg.addWidget(QLabel("cancel-path:"), 2, 2)
        bg.addWidget(self.pt_cancel, 2, 3)

        self.pt_warn = QLabel("")
        self.pt_warn.setWordWrap(True)
        bg.addWidget(self.pt_warn, 3, 0, 1, 4)
        bg.setRowStretch(4, 1)
        bg.setColumnStretch(1, 1)
        bg.setColumnStretch(3, 1)

        pbox = QGroupBox("1. Pick an identity")
        pg = QGridLayout(pbox)
        pg.setContentsMargins(8, 4, 8, 6)
        self.preset = QComboBox()
        for name in PRESETS:
            self.preset.addItem(name, name)
        pg.addWidget(self.preset, 0, 0)
        b = QPushButton("Load preset")
        b.setToolTip("Fill the fields from this preset. Apply TPM Identity to make them effective.")
        b.clicked.connect(self._apply_preset)
        pg.addWidget(b, 0, 1)
        b = QPushButton("Copy this machine's TPM")
        b.setToolTip("Read the real chip and load its values. Read only.")
        b.clicked.connect(self._dump_physical)
        pg.addWidget(b, 1, 0)
        b = QPushButton("Randomise vendor identity")
        b.setToolTip("New manufacturer, vendor strings, model and firmware "
                     "version. Spec-defined fields are left alone.")
        b.clicked.connect(self._regen_all)
        pg.addWidget(b, 1, 1)
        pg.setColumnStretch(0, 1)
        pg.setColumnStretch(1, 1)

        # ---- identity fields, compact ---------------------------------------
        fbox = QGroupBox("2. What it reports")
        fbox_lay = QVBoxLayout(fbox)
        fbox_lay.setContentsMargins(4, 4, 4, 4)
        fields_host = QWidget()
        fg = self._fields_grid = QGridLayout(fields_host)
        fg.setContentsMargins(4, 0, 4, 0)
        fg.setVerticalSpacing(2)
        fg.setHorizontalSpacing(4)
        self._field_rows = []
        self._field_headings = []
        for title in ("Vendor and firmware", "Specification and platform"):
            heading = QLabel(title)
            heading.setStyleSheet("font-weight: bold;")
            self._field_headings.append(heading)
        for key, label, kind, tip in FIELDS:
            lb = QLabel(label + ":")
            lb.setToolTip(tip)

            ed = QLineEdit()
            ed.setToolTip(tip)
            ed.setFixedWidth(120)
            ed.textEdited.connect(lambda _t, k=key: self._on_edit(k))

            decoded = QLabel("")
            decoded.setStyleSheet("color: #888;")
            decoded.setMinimumWidth(80)
            decoded.setToolTip(tip)

            rb = QPushButton("Regen")
            rb.setMinimumWidth(80)
            if key in STRUCTURAL:
                rb.setEnabled(False)
                rb.setText("spec")
                rb.setToolTip("Fixed by the TPM specification. A real part cannot "
                              "report anything else, so changing it would stand "
                              "out more than leaving it.")
            else:
                rb.setToolTip("Random value of the right shape for this field")
                rb.clicked.connect(lambda _c, k=key: self._regen(k))
            self._field_rows.append((lb, ed, decoded, rb))
            self.widgets[key] = {"edit": ed, "decoded": decoded, "kind": kind}

        # Both field groups stay visible; on smaller windows they stack.
        fbox_lay.addWidget(fields_host)
        fbox_lay.addStretch(1)

        # ---- keys and NV state ------------------------------------------------
        kbox = QGroupBox("3. Keys and NV state")
        kg = QGridLayout(kbox)
        kg.setContentsMargins(8, 4, 8, 6)
        kg.setVerticalSpacing(3)
        r = 0
        self.state_dir = QLineEdit()
        self.state_dir.setToolTip("Where the NV store, EK and certificates live.")
        self.state_dir.textEdited.connect(lambda t: self._set_state_dir(t))
        kg.addWidget(QLabel("State dir:"), r, 0)
        kg.addWidget(self.state_dir, r, 1, 1, 2)
        bb = QPushButton("...")
        bb.setFixedWidth(28)
        bb.clicked.connect(self._browse_state)
        kg.addWidget(bb, r, 3)
        r += 1

        self.ek_algo = QComboBox()
        for v, d in (("rsa2048", "RSA 2048. What most discrete TPMs ship with."),
                     ("rsa3072", "RSA 3072."),
                     ("ecc256", "ECC NIST P-256. Typical of firmware TPMs."),
                     ("ecc384", "ECC NIST P-384.")):
            self.ek_algo.addItem(v, v)
            self.ek_algo.setItemData(self.ek_algo.count() - 1, d,
                                     Qt.ItemDataRole.ToolTipRole)
        kg.addWidget(QLabel("EK type:"), r, 0)
        kg.addWidget(self.ek_algo, r, 1)
        self.pcr_banks = QLineEdit("sha1,sha256")
        self.pcr_banks.setToolTip("PCR banks to activate. Windows measures into "
                                  "sha1 and sha256; without sha256 attestation "
                                  "fails.")
        kg.addWidget(QLabel("PCR banks:"), r, 2)
        kg.addWidget(self.pcr_banks, r, 3)
        r += 1

        self.chk_ekcert = QCheckBox("EK certificate")
        self.chk_ekcert.setChecked(True)
        self.chk_ekcert.setToolTip("Required. Without it Windows reports "
                                   "INFORMATION_EK_CERTIFICATE and 'Ready For "
                                   "Attestation' is False.")
        self.chk_platcert = QCheckBox("Platform certificate")
        self.chk_platcert.setChecked(True)
        self.chk_lock = QCheckBox("Lock NVRAM")
        self.chk_lock.setToolTip("Matches a shipped part, which will not let you "
                                 "rewrite its NV area.")
        kg.addWidget(self.chk_ekcert, r, 0, 1, 2)
        kg.addWidget(self.chk_platcert, r, 2, 1, 2)
        r += 1
        kg.addWidget(self.chk_lock, r, 0, 1, 2)
        r += 1

        for i, (text, slot, tip) in enumerate((
                ("New EK + certificates", self._new_ek,
                 "Re-provision the EMULATED TPM's endorsement key and certs. "
                 "BitLocker keys sealed to the old TPM will not unseal."),
                ("Back up state", self._backup_state, "Timestamped copy"),
                ("Restore state", self._restore_state, "Restore from the backup"),
                ("Mirror physical NV layout", self._mirror_nv,
                 "Recreate the real chip's NV index layout"))):
            bt = QPushButton(text)
            bt.setToolTip(tip)
            bt.clicked.connect(slot)
            kg.addWidget(bt, r + i // 2, (i % 2) * 2, 1, 2)
        kg.setColumnStretch(1, 1)
        kg.setColumnStretch(3, 1)
        kg.setRowStretch(r + 2, 1)

        # ============================ verdict and details ====================
        vbox = QGroupBox("TPM checks")
        vl = QVBoxLayout(vbox)
        vl.setContentsMargins(8, 4, 8, 6)
        status_row = QHBoxLayout()
        self.verdict = QLabel("not checked yet")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        self.verdict.setFont(f)
        status_row.addWidget(self.verdict, 1)
        self.btn_repair = QPushButton('Install / initialize TPM')
        self.btn_repair.setToolTip('Download missing TPM tools and initialize an empty private state directory. Existing keys are preserved.')
        status_row.addWidget(self.btn_repair)
        rb2 = QPushButton("Re-check")
        rb2.clicked.connect(self.check_attestation)
        status_row.addWidget(rb2)
        self.btn_check_details = QPushButton("Show checks")
        self.btn_check_details.setCheckable(True)
        self.btn_check_details.toggled.connect(self._toggle_checks)
        status_row.addWidget(self.btn_check_details)
        vl.addLayout(status_row)
        self.check_summary = QLabel()
        self.check_summary.setWordWrap(True)
        vl.addWidget(self.check_summary)
        self.checks = QPlainTextEdit()
        self.checks.setReadOnly(True)
        self.checks.setFont(QFont(MONO, 9))
        self.checks.setFixedHeight(150)
        self.checks.hide()
        vl.addWidget(self.checks)

        ibox = QGroupBox("Details")
        il = QVBoxLayout(ibox)
        il.setContentsMargins(8, 4, 8, 6)
        row = QGridLayout()
        for i, (text, slot) in enumerate((("Current NV state", self._show_state),
                           ("Reload from .env", self.load_env),
                           ("Current header", self._show_header),
                           ("Installed swtpm", self._show_live),
                           ("Compare to real chip", self._verify_physical))):
            bt = QPushButton(text)
            bt.clicked.connect(slot)
            row.addWidget(bt, i // 2, i % 2)
        il.addLayout(row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont(MONO, 9))
        self.log.setMinimumHeight(90)
        self.log.setMaximumHeight(100)
        il.addWidget(self.log)

        # ============================ assembly ===============================
        outer.insertWidget(2, vbox)
        self._cards = (bbox, pbox, fbox, kbox, ibox)
        self._layout_mode = None
        self._arrange_cards()

        # These controls build the EMULATED chip's identity. Under passthrough the
        # guest talks to real silicon and none of it applies, so they are greyed
        # rather than left looking live.
        self._emulated_only = [pbox, fbox, kbox, self.identity_actions]
        self._load_backend()
        self.rb_emulated.toggled.connect(self._on_backend_toggled)
        for e in (self.pt_path, self.pt_cancel):
            e.textEdited.connect(lambda _t: self._apply_backend())

    def _toggle_checks(self, expanded):
        self.checks.setVisible(expanded)
        self.btn_check_details.setText("Hide checks" if expanded else "Show checks")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_cards"):
            self._arrange_cards()

    def _arrange_cards(self):
        """Use the available width without recreating editors or losing edits."""
        width = self.viewport().width()
        mode = "wide" if width >= 1250 else "medium" if width >= 900 else "narrow"
        if mode == self._layout_mode:
            return
        self._layout_mode = mode
        for grid in (self._source_grid, self._body_grid, self._fields_grid):
            while grid.count():
                grid.takeAt(0)
            for col in range(grid.columnCount()):
                grid.setColumnStretch(col, 0)
                grid.setColumnMinimumWidth(col, 0)

        bbox, pbox, fbox, kbox, ibox = self._cards
        sg, bg, fg = self._source_grid, self._body_grid, self._fields_grid
        sg.addWidget(bbox, 0, 0)
        sg.addWidget(pbox, 1 if mode == "narrow" else 0, 0 if mode == "narrow" else 1)
        sg.setColumnStretch(0, 1)
        sg.setColumnStretch(1, 0 if mode == "narrow" else 1)
        if mode == "wide":
            bg.addWidget(fbox, 0, 0, 2, 1)
            bg.addWidget(kbox, 0, 1)
            bg.addWidget(ibox, 1, 1)
            bg.setColumnStretch(0, 2)
            bg.setColumnStretch(1, 1)
        elif mode == "medium":
            bg.addWidget(fbox, 0, 0, 1, 2)
            bg.addWidget(kbox, 1, 0)
            bg.addWidget(ibox, 1, 1)
            bg.setColumnStretch(0, 1)
            bg.setColumnStretch(1, 1)
        else:
            for row, card in enumerate((fbox, kbox, ibox)):
                bg.addWidget(card, row, 0)
            bg.setColumnStretch(0, 1)

        # Nine vendor/firmware fields, then ten specification/platform fields.
        for group, (start, end) in enumerate(((0, 9), (9, len(FIELDS)))):
            col = 5 * group if mode != "narrow" else 0
            start_row = 11 * group if mode == "narrow" else 0
            fg.addWidget(self._field_headings[group], start_row, col, 1, 4)
            for row, widgets in enumerate(self._field_rows[start:end], start_row + 1):
                for offset, widget in enumerate(widgets):
                    fg.addWidget(widget, row, col + offset)
            fg.setColumnStretch(col + 2, 1)
        if mode != "narrow":
            fg.setColumnMinimumWidth(4, 24)

    # ------------------------------------------------------------ backend ---
    def _load_backend(self):
        """Restore the saved choice, falling back to what -tpmdev already says."""
        tpmdev = self.cfg.simple.get("tpmdev", "")
        mode = self.cfg.data.get("tpm_backend")
        if mode not in ("emulator", "passthrough"):
            mode = "passthrough" if tpmdev.startswith("passthrough") else "emulator"

        m = re.search(r"\bpath=([^,]+)", tpmdev)
        self.pt_path.setText(m.group(1) if m and tpmdev.startswith("passthrough")
                             else self._default_tpm_path())
        m = re.search(r"cancel-path=([^,]+)", tpmdev)
        self.pt_cancel.setText(m.group(1) if m else "/dev/null")

        self._loading_backend = True
        (self.rb_emulated if mode == "emulator" else self.rb_passthrough).setChecked(True)
        self._loading_backend = False
        # Re-apply rather than only painting the radio. A session saved under
        # passthrough must come back with the device model and chardev already
        # consistent; setChecked() on an already-checked button emits nothing, so
        # without this the config keeps whatever it was saved with and QEMU dies
        # at startup.
        self._apply_backend(emit=False)

    @staticmethod
    def _default_tpm_path():
        for p in ("/dev/tpm0", "/dev/tpmrm0"):
            if os.path.exists(p):
                return p
        return "/dev/tpm0"

    def _on_backend_toggled(self, *_):
        if getattr(self, "_loading_backend", False):
            return
        self._apply_backend()

    def _apply_backend(self, emit=True):
        """Rewrite -tpmdev for the selected backend, keeping the device wired."""
        mode = "emulator" if self.rb_emulated.isChecked() else "passthrough"
        cur = self.cfg.simple.get("tpmdev", "")
        m = re.search(r"\bid=([^,]+)", cur)
        # The -device tpm-* references this id; changing it would orphan it.
        tid = m.group(1) if m else "tpm-tpm0"

        # Whichever way we are switching, the chardev name has to survive the
        # round trip: it is only spelled out in the emulator form of -tpmdev, so
        # it is recorded before that string is overwritten.
        m = re.search(r"chardev=([^,]+)", cur)
        if m:
            self.cfg.data["tpm_chardev"] = m.group(1)
        chardev = self.cfg.data.get("tpm_chardev") or "chrtpm"

        if mode == "emulator":
            self.cfg.simple["tpmdev"] = f"emulator,id={tid},chardev={chardev}"
        else:
            path = self.pt_path.text().strip() or self._default_tpm_path()
            cancel = self.pt_cancel.text().strip() or "/dev/null"
            self.cfg.simple["tpmdev"] = (f"passthrough,id={tid},path={path},"
                                         f"cancel-path={cancel}")

        # tpm-crb's command buffer is fixed at 3968 bytes. A real chip reporting
        # a 4096-byte buffer makes QEMU abort at realize -- "Requested buffer
        # size of 3968 is smaller than host TPM's fixed buffer size of 4096",
        # exit 1, before the guest ever starts. tpm-tis passes the host buffer
        # through, so passthrough has to use it. Emulated keeps tpm-crb, which is
        # the interface a real AMD fTPM presents and which swtpm is happy with.
        dev = next((d for d in self.cfg.devices
                    if str(d.get("driver", "")).startswith("tpm-")
                    and not d.get("_disabled")), None)
        if dev is not None:
            if mode == "passthrough":
                if dev.get("driver") != "tpm-tis":
                    self.cfg.data["tpm_model_emulated"] = dev.get("driver")
                    dev["driver"] = "tpm-tis"
            else:
                dev["driver"] = (self.cfg.data.get("tpm_model_emulated")
                                 or "tpm-crb")

        # The swtpm socket chardev is a client connect. Under passthrough nothing
        # starts swtpm, so leaving it on the command line makes QEMU abort with
        # "Failed to connect" before the guest exists.
        for c in self.cfg.data.get("chardevs", []):
            if c.get("id") == chardev:
                if mode == "passthrough":
                    c["_disabled"] = True
                else:
                    c.pop("_disabled", None)

        self.cfg.data["tpm_backend"] = mode
        self._sync_backend_ui(mode)
        if emit:
            self.changed.emit()
            self.check_attestation()

    def _sync_backend_ui(self, mode):
        passthru = mode == "passthrough"
        for box in getattr(self, "_emulated_only", []):
            box.setEnabled(not passthru)
        self.pt_path.setEnabled(passthru)
        self.pt_cancel.setEnabled(passthru)
        if not passthru:
            self.pt_warn.setText("")
            self.pt_warn.hide()
            return
        missing = not os.path.exists(self.pt_path.text().strip())
        msgs = ["The guest takes exclusive control of the real chip: the host "
                "loses its TPM while the VM runs, PCRs reflect the host's boot "
                "rather than the guest's, and guest writes to NV are permanent."]
        if missing:
            msgs.append(f"{self.pt_path.text().strip()} does not exist.")
        self.pt_warn.setText("  ".join(msgs))
        self.pt_warn.setStyleSheet("color: #e06c75;" if missing else "color: #d19a66;")
        self.pt_warn.show()

    # --------------------------------------------------------------- edit ---
    def _on_edit(self, key):
        self._decode(key)
        self.changed.emit()

    def _decode(self, key):
        w = self.widgets[key]
        v = w["edit"].text().strip()
        if w["kind"] == "ascii4":
            w["decoded"].setText(f'"{_to_ascii(v)}"' if v else "")
        elif w["kind"] == "u32":
            try:
                w["decoded"].setText(str(int(v, 0)))
            except (ValueError, TypeError):
                w["decoded"].setText("not a number" if v else "")
        else:
            w["decoded"].setText("")

    def _regen(self, key):
        """A random value that still looks like the field it replaces."""
        import random
        if key in STRUCTURAL:
            return                      # spec-defined; see STRUCTURAL above
        w = self.widgets[key]
        kind = w["kind"]
        if key in ("TPM_PT_MANUFACTURER", "TPM_PT_VENDOR_STRING_1"):
            # Pick a manufacturer that actually exists rather than four random
            # letters, and keep vendor string 1 matching it the way real parts do.
            code, name = random.choice(REAL_VENDORS)
            self.widgets["TPM_PT_MANUFACTURER"]["edit"].setText(code)
            self.widgets["TPM_PT_VENDOR_STRING_1"]["edit"].setText(code)
            self._decode("TPM_PT_MANUFACTURER")
            self._decode("TPM_PT_VENDOR_STRING_1")
            self.changed.emit()
            return
        if kind == "ascii4":
            cur = w["edit"].text().strip()
            # A field that is zero on the real part stays zero. Filling the
            # unused vendor strings with random bytes makes the identity less
            # believable, not more: no shipping TPM reports junk there.
            try:
                if int(cur or "0", 0) == 0:
                    return
            except ValueError:
                pass
            ascii_now = _to_ascii(cur).replace("\\0", "")
            if ascii_now and all(c.isalnum() for c in ascii_now):
                # Keep the same number of printable characters, so a 3-letter
                # vendor tag stays 3 letters and the trailing NULs stay NULs.
                new = randomize.like(ascii_now)
                w["edit"].setText(_from_ascii(new))
            else:
                w["edit"].setText("0x%08X" % random.getrandbits(32))
        elif kind == "u32":
            w["edit"].setText("0x%X" % random.getrandbits(20))
        elif kind == "dec":
            cur = w["edit"].text().strip()
            try:
                n = int(cur, 0)
            except (ValueError, TypeError):
                n = 0
            if n > 1900:                       # a year
                w["edit"].setText(str(random.randint(2014, 2023)))
            elif n > 31:                       # a day of year
                w["edit"].setText(str(random.randint(1, 365)))
            else:
                w["edit"].setText(str(n))      # level/family: leave structural
        else:
            w["edit"].setText(randomize.like(w["edit"].text() or "Model X"))
        self._decode(key)
        self.changed.emit()

    def _regen_all(self):
        for key in self.widgets:
            self._regen(key)
        self.log.setPlainText(
            "regenerated the vendor identity fields (nothing written yet)\n\n"
            "Left unchanged on purpose: " + ", ".join(
                dict((k, l) for k, l, _kd, _t in FIELDS)[k] for k in FIELDS_ORDER
                if k in STRUCTURAL)
            + ".\nThose are fixed by the TPM specification - a real part cannot "
              "report anything else, so changing them is itself the signal.")

    def _apply_preset(self):
        vals = PRESETS.get(self.preset.currentData(), {})
        for key, v in vals.items():
            if key in self.widgets:
                self.widgets[key]["edit"].setText(str(v))
                self._decode(key)
        self.log.setPlainText(f"loaded preset: {self.preset.currentData()}\n"
                              f"nothing written yet - use Apply TPM Identity at the top")
        self.changed.emit()

    # ----------------------------------------------------------- env file ---
    def load_env(self):
        p = self.paths()
        if not os.path.isfile(p["env"]):
            self.log.setPlainText(f"no env file at {p['env']}")
            return
        vals = {}
        for line in open(p["env"]):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
        # Fall back to the header for anything the .env does not carry.
        hdr = _parse_header(p["header"])
        from_hdr = []
        for key, w in self.widgets.items():
            v = vals.get(key, "")
            if not v:
                hk = HEADER_KEYS.get(key)
                if hk and hk in hdr:
                    v = hdr[hk]
                    from_hdr.append(key)
            w["edit"].setText(v)
            self._decode(key)
        msg = (f"loaded {p['env']}\n"
               f"{len([k for k in vals if k in self.widgets])} of "
               f"{len(self.widgets)} fields came from the .env")
        if from_hdr:
            msg += (f"\n{len(from_hdr)} recovered from {os.path.basename(p['header'])}: "
                    + ", ".join(from_hdr))
        self.log.setPlainText(msg)

    def save_env(self):
        p = self.paths()
        if not os.path.isdir(os.path.dirname(p["env"])):
            QMessageBox.critical(self, "No TPM tree",
                                 f"{p['root']} does not exist.")
            return False
        if os.path.isfile(p["env"]):
            import shutil
            shutil.copyfile(p["env"], p["env"] + ".prev")
        lines = ["# Written by vmstart_2. The previous file is kept as .prev.",
                 "# gen-tpm-vendor-identity-h.sh sources this, so string values",
                 "# must stay quoted or the shell tries to execute them.", ""]
        for key, label, kind, _tip in FIELDS:
            v = self.widgets[key]["edit"].text().strip()
            if not v:
                continue
            lines.append(f'{key}="{v}"' if kind == "str" else f"{key}={v}")
        with open(p["env"], "w") as f:
            f.write("\n".join(lines) + "\n")
        self.log.setPlainText(f"wrote {p['env']}\n\n" + "\n".join(lines))
        return True

    def _regen_header(self):
        if not self.save_env():
            return
        p = self.paths()
        if not os.path.isfile(p["gen"]):
            self.log.appendPlainText(f"\nmissing generator: {p['gen']}")
            return
        r = subprocess.run(["bash", p["gen"], p["env"], p["header"]],
                           capture_output=True, text=True)
        self.log.appendPlainText(
            f"\n--- {os.path.basename(p['gen'])} (rc={r.returncode}) ---\n"
            + (r.stdout + r.stderr).strip())
        if r.returncode == 0:
            self.log.appendPlainText(
                f"\nheader written. It does NOT take effect until libtpms and "
                f"swtpm are rebuilt.")

    def _rebuild(self):
        p = self.paths()
        if QMessageBox.question(
                self, "Rebuild libtpms and swtpm",
                "This writes the .env, regenerates the header and runs\n"
                f"{p['build']} --no-tpm-dump\n\n"
                "It takes several minutes and replaces the installed swtpm.\n"
                "Do not do this while a VM is running. Continue?"
                ) != QMessageBox.StandardButton.Yes:
            return
        self._regen_header()
        if not os.path.isfile(p["build"]):
            self.log.appendPlainText(f"\nmissing build script: {p['build']}")
            return
        # The integrated build script installs into this user's private TPM
        # workspace. It does not configure or restart shared libvirt services.
        argv, env = ["bash", p["build"], "--no-tpm-dump"], dict(os.environ)
        self.log.appendPlainText(f"\n--- running {os.path.basename(p['build'])} in the private workspace, "
                                 f"this takes a few minutes ---")
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        # Merge the streams into one chronological log. Concatenating them
        # instead put every stdout line before every stderr line, so tailing
        # showed the end of autoreconf's chatter and hid the end of the build --
        # a successful rebuild read as though it had stopped at configure.
        r = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, cwd=p["root"], env=env)
        tail = "\n".join((r.stdout or "").strip().splitlines()[-40:])
        self.log.appendPlainText(f"(rc={r.returncode})\n{tail}")
        if r.returncode != 0:
            self.log.appendPlainText(
                "\nRebuild failed. Check the build output above.")
            return
        # Say plainly that it landed, and prove it from the installed files
        # rather than from the exit code alone.
        self.log.appendPlainText("\nREBUILD OK. The identity in section 2 is now "
                                 "compiled into libtpms.")
        self.cfg.data.setdefault("tools", {})["swtpm_binary"] = os.path.join(p["root"], "_install", "bin", "swtpm")
        self.changed.emit()
        binary = self.cfg.data.get("tools", {}).get("swtpm_binary", "")
        if binary and os.path.isfile(binary):
            when = time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(binary)))
            self.log.appendPlainText(f"installed swtpm rebuilt at {when}: {binary}")
        else:
            self.log.appendPlainText(
                f"WARNING: the swtpm the launcher will run is '{binary or '(unset)'}', "
                f"which does not exist. Set it on the Paths & Tools tab or the guest "
                f"will not get this identity.")
        self.check_attestation()

    # ---------------------------------------------------------- inspection ---
    def _dump_physical(self):
        p = self.paths()
        if not os.path.isfile(p["dump"]):
            self.log.setPlainText(f"missing {p['dump']}")
            return
        argv, env, ok = sudo_command(["bash", p["dump"]],
                                    prompt="vmstart_2: read the physical TPM (root)")
        if not ok:
            self.log.setPlainText("reading the TPM needs root and no password prompt "
                                  "is available. Install ksshaskpass/ssh-askpass or "
                                  "enable passwordless sudo.")
            return
        r = subprocess.run(argv, capture_output=True, text=True, env=env)
        if r.returncode != 0:
            self.log.setPlainText("dump failed:\n" + (r.stdout + r.stderr).strip())
            return
        vals = {}
        for line in r.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"')
        n = 0
        for key, w in self.widgets.items():
            if key in vals:
                w["edit"].setText(vals[key])
                self._decode(key)
                n += 1
        self.log.setPlainText(f"read {n} properties from the physical TPM "
                              f"(nothing written yet)\n\n" + r.stdout.strip())
        self.changed.emit()

    def _show_header(self):
        p = self.paths()
        if not os.path.isfile(p["header"]):
            self.log.setPlainText(f"no header at {p['header']}")
            return
        self.log.setPlainText(f"{p['header']}\n\n" + open(p["header"]).read())

    def _show_live(self):
        """What the installed swtpm actually reports, which is the truth."""
        t = self.cfg.data.get("tools", {})
        binary = t.get("swtpm_binary") or "/usr/bin/swtpm"
        if not os.path.isfile(binary):
            self.log.setPlainText(f"no swtpm at {binary}")
            return
        r = subprocess.run([binary, "socket", "--tpm2", "--print-capabilities"],
                           capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip()
        ver = subprocess.run([binary, "--version"], capture_output=True, text=True)
        self.log.setPlainText(
            f"{binary}\n{(ver.stdout + ver.stderr).strip()}\n\n{out}\n\n"
            f"This is the installed build. If it does not match the fields "
            f"above, the rebuild has not been run since they were changed.")

    # ------------------------------------------------------ keys and state ---
    def _state_path(self):
        t = self.cfg.data.setdefault("tools", {})
        v = t.get("swtpm_state") or ""
        if not v:
            uuid = self.cfg.simple.get("uuid", "")
            v = f"/var/lib/libvirt/swtpm/{uuid}/tpm2" if uuid else ""
            t["swtpm_state"] = v
        return v

    def _set_state_dir(self, text):
        self.cfg.data.setdefault("tools", {})["swtpm_state"] = text.strip()
        self.changed.emit()

    def _browse_state(self):
        p = QFileDialog.getExistingDirectory(self, "swtpm state directory",
                                             self.state_dir.text() or "/var/lib")
        if p:
            self.state_dir.setText(p)
            self._set_state_dir(p)

    def _sudo(self, args, timeout=120):
        try:
            r = subprocess.run(["sudo", "-n"] + args, capture_output=True,
                               text=True, timeout=timeout)
            return r.returncode, (r.stdout + r.stderr).strip()
        except Exception as e:
            return 1, str(e)

    def _show_state(self):
        """What is actually inside the NV store.

        Reads tpm2-00.permall directly rather than starting a throwaway swtpm:
        the state blob carries the libtpms profile as JSON, the certificates as
        DER, and the issuer strings in the clear. That is both more reliable
        than bringing a TPM up over a TCTI and impossible to get half-right.
        """
        d = self.state_dir.text().strip()
        if not d:
            self.log.setPlainText("no state directory set")
            return
        rc, listing = self._sudo(["ls", "-la", d])
        lines = [d, listing, ""]

        blob = os.path.join(d, "tpm2-00.permall")
        rc, b64 = self._sudo(["base64", "-w0", blob])
        if rc != 0:
            self.log.setPlainText("\n".join(lines + [f"cannot read {blob}", b64]))
            return
        import base64
        try:
            data = base64.b64decode(b64)
        except Exception as e:
            self.log.setPlainText("\n".join(lines + [f"unreadable blob: {e}"]))
            return

        lines.append(f"{os.path.basename(blob)}: {len(data)} bytes")

        # --- libtpms profile: which algorithms and commands are enabled ------
        m = re.search(rb'\{"Name":.*?\}', data, re.S)
        if m:
            try:
                prof = json.loads(m.group(0).decode("utf-8", "replace"))
            except Exception:
                prof = {}
            if prof:
                lines += ["", f"profile: {prof.get('Name','?')} "
                              f"(state format level {prof.get('StateFormatLevel','?')})"]
                algs = prof.get("Algorithms", "")
                lines.append("algorithms: " + algs)
                hashes = [h for h in ("sha1", "sha256", "sha384", "sha512", "sm3-256")
                          if h in algs.split(",")]
                lines.append("hash banks available: " + (", ".join(hashes) or "none"))
                if "sha256" not in hashes:
                    lines.append("  WARNING: no sha256. Windows measures into it; "
                                 "a TPM 2.0 without it is not credible.")
                lines.append("commands: " + prof.get("Commands", "")[:100] + " ...")
        else:
            lines.append("no libtpms profile found in the state")

        # --- certificates ------------------------------------------------------
        certs = data.count(b"\x30\x82")
        issuers = sorted({s.decode("ascii", "replace") for s in
                          re.findall(rb"[ -~]{6,40}", data)
                          if b"localca" in s.lower() or b"CN=" in s})
        lines += ["", f"DER SEQUENCE markers: {certs} "
                      f"({'certificates are present' if certs else 'no certificate data'})"]
        if issuers:
            lines.append("certificate issuer strings: " + ", ".join(issuers))
            if any("localca" in i.lower() for i in issuers):
                # This is the honest part: the cert exists, which keeps Windows
                # attestation happy, but it is not signed by the vendor CA a
                # real part of this make would carry.
                lines.append("  Note: issued by swtpm's local CA, not by the "
                             "vendor CA a real chip of this make would carry. "
                             "It satisfies Windows attestation readiness; it "
                             "does not survive a check against vendor roots.")
        else:
            lines.append("no issuer strings found; the EK certificate is probably "
                         "absent, and Windows will report "
                         "INFORMATION_EK_CERTIFICATE.")

        models = sorted({s.decode("ascii", "replace").strip() for s in
                         re.findall(rb"[ -~]{4,20}", data)
                         if b"fTPM" in s or b"SLB" in s or b"ST33" in s})
        if models:
            lines.append("model strings in state: " + ", ".join(models))
        self.log.setPlainText("\n".join(lines))


    def _backup_state(self):
        d = self.state_dir.text().strip()
        if not d or not os.path.isdir(d):
            self.log.setPlainText(f"no state directory at {d}")
            return
        dest = d.rstrip("/") + ".bak"
        rc, out = self._sudo(["cp", "-a", d, dest])
        self.log.setPlainText(f"cp -a {d} {dest}\nrc={rc}\n{out}\n"
                              f"{'backed up' if rc == 0 else 'FAILED'}")

    def _restore_state(self):
        d = self.state_dir.text().strip()
        src = d.rstrip("/") + ".bak"
        if not os.path.isdir(src):
            self.log.setPlainText(f"no backup at {src}")
            return
        if QMessageBox.question(
                self, "Restore TPM state",
                f"Replace\n  {d}\nwith\n  {src}\n\n"
                "The guest will see the TPM it had when that backup was taken, "
                "including its keys. Continue?"
                ) != QMessageBox.StandardButton.Yes:
            return
        rc, out = self._sudo(["sh", "-c",
                              f"rm -rf {d!r} && cp -a {src!r} {d!r}"])
        self.log.setPlainText(f"rc={rc}\n{out}\n"
                              f"{'restored' if rc == 0 else 'FAILED'}")

    def _new_ek(self):
        """Re-provision the EMULATED TPM. Never touches the physical chip."""
        d = self.state_dir.text().strip()
        binary = self.cfg.data.get("tools", {}).get("swtpm_binary", "")
        setup = os.path.join(os.path.dirname(binary), "swtpm_setup") if binary else ""
        if not setup or not os.path.isfile(setup):
            self.log.setPlainText(f"swtpm_setup not found next to {binary}")
            return
        if QMessageBox.question(
                self, "New endorsement key",
                f"Generate a new EK and certificates in\n  {d}\n\n"
                "This is the EMULATED TPM only; the motherboard's chip is not "
                "touched.\n\nWindows will see a different TPM. BitLocker keys "
                "sealed to the old one will not unseal. Continue?"
                ) != QMessageBox.StandardButton.Yes:
            return
        args = [setup, "--tpm2", "--tpmstate", f"dir={d}",
                "--tpm", f"{binary} socket",
                "--overwrite", "--pcr-banks", self.pcr_banks.text().strip() or "sha1,sha256"]
        algo = self.ek_algo.currentData()
        if algo:
            args += ["--ecc"] if algo.startswith("ecc") else ["--rsa-keysize",
                                                             algo.replace("rsa", "")]
        if self.chk_ekcert.isChecked():
            args.append("--create-ek-cert")
        if self.chk_platcert.isChecked():
            args.append("--create-platform-cert")
        if self.chk_lock.isChecked():
            args.append("--lock-nvram")
        self.log.setPlainText("running:\n  " + " ".join(args) + "\n")
        rc, out = self._sudo(args, timeout=300)
        self.log.appendPlainText(f"\nrc={rc}\n{out}")
        if rc == 0:
            self._show_state()

    # ------------------------------------------------- the physical chip ---
    def _phys_script(self, action):
        p = self.paths()
        script = os.path.join(p["root"], "scripts", "tpm-reconstruct.sh")
        if not os.path.isfile(script):
            self.log.setPlainText(f"missing {script}")
            return None
        return script

    def _adopt_physical(self):
        """Read the real chip's identity into the fields above."""
        self._dump_physical()

    def _mirror_nv(self):
        script = self._phys_script("mirror")
        if not script:
            return
        self.log.setPlainText(
            "Mirroring the NV layout runs the existing reconstruct script, "
            "which is menu driven.\n\n"
            f"  sudo {script}\n\n"
            "Choose option 6 (Mirror host NV layout). It reads the physical "
            "chip and writes only to the emulated state directory.\n\n"
            "This is deliberately not automated from here: the same script's "
            "option 8 re-provisions the PHYSICAL TPM's endorsement key, which a "
            "board permits a limited number of times and cannot be undone.")

    def _verify_physical(self):
        rc, out = self._sudo(["sh", "-c",
                              "TPM2TOOLS_DEVICE=/dev/tpmrm0 tpm2 getcap properties-fixed"],
                             timeout=30)
        if rc != 0:
            self.log.setPlainText("could not read the physical TPM:\n" + out)
            return
        want = {k: self.widgets[k]["edit"].text().strip() for k in self.widgets}
        lines = ["physical chip properties-fixed:", out, "",
                 "comparison with the fields above:"]
        for key, label, kind, _t in FIELDS:
            v = want.get(key, "")
            if not v:
                continue
            m = re.search(rf"{key.replace('TPM_PT_', 'TPM2_PT_')}.*?raw:\s*(\S+)",
                          out, re.S | re.I)
            real = m.group(1) if m else None
            if real is None:
                continue
            same = False
            try:
                same = int(real, 0) == int(v, 0)
            except ValueError:
                same = str(real) == v
            lines.append(f"  {label:<24} emulated {v:<14} physical {real:<14} "
                         f"{'match' if same else 'DIFFERENT'}")
        self.log.setPlainText("\n".join(lines))

    # ------------------------------------------------------- will it pass? ---
    def check_attestation(self):
        """Answer the only question that matters, with the reason for each part.

        Windows attestation is pass/fail on a handful of concrete conditions.
        Reading them off a wall of properties is guesswork, so they are checked
        here and each one says what to click when it fails.
        """
        checks = []   # (state, what, why / how to fix)

        # --- is there a TPM in the VM at all -------------------------------
        tpmdev = self.cfg.simple.get("tpmdev", "")
        dev = next((d for d in self.cfg.devices
                    if str(d.get("driver", "")).startswith("tpm-")
                    and not d.get("_disabled")), None)
        if not tpmdev or not dev:
            checks.append(("FAIL", "TPM present in the VM",
                           "no -tpmdev or tpm device; Windows 11 will refuse to "
                           "install and attestation cannot run"))
        else:
            checks.append(("PASS", "TPM present in the VM",
                           f"{dev.get('driver')} backed by {tpmdev.split(',')[0]}"))

        # Every check below this point is about the emulated chip. Reporting
        # swtpm problems for a guest that never touches swtpm would be noise.
        if tpmdev.startswith("passthrough"):
            checks.extend(self._passthrough_checks(tpmdev))
            return self._render_checks(checks)

        # --- swtpm binary ----------------------------------------------------
        t = self.cfg.data.get("tools", {})
        binary = t.get("swtpm_binary", "")
        if not binary or not os.path.isfile(binary):
            checks.append(("FAIL", "swtpm binary",
                           f"not found at {binary or '(unset)'}; the start hook "
                           f"aborts before the VM launches"))
        else:
            from tpm_setup import packaged_binary
            custom = packaged_binary(binary)
            checks.append(("PASS" if custom else "WARN", "swtpm binary",
                           binary + ("" if custom else
                                     "  (external build: its compiled identity has not been verified)")))

        # --- state directory and its contents ---------------------------------
        d = self.state_dir.text().strip()
        blob = os.path.join(d, "tpm2-00.permall") if d else ""
        data = b""
        if blob:
            try:
                with open(blob,'rb') as stream: data = stream.read(16*1024*1024)
            except PermissionError:
                rc, b64 = self._sudo(["base64", "-w0", blob])
                if rc == 0:
                    import base64
                    try: data = base64.b64decode(b64)
                    except ValueError: pass
            except OSError: pass
        if not data:
            checks.append(("FAIL", "NV state readable",
                           f"cannot read {blob or '(no state dir set)'}"))
        else:
            checks.append(("PASS", "NV state readable", f"{len(data)} bytes"))

            # Ask a disposable copy of the TPM. Searching raw NV bytes for
            # JSON algorithm names falsely rejects valid modern state formats.
            from tpm_setup import inspect_state
            try:
                banks,has_cert=inspect_state(binary,data,os.stat(binary).st_mtime_ns)
                checks.append(("PASS" if has_cert else "FAIL", "EK certificate in NV",
                               "Present" if has_cert else "Missing. Use New EK + certificates if this is a new guest, or restore its original TPM state."))
                if has_cert and b"localca" in data.lower():
                    checks.append(("WARN", "EK certificate issuer",
                                   "Signed by the private local CA, not a hardware vendor CA. Services requiring vendor attestation may reject it."))
                checks.append(("PASS" if "sha256" in banks else "FAIL", "sha256 PCR bank",
                               ", ".join(banks) if "sha256" in banks else "Not allocated. Restore the guest's TPM state or reconfigure its PCR banks."))
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
                checks.append(("FAIL", "TPM capabilities", "Could not verify PCR banks and certificates: "+str(error)))

        # --- identity coherence ------------------------------------------------
        man = self.widgets["TPM_PT_MANUFACTURER"]["edit"].text().strip()
        v1 = self.widgets["TPM_PT_VENDOR_STRING_1"]["edit"].text().strip()
        known = {c for c, _n in REAL_VENDORS}
        if not man:
            checks.append(("FAIL", "manufacturer set", "empty"))
        elif man in known:
            checks.append(("PASS", "manufacturer is a real vendor", _to_ascii(man)))
        else:
            checks.append(("WARN", "manufacturer is a real vendor",
                           f"{_to_ascii(man)} is not in the known vendor list; "
                           f"software that checks against one will not match it"))
        if man and v1 and man != v1:
            checks.append(("WARN", "vendor string matches manufacturer",
                           f"{_to_ascii(man)} vs {_to_ascii(v1)}; real parts "
                           f"normally repeat the manufacturer here"))

        # --- has the identity actually been built ------------------------------
        p = self.paths()
        hdr = _parse_header(p["header"])
        want = self.widgets["TPM_PT_MANUFACTURER"]["edit"].text().strip()
        built = hdr.get("TPM_IDENT_MANUFACTURER_U32", "")
        try:
            same = int(built or "0", 0) == int(want or "0", 0)
        except ValueError:
            same = False
        from tpm_setup import packaged_binary
        if packaged_binary(binary) and not os.path.isfile(p['header']):
            checks.append(('PASS', 'Published TPM build',
                           'Using the installed custom TPM component. Changing its compiled identity requires a matching custom build.'))
        elif same:
            checks.append(("PASS", "header matches the fields above",
                           "no rebuild needed for the manufacturer"))
        else:
            checks.append(("WARN", "header matches the fields above",
                           f"header has {_to_ascii(built)}, fields say "
                           f"{_to_ascii(want)}. Use Apply TPM Identity at the top; libtpms "
                           f"must be rebuilt, before a guest sees the change"))

        return self._render_checks(checks)

    def _passthrough_checks(self, tpmdev):
        """What matters when the guest is handed the real chip."""
        checks = []
        m = re.search(r"\bpath=([^,]+)", tpmdev)
        path = m.group(1) if m else ""
        if not path or not os.path.exists(path):
            checks.append(("FAIL", "host TPM device",
                           f"{path or '(unset)'} does not exist; QEMU will refuse "
                           f"to start"))
        else:
            checks.append(("PASS", "host TPM device", path))

        m = re.search(r"cancel-path=([^,]+)", tpmdev)
        cancel = m.group(1) if m else ""
        if not cancel:
            checks.append(("FAIL", "cancel path",
                           "not set. A CRB firmware TPM exposes no sysfs cancel "
                           "node, so QEMU aborts with 'Could not guess TPM cancel "
                           "path'. Use /dev/null"))
        elif cancel == "/dev/null":
            checks.append(("PASS", "cancel path",
                           "/dev/null; command cancellation is a no-op, which is "
                           "normal for a CRB fTPM"))
        else:
            checks.append(("PASS" if os.path.exists(cancel) else "FAIL",
                           "cancel path", cancel))

        dev = next((d for d in self.cfg.devices
                    if str(d.get("driver", "")).startswith("tpm-")
                    and not d.get("_disabled")), None)
        if dev and dev.get("driver") == "tpm-crb":
            checks.append(("FAIL", "device model",
                           "tpm-crb has a fixed 3968-byte command buffer and the "
                           "host chip reports 4096. QEMU aborts at startup with "
                           "'Requested buffer size of 3968 is smaller than host "
                           "TPM's fixed buffer size of 4096' and exits 1. "
                           "Passthrough needs tpm-tis"))
        elif dev:
            checks.append(("PASS", "device model",
                           f"{dev.get('driver')} passes the host buffer through"))

        checks.append(("WARN", "host loses its TPM",
                       "passthrough is exclusive: nothing on the host can use the "
                       "chip while the guest holds it"))
        checks.append(("WARN", "PCRs are the host's",
                       "measurements reflect this machine's boot, not the guest's, "
                       "so guest-side attestation reads values it did not produce"))
        checks.append(("WARN", "emulated identity unused",
                       "the emulated identity controls do not apply; the guest reports the real "
                       "chip's manufacturer and firmware version"))
        checks.append(("WARN", "NV writes are permanent",
                       "the guest can change the real chip's persistent state, "
                       "including clearing it"))
        return checks

    def _render_checks(self, checks):
        self.last_checks = checks
        fails = [c for c in checks if c[0] == "FAIL"]
        warns = [c for c in checks if c[0] == "WARN"]
        if fails:
            self.verdict.setText(f"WILL FAIL  -  {len(fails)} blocking problem"
                                 f"{'s' if len(fails) != 1 else ''}")
            self.verdict.setStyleSheet("color: #e06c75;")
        elif warns:
            self.verdict.setText(f"SHOULD PASS  -  {len(warns)} thing"
                                 f"{'s' if len(warns) != 1 else ''} to be aware of")
            self.verdict.setStyleSheet("color: #e5c07b;")
        else:
            self.verdict.setText("SHOULD PASS")
            self.verdict.setStyleSheet("color: #98c379;")

        issues = fails + warns
        self.check_summary.setText("\n".join(
            f"{what}: {why}" for _status, what, why in issues))
        self.check_summary.setVisible(bool(issues))
        width = max(len(c[1]) for c in checks)
        self.checks.setPlainText("\n".join(
            f"[{st:4}] {what:<{width}}  {why}" for st, what, why in checks))
        self.btn_repair.setVisible(bool(fails) and not self.cfg.simple.get('tpmdev','').startswith('passthrough'))
        self.checks_changed.emit()
        return checks
