import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import guest_connection as guest
import portable


class GuestConnectionTests(unittest.TestCase):
    def setUp(self):
        self.config = portable.configuration('windows')
        self.template = (portable.ROOT/'guest/vmstealth75.bat').read_bytes().decode()

    def test_managed_copy_fills_login_port_edition_paths_and_selected_guest(self):
        self.config['tools']['vmstealth_host'] = '/home/alice/My VMs/editions/enhanced/helper.sh'
        self.config['simple'].update(qmp='unix:/home/alice/My VMs/run/qmp.sock,server,nowait', name='Windows 11,debug-threads=on')
        before = copy.deepcopy(self.config)
        text = guest.render(self.template, self.config, managed=True, user='alice', address='192.168.1.25')
        for assignment in ('HOST_LOGIN=alice@192.168.1.25', 'HOST_PORT=2222',
                           'HOST_HELPER=/home/alice/My VMs/editions/enhanced/helper.sh',
                           'QMP_SOCKET=/home/alice/My VMs/run/qmp.sock', 'GUEST_NAME=Windows 11'):
            self.assertIn('set "'+assignment+'"', text)
        self.assertIn("bash '%HOST_HELPER%' --qmp '%QMP_SOCKET%' --domain '%GUEST_NAME%'", text)
        self.assertIn('ssh.exe -tt ', text)
        self.assertEqual(self.config, before)
        self.assertEqual((portable.ROOT/'guest/vmstealth75.bat').read_bytes().decode(), self.template)
        self.assertEqual(text.count('\r\n'), text.count('\n'))
        self.assertEqual(text.count('\n'), self.template.count('\n'))

    def test_qemu_guest_name_option_is_not_copied_as_part_of_the_name(self):
        self.config['simple']['name'] = 'guest=win10,debug-threads=on'
        text = guest.render(self.template, self.config, managed=True, user='alice', address='192.168.1.25')
        self.assertIn('set "GUEST_NAME=win10"', text)
        self.assertNotIn('GUEST_NAME=guest=', text)

    def test_custom_login_and_commands_are_preserved(self):
        custom = '@echo off\r\nset "HOST_LOGIN=bob@192.168.4.8"\r\necho custom\r\n'
        with patch.object(guest, 'host_address', side_effect=AssertionError('unneeded discovery')):
            self.assertEqual(guest.render(custom, self.config, managed=False), custom)
        placeholder = custom.replace('bob@192.168.4.8', 'YOUR_LINUX_USER@YOUR_LINUX_HOST')
        self.assertEqual(guest.render(placeholder, self.config, managed=False, user='bob', address='192.168.4.8'), custom)

    def test_bridge_default_route_ambiguous_network_and_offline_nat(self):
        addresses = [('docker0','172.17.0.1'), ('eth0','192.168.1.2'), ('br0','192.168.9.2')]
        self.assertEqual(guest.host_address(self.config, addresses, 'eth0'), '192.168.9.2')
        self.config['network']['bridge'] = ''
        self.assertEqual(guest.host_address(self.config, addresses, 'eth0'), '192.168.1.2')
        with self.assertRaisesRegex(ValueError, 'Several local networks'):
            guest.host_address(self.config, addresses, '')
        with self.assertRaisesRegex(ValueError, 'No local IPv4'):
            guest.host_address(self.config, [('docker0','172.17.0.1')], '')
        self.config['network']['mode'] = 'user'
        self.assertEqual(guest.host_address(self.config, [], ''), '10.0.2.2')

    def test_rejects_shell_boundaries_and_duplicate_template_fields(self):
        for value in ('/tmp/" & whoami', '/tmp/a\ncommand', "/tmp/it's", '/tmp/%PATH%'):
            self.config['tools']['vmstealth_host'] = value
            with self.assertRaises(ValueError):
                guest.render(self.template, self.config, managed=True, user='alice', address='192.168.1.2')
        self.config = portable.configuration('windows')
        with self.assertRaisesRegex(ValueError, 'exactly one HOST_PORT'):
            guest.render(self.template+'set "HOST_PORT=22"\r\n', self.config, managed=True, user='alice', address='192.168.1.2')


if __name__ == '__main__': unittest.main()
