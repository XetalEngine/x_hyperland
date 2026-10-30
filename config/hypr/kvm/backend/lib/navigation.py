"""Presentation and navigation for the configuration pages."""

from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QEvent, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLineEdit, QListWidget,
                             QListWidgetItem, QLabel, QAbstractItemView)


# Keep the original tab names as keys: wizard links and configuration reloads
# can still address the same pages regardless of their presentation.
PAGES = [
    ("Single GPU", "START", "Single GPU", "Launch with GPU passthrough and the start / revert scripts.",
     "overview launch preflight test history log gaming"),
    ("Virtual GPU", "START", "Virtual GPU", "Run the same guest in a virtual display while keeping Linux available.",
     "launch desktop spice vnc bochs qxl virtio graphics testing"),
    ("Dual GPU", "START", "Dual GPU", "Give the guest an unused GPU while Linux keeps its desktop GPU.",
     "launch spare second integrated igpu passthrough looking glass hardware acceleration"),
    ("Wizard", "START", "Setup wizard", "Guided setup with the same settings available in the editor.",
     "start over new setup iommu"),
    ("CPU Pinning", "HARDWARE", "CPU pinning", "Choose guest cores, then place emulator and I/O threads on the host.",
     "processor cores threads smt cache ccd scheduling affinity"),
    ("CPU Features", "HARDWARE", "CPU features", "Control the CPU capabilities reported to the guest, including vendor-specific flags.",
     "processor amd intel svm vmx flags"),
    ("Memory", "HARDWARE", "Memory", "Set guest RAM, hugepage backing, and memory backend options.",
     "ram allocation hugepages"),
    ("Disks", "HARDWARE", "Disks & storage", "Attach disks and installation media, then adjust controllers, boot order, and disk options.",
     "storage iso cd rom nvme sata cache serial"),
    ("PCI / USB", "HARDWARE", "PCI & USB devices", "Choose host devices to pass through and review their guest assignments.",
     "gpu graphics audio controller passthrough rom iommu"),
    ("Machine", "CONFIGURATION", "Machine & network", "Configure the machine type, networking, and additional QEMU options.",
     "bridge tap mac nic flags globals switches coverage"),
    ("SMBIOS", "CONFIGURATION", "SMBIOS identity", "Edit the guest's system and BIOS identity, preview patches, and build the output blob.",
     "bios firmware uuid serial identity"),
    ("Boot Arguments", "CONFIGURATION", "Boot Arguments", "Choose macOS boot arguments, their values and startup behavior.",
     "mac opencore nvidia startup settle verbose amfi debug keepsyms"),
    ("TPM", "CONFIGURATION", "TPM", "Select the TPM backend and manage its identity, keys, state, and checks.",
     "security attestation swtpm nv identity rebuild"),
    ("Paths && Tools", "ADVANCED", "Paths & tools", "Locate the emulator, firmware, supporting files, and build tools.",
     "qemu ovmf nvram acpi modules binaries environment"),
    ("Launch Procedure", "ADVANCED", "Launch procedure", "Review or edit the scripts that prepare the host and restore it after QEMU exits.",
     "hooks start revert scripts"),
    ("Command Preview", "ADVANCED", "Command preview", "Inspect the generated QEMU command and export a launch script.",
     "export standalone arguments command line"),
]

PAGE_ICONS = {
    "Single GPU": "gpu", "Virtual GPU": "virtual-display", "Dual GPU": "dual-display",
    "Wizard": "wand", "CPU Pinning": "cpu-pin", "CPU Features": "cpu-settings",
    "Memory": "memory", "Disks": "storage", "PCI / USB": "usb",
    "Machine": "network", "SMBIOS": "identity", "Boot Arguments": "terminal", "TPM": "shield",
    "Paths && Tools": "tools", "Launch Procedure": "checklist", "Command Preview": "terminal",
}
ICON_DIR = Path(__file__).resolve().parents[1] / "assets" / "sidebar"


class PageNavigation(QWidget):
    activated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navigationPanel")
        self.setFixedWidth(216)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a page…")
        self.search.setAccessibleName("Find a configuration page")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setObjectName("pageNavigation")
        self.list.setAccessibleName("Configuration pages")
        self.list.setIconSize(QSize(20, 20))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        layout.addWidget(self.list, 1)
        self.empty = QLabel("No matching pages")
        self.empty.setObjectName("muted")
        self.empty.hide()
        layout.addWidget(self.empty)
        self.items = {}
        self.groups = {}
        self.hidden_pages = {"Wizard"}
        self.blocked_pages = {"Boot Arguments"}
        self.profile = "windows"
        for key, group, title, description, keywords in PAGES:
            if group not in self.groups:
                heading = QListWidgetItem(group, self.list)
                heading.setFlags(Qt.ItemFlag.NoItemFlags)
                heading.setSizeHint(QSize(0, 30))
                font = heading.font()
                font.setBold(True)
                font.setPointSize(9)
                heading.setFont(font)
                self.groups[group] = heading
            item = QListWidgetItem(title, self.list)
            item.setIcon(QIcon(str(ICON_DIR / f"{PAGE_ICONS[key]}.svg")))
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setToolTip(description)
            item.setSizeHint(QSize(0, 36))
            self.items[key] = item
        self.list.itemClicked.connect(self._activate)
        self.list.installEventFilter(self)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._open_first_match)
        self._filter("")

    def _activate(self, item):
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key and key not in self.blocked_pages:
            self.activated.emit(key)

    def eventFilter(self, obj, event):
        if (obj is self.list and event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            self._activate(self.list.currentItem())
            return True
        return super().eventFilter(obj, event)

    def select(self, key):
        if key == "Wizard":
            self.list.setCurrentRow(-1)
            return
        if key in self.blocked_pages:
            return
        item = self.items.get(key)
        if item is not None:
            if key in self.hidden_pages:
                self.hidden_pages.remove(key)
                self._filter(self.search.text())
            # A programmatic jump (for example, after launch) must remain
            # visible even if the user previously filtered the page list.
            if item.isHidden():
                self.search.clear()
            self.list.setCurrentItem(item)
            self.list.scrollToItem(item)

    def _filter(self, text):
        words = text.casefold().split()
        visible_groups = set()
        for key, group, title, description, keywords in PAGES:
            if self.profile == "macos" and key == "SMBIOS":
                title, description, keywords = "Mac & OpenCore", "Mac boot settings, identity and security", "opencore nvidia boot sip amfi ram serial uuid firmware"
            haystack = f"{key} {group} {title} {description} {keywords}".casefold()
            visible = key not in self.hidden_pages | self.blocked_pages and all(word in haystack for word in words)
            self.items[key].setHidden(not visible)
            if visible:
                visible_groups.add(group)
        for group, item in self.groups.items():
            item.setHidden(group not in visible_groups)
        self.empty.setVisible(not visible_groups)

    def set_profile(self, profile):
        self.profile = profile
        self.blocked_pages = {"TPM"} if profile == "macos" else {"Boot Arguments"}
        item = self.items["SMBIOS"]
        item.setText("Mac & OpenCore" if profile == "macos" else "SMBIOS identity")
        item.setToolTip("Edit and validate Mac boot settings, identity and security." if profile == "macos" else
                        next(p[3] for p in PAGES if p[0] == "SMBIOS"))
        self._filter(self.search.text())

    def _open_first_match(self):
        for item in self.items.values():
            if not item.isHidden():
                self._activate(item)
                return
