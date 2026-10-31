"""Page-level diagnostics and a visible, slow pulse for invalid settings."""
from collections import defaultdict
from pathlib import Path
from PyQt6.QtCore import Qt,QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QStyledItemDelegate
import packages
import portable

ISSUE_ROLE = int(Qt.ItemDataRole.UserRole) + 10


class IssueDelegate(QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.phase = False
        self.timer = QTimer(self)
        self.timer.setInterval(700)
        self.timer.timeout.connect(self.pulse)

    def pulse(self):
        self.phase = not self.phase
        self.parent().viewport().update()

    def paint(self, painter, option, index):
        super().paint(painter,option,index)
        if index.data(ISSUE_ROLE):
            painter.save()
            color = QColor('#ef5350');color.setAlpha(72 if self.phase else 24)
            painter.fillRect(option.rect.adjusted(0,1,0,-1),color)
            painter.setPen(QColor('#ef5350'))
            painter.drawText(option.rect.adjusted(0,0,-6,0),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,'!')
            painter.restore()


def collect(window):
    cfg=window.cfg;issues=defaultdict(list)
    for severity,message in cfg.validate():
        if severity not in ('error','warn'): continue
        text=message.lower()
        page = ('CPU Pinning' if any(k in text for k in ('vcpus','topology','pinning')) else
                'CPU Features' if any(k in text for k in ('cpu','hypervisor','kvmclock')) else
                'TPM' if 'tpm' in text else
                'Paths && Tools' if any(k in text for k in ('acpi','ovmf','pflash','firmware','components/')) else
                'Disks' if any(k in text for k in ('disk','blockdev','serial','nvme')) else
                'PCI / USB' if any(k in text for k in ('pci','usb','device','romfile')) else
                'Memory' if any(k in text for k in ('memory','hugepage','ram')) else
                'SMBIOS' if 'smbios' in text else 'Command Preview')
        issues[page].append(message)
    for page,tab in (('Disks',window.tab_disks),('PCI / USB',window.tab_hw)):
        issues[page].extend(getattr(tab,'problems',[]))
    if cfg.profile != 'macos':
        issues['TPM'].extend(f'{name}: {why}' for state,name,why in getattr(window.tab_tpm,'last_checks',[])
                             if state=='FAIL')
    editor=getattr(window,'tab_opencore',None)
    if editor: issues['SMBIOS'].extend(getattr(editor,'_errors',{}).values())
    binary=cfg.data.get('_meta',{}).get('binary','')
    if not binary or not Path(binary).is_file():issues['Paths && Tools'].append('QEMU is missing. Install / download missing components.')
    tools=cfg.data.get('tools',{})
    network = cfg.data.get('network', {})
    if network.get('mode') == 'tap':
        import hostinfo
        bridge = network.get('bridge', '')
        if not bridge or bridge not in hostinfo.net_bridges():
            issues['Machine'].append(f'Bridge {bridge or "(not selected)"} is missing. Choose Create Bridge or NAT networking.')
    if not packages.installed('baseline'):
        issues['Paths && Tools'].append('VM support files are missing. Install / download missing components.')
    if tools.get('kvm_build_enabled') and Path(tools.get('kvm_build',''))==portable.ROOT/'module-tool.sh':
        entry=packages.installed('kvm-amd')
        reason=packages.compatibility('kvm-amd',entry) if entry else 'Custom KVM module is missing'
        if reason:issues['Paths && Tools'].append(reason+'. Download a matching build or choose Use system KVM.')
    for key in ('template_blob','output_blob'):
        value=cfg.data.get('smbios',{}).get(key)
        if value and not Path(value).is_file():issues['SMBIOS'].append('Missing '+value)
    return {page:list(dict.fromkeys(messages)) for page,messages in issues.items() if messages}


def install(window):
    nav=window.navigation
    window.issue_delegate=IssueDelegate(nav.list)
    nav.list.setItemDelegate(window.issue_delegate)
    window.issue_tooltips={key:item.toolTip() for key,item in nav.items.items()}
    timer=QTimer(window);timer.setInterval(2500)
    timer.timeout.connect(lambda:refresh(window))
    timer.start();window.issue_timer=timer
    refresh(window)


def refresh(window):
    if getattr(window,'_checking_health',False):return
    window._checking_health=True
    try:
        window.tab_disks._check();window.tab_hw._check()
        tab=window.tab_tpm
        if hasattr(tab,'state_dir'):
            blob=Path(tab.state_dir.text())/'tpm2-00.permall'
            try:stamp=(blob.stat().st_mtime_ns,blob.stat().st_size)
            except OSError:stamp=None
            tools=window.cfg.data.get('tools',{})
            signature=(id(tab),str(blob),stamp,tools.get('swtpm_binary'),
                       window.cfg.simple.get('tpmdev'),
                       tuple(v['edit'].text() for v in tab.widgets.values()))
            if signature != getattr(window,'_tpm_health_signature',None):
                window._tpm_health_signature=signature
                tab.check_attestation()
        issues=collect(window)
    finally:window._checking_health=False
    window.page_issues=issues
    tools=window.cfg.data.get('tools',{})
    entry=packages.installed('kvm-amd')
    mismatch=not entry or packages.compatibility('kvm-amd',entry)
    window.use_system_kvm.setVisible(bool(tools.get('kvm_build_enabled') and mismatch))
    nav=window.navigation
    for key,item in nav.items.items():
        messages=issues.get(key,[])
        item.setData(ISSUE_ROLE,bool(messages))
        item.setToolTip('\n'.join(messages) if messages else window.issue_tooltips.get(key,''))
    delegate=window.issue_delegate
    if issues and not delegate.timer.isActive(): delegate.timer.start()
    elif not issues:delegate.timer.stop()
    nav.list.viewport().update()
    key=window.tabs.tabText(window.tabs.currentIndex())
    messages=[] if key=='TPM' else issues.get(key,[])  # TPM has its own status card.
    window.issue_banner.setText('\n'.join(messages[:3])+('\nMore details are shown on this page.' if len(messages)>3 else ''))
    window.issue_banner.setVisible(bool(messages))
