"""Bridge transactions use a fake NetworkManager; never change host networking."""
import unittest
from gi.repository import GLib
import network_bridge as bridge

V = GLib.Variant


def ethernet():
    return dict(path='/device/eth0', Interface='eth0', DeviceType=1, State=100,
        Managed=True, physical=True, HwAddress='02:12:34:56:78:90', Mtu=9000,
        active={'Connection':'/profile/original', 'Default':True, 'Ip4Config':'/ip4/original'},
        settings={
            'connection':{'id':V('s','My wired connection'), 'uuid':V('s','original-uuid'),
                          'type':V('s','802-3-ethernet'), 'autoconnect':V('b', True)},
            '802-3-ethernet':{'mtu':V('u',9000)},
            'ipv4':{'method':V('s','manual'), 'gateway':V('s','192.0.2.1'),
                    'address-data':V('aa{sv}', [{'address':V('s','192.0.2.5'), 'prefix':V('u',24)}]),
                    'dns-data':V('as',['192.0.2.53']), 'route-metric':V('x',77)},
            'ipv6':{'method':V('s','auto'), 'addr-gen-mode':V('i',1)},
            'proxy':{'method':V('i',0)}})


class FakeNM:
    def __init__(self, fail=None):
        self.nic = ethernet(); self.events = []; self.added = {}; self.fail = fail
    def devices(self): return [self.nic]
    def profiles(self): return [self.nic['settings']]
    def checkpoint(self, device):
        self.events.append(('checkpoint',device))
        if self.fail == 'checkpoint': raise RuntimeError('Recovery unavailable')
        return '/checkpoint/1'
    def add(self, settings):
        path = f'/profile/new{len(self.added)}'
        self.added[path] = settings
        self.events.append(('add',path))
        if self.fail == 'port' and len(self.added) == 2:
            del self.added[path]
            raise RuntimeError('Port creation failed')
        return path
    def activate(self, profile, device='/'):
        self.events.append(('activate',profile,device))
        if self.fail == 'activate': raise RuntimeError('Activation failed')
        return profile.replace('/profile/', '/active/')
    def ready(self, *args): return self.fail != 'timeout'
    def save(self, path, settings):
        self.events.append(('save',path))
        if self.fail == 'save': raise RuntimeError('Saving failed')
    def delete(self, path): self.events.append(('delete',path))
    def rollback(self, checkpoint): self.events.append(('rollback',checkpoint))
    def commit(self, checkpoint): self.events.append(('commit',checkpoint))


class BridgeTests(unittest.TestCase):
    def test_keeps_static_addresses_dns_ipv6_mtu_and_original_profile(self):
        nm = FakeNM(); original = dict(nm.nic['settings']['connection'])
        result = bridge.create_bridge('br0', nm)
        created, port = nm.added.values()
        for group in ('ipv4', 'ipv6', 'proxy'):
            self.assertEqual(created[group], nm.nic['settings'][group])
        self.assertEqual(bridge.value(created, '802-3-ethernet', 'mtu'), 9000)
        self.assertEqual(bridge.value(created, 'bridge', 'mac-address'), list(bytes.fromhex('021234567890')))
        self.assertEqual(bridge.value(port, 'connection', 'master'), bridge.value(created, 'connection', 'uuid'))
        self.assertNotIn('ipv4', port)
        self.assertTrue(bridge.value(port, 'connection', 'autoconnect'))
        self.assertEqual(nm.nic['settings']['connection'], original)
        self.assertEqual(nm.events[0][0], 'checkpoint')
        self.assertEqual(nm.events[-1], ('commit','/checkpoint/1'))
        self.assertEqual(result['bridge'], 'br0')
        self.assertFalse(any('/profile/original' in event for event in nm.events))

    def test_each_failed_stage_rolls_back_and_deletes_only_own_profiles(self):
        for stage in ('port', 'activate', 'timeout', 'save'):
            with self.subTest(stage=stage):
                nm = FakeNM(stage)
                with self.assertRaisesRegex(RuntimeError, 'original Ethernet connection'):
                    bridge.create_bridge('br0', nm, timeout=0)
                self.assertEqual(nm.events[-1], ('rollback','/checkpoint/1'))
                self.assertFalse(any(e[0]=='commit' for e in nm.events))
                self.assertEqual({e[1] for e in nm.events if e[0]=='delete'}, set(nm.added))

    def test_does_nothing_without_a_checkpoint(self):
        nm = FakeNM('checkpoint')
        with self.assertRaisesRegex(RuntimeError, 'Recovery unavailable'):
            bridge.create_bridge('br0', nm)
        self.assertEqual(nm.events, [('checkpoint','/device/eth0')])

    def test_existing_active_bridge_is_selected_without_mutation(self):
        nm = FakeNM(); nm.nic.update(Interface='br0', DeviceType=13)
        self.assertEqual(bridge.create_bridge('br0', nm)['bridge'], 'br0')
        self.assertEqual(nm.events, [])

    def test_wifi_conflicts_and_enterprise_connections_are_not_modified(self):
        for change, message in (({'DeviceType':2}, 'Wi-Fi'),
                                ({'Interface':'br0'}, 'already exists'),
                                ({'State':30}, 'No connected')):
            nm = FakeNM(); nm.nic.update(change)
            with self.assertRaisesRegex(RuntimeError, message): bridge.create_bridge('br0', nm)
            self.assertEqual(nm.events, [])
        nm = FakeNM(); nm.nic['settings']['802-1x'] = {'eap':V('as',['tls'])}
        with self.assertRaisesRegex(RuntimeError, 'manual bridge'): bridge.create_bridge('br0', nm)
        self.assertEqual(nm.events, [])

    def test_inactive_saved_profile_is_never_overwritten(self):
        nm = FakeNM()
        nm.profiles = lambda:[{'connection':{'interface-name':V('s','br0')}}]
        with self.assertRaisesRegex(RuntimeError, 'saved profile'): bridge.create_bridge('br0', nm)
        self.assertEqual(nm.events, [])

    def test_bad_interface_names_never_reach_networkmanager(self):
        for name in ('lo', '../br0', 'br0;reboot', '', 'a'*16):
            with self.assertRaises(ValueError): bridge.detect(name, None)

    def test_readiness_requires_the_original_route_and_addresses(self):
        nm = object.__new__(bridge.NetworkManager)
        active = {'State':2,'Default':False,'Ip4Config':'/ip4/bridge'}
        nm.props = lambda path, iface: {'AddressData':[{'address':'192.0.2.5'}]} if path=='/ip4/bridge' else active
        self.assertFalse(nm.ready('/active/bridge','/active/port',ethernet()))
        active['Default'] = True
        self.assertTrue(nm.ready('/active/bridge','/active/port',ethernet()))
        active['State'] = 4
        with self.assertRaisesRegex(RuntimeError,'activate'): nm.ready('/active/bridge','/active/port',ethernet())


if __name__ == '__main__': unittest.main()
