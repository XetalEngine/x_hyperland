"""Exercise setup/rollback without changing the machine's SSH or firewall."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import local_ssh as ssh


class FakeSystem:
    def __init__(self, fail='', active=False, enabled=False):
        self.fail = fail; self.running = active; self.boot = enabled; self.events = []
    def active(self, name): return self.running
    def enabled(self, name): return self.boot
    def which(self, name): return None
    def port_available(self): self.events.append(['port-check'])
    def ensure_server(self): self.events.append(['install-openssh']); return '/usr/bin/sshd'
    def banner(self):
        self.events.append(['banner'])
        if self.fail == 'banner': raise RuntimeError('No SSH greeting')
    def run(self, command, **kwargs):
        self.events.append(command)
        if self.fail and self.fail in command:
            self.fail = ''; raise RuntimeError('Simulated failure')
        if command[:2] in (['systemctl','start'], ['systemctl','restart']): self.running = True
        if command[:2] == ['systemctl','stop']: self.running = False
        if command[:2] == ['systemctl','enable']: self.boot = True
        if command[:2] == ['systemctl','disable']: self.boot = False
        return subprocess.CompletedProcess(command, 0, '', '')


class SetupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); self.root = Path(tmp.name)
        self.config = self.root/ssh.CONFIG.relative_to('/')
        self.unit = self.root/ssh.UNIT.relative_to('/')

    def test_enable_is_isolated_authenticated_and_checks_the_listener(self):
        system = FakeSystem()
        result = ssh.enable('alice', system, self.root)
        text = self.config.read_text()
        self.assertIn('Port 2222\n', text)
        self.assertIn('PermitRootLogin no\n', text)
        self.assertIn('DisableForwarding yes\n', text)
        self.assertIn('alice@192.168.0.0/16', text)
        self.assertNotIn('alice@*', text)
        self.assertIn('IPAddressDeny=any', self.unit.read_text())
        self.assertEqual(result['port'], 2222)
        self.assertEqual(system.events[-1], ['banner'])
        self.assertTrue(system.boot and system.running)
        self.assertFalse((self.root/'etc/ssh/sshd_config').exists())
        ssh.enable('bob', system, self.root)
        self.assertIn('# Users: alice bob\n', self.config.read_text())

    def test_failed_validation_firewall_start_and_banner_restore_previous_state(self):
        for stage in ('-t', 'add-rule', 'start', 'banner'):
            with self.subTest(stage=stage):
                system = FakeSystem(fail=stage)
                with patch.object(ssh, 'firewall_commands', return_value=[(['add-rule'], ['remove-rule'])]):
                    with self.assertRaisesRegex(RuntimeError, 'Previous SSH configuration restored'):
                        ssh.enable('alice', system, self.root)
                self.assertFalse(self.config.exists() or self.unit.exists())
                self.assertFalse(system.boot or system.running)
                if stage in ('start','banner'): self.assertIn(['remove-rule'], system.events)

    def test_existing_managed_service_is_restored_on_failed_reconfiguration(self):
        system = FakeSystem(); ssh.enable('alice', system, self.root)
        original = self.config.read_bytes(); system.fail = '-t'
        with self.assertRaises(RuntimeError): ssh.enable('bob', system, self.root)
        self.assertEqual(self.config.read_bytes(), original)
        self.assertTrue(system.boot and system.running)

    def test_duplicate_ufw_rule_is_not_removed_during_recovery(self):
        system = FakeSystem(fail='start'); original = system.run
        def run(command, **kwargs):
            if command == ['ufw','allow-rule']:
                system.events.append(command)
                return subprocess.CompletedProcess(command,0,'Skipping adding existing rule\n','')
            return original(command, **kwargs)
        system.run = run
        with patch.object(ssh,'firewall_commands',return_value=[(['ufw','allow-rule'],['ufw','remove-rule'])]):
            with self.assertRaises(RuntimeError):ssh.enable('alice',system,self.root)
        self.assertNotIn(['ufw','remove-rule'],system.events)

    def test_foreign_files_root_accounts_and_busy_ports_are_not_modified(self):
        self.config.parent.mkdir(parents=True); self.config.write_text('administrator config\n')
        system = FakeSystem()
        with self.assertRaisesRegex(RuntimeError, 'not managed'): ssh.enable('alice', system, self.root)
        self.assertEqual(system.events, [])
        self.assertEqual(self.config.read_text(), 'administrator config\n')
        self.config.unlink()
        for user in ('root', 'alice\nPermitRootLogin yes', '*', 'alice@*'):
            with self.assertRaises(ValueError): ssh.enable(user, system, self.root)
        with patch.object(system, 'port_available', side_effect=RuntimeError('port busy')):
            with self.assertRaisesRegex(RuntimeError, 'port busy'): ssh.enable('alice', system, self.root)
        self.assertEqual(system.events, [])


class FirewallTests(unittest.TestCase):
    def test_firewalld_adds_private_sources_in_active_zones_without_reload(self):
        system = FakeSystem(); system.active = lambda _: True
        system.which = lambda name: '/bin/'+name if name == 'firewall-cmd' else None
        def run(command, **kwargs):
            output = 'home\n  interfaces: br0\n' if '--get-active-zones' in command else ''
            code = int(any('--query-rich-rule' in item for item in command))
            return subprocess.CompletedProcess(command, code, output, '')
        system.run = run
        changes = ssh.firewall_commands(system)
        self.assertEqual(len(changes), 6)
        for add, remove in changes:
            self.assertIn('--zone=home', add)
            self.assertIn('source address=', add[-1])
            self.assertIn('port="2222"', add[-1])
            self.assertNotIn('--reload', add)
            self.assertIn('--remove-rich-rule=', remove[-1])

    def test_ufw_keeps_existing_rule_and_never_disables_firewall(self):
        system = FakeSystem(); system.which = lambda name: '/bin/ufw' if name == 'ufw' else None
        def run(command, **kwargs):
            text = 'Status: active\n' if command == ['ufw','status'] else 'ufw allow from 10.0.0.0/8 to any port 2222 proto tcp\n'
            return subprocess.CompletedProcess(command, 0, text, '')
        system.run = run
        changes = ssh.firewall_commands(system)
        self.assertEqual(len(changes), 2)
        self.assertFalse(any('disable' in command for pair in changes for command in pair))
        self.assertTrue(all('10.0.0.0/8' not in command for pair in changes for command in pair))


class PackageTests(unittest.TestCase):
    def test_arch_installs_only_openssh_when_missing(self):
        system=ssh.System();events=[]
        def which(name):
            if name=='pacman':return '/usr/bin/pacman'
            if name=='sshd' and events:return '/usr/bin/sshd'
        with patch.object(system,'which',side_effect=which),patch.object(system,'run',side_effect=lambda args,**kw:events.append(args)):
            self.assertEqual(system.ensure_server(),'/usr/bin/sshd')
        self.assertEqual(events,[['pacman','-S','--needed','--noconfirm','openssh']])

    def test_debian_package_cannot_auto_start_general_ssh_and_masks_are_removed(self):
        for failure in (False,True):
            system=ssh.System();events=[];installed=[]
            def which(name):
                if name=='apt-get':return '/usr/bin/apt-get'
                if name=='sshd' and installed:return '/usr/sbin/sshd'
            def run(args,**kwargs):
                events.append(args)
                if args[0]=='apt-get':
                    if failure:raise RuntimeError('download failed')
                    installed.append(True)
                return subprocess.CompletedProcess(args,0,'not-found\n','')
            with patch.object(system,'which',side_effect=which),patch.object(system,'run',side_effect=run):
                if failure:
                    with self.assertRaisesRegex(RuntimeError,'download failed'):system.ensure_server()
                else:self.assertEqual(system.ensure_server(),'/usr/sbin/sshd')
            for name in ('ssh.service','ssh.socket'):
                self.assertIn(['systemctl','mask','--runtime',name],events)
                self.assertIn(['systemctl','disable',name],events)
                self.assertIn(['systemctl','unmask','--runtime',name],events)


if __name__ == '__main__': unittest.main()
