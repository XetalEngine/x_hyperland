"""Behavioral checks use private files and fake hardware; no messages are sent."""
from pathlib import Path
import json,tempfile,unittest
from unittest.mock import patch
from . import phone,power,monitor_hardware as monitor


class ServicesTests(unittest.TestCase):
    def test_whatsapp_uri_is_encoded_and_unknown_protocols_rejected(self):
        url=phone.whatsapp_url('whatsapp://send?phone=%2B15551234567&text=hello%20%26%20goodbye')
        self.assertEqual(url,'https://web.whatsapp.com/send?phone=15551234567&text=hello+%26+goodbye')
        for value in ('javascript:alert(1)','https://evil.example','whatsapp://settings','whatsapp://send?phone=abc'):
            with self.assertRaises(ValueError):phone.whatsapp_url(value)

    def test_sms_keeps_text_as_a_single_argument(self):
        with patch.object(phone,'run',return_value='sent') as run:
            phone.action('phone-123','send-sms','hello; $(touch nope)','+1 (555) 123-4567')
        self.assertEqual(run.call_args.args[0],['kdeconnect-cli','--device','phone-123','--send-sms','hello; $(touch nope)','--destination','+15551234567'])

    def test_power_defaults_do_not_change_existing_idle_policy(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(power,'FILE',Path(folder)/'missing.json'):
            self.assertFalse(power.load()['enabled']);self.assertEqual(power.load()['lid_ac'],'system')

    def test_idle_policy_respects_inhibitors_and_uses_selected_power_source(self):
        value=power.normalize(dict(power.DEFAULTS,enabled=True,ac_lock=2,ac_screen=3,ac_sleep=4))
        ac=power.idle_config(value,False);battery=power.idle_config(value,True)
        self.assertIn('timeout = 120',ac);self.assertIn('timeout = 240',ac)
        self.assertIn('timeout = 1200',battery);self.assertNotIn('ignore_inhibit',ac)
        self.assertIn('inhibit_sleep = 3',ac)
        with self.assertRaises(ValueError):power.normalize(dict(value,ac_lock=5))
        with self.assertRaises(ValueError):power.normalize(dict(value,lid_ac='reboot'))

    def test_monitor_apply_rolls_back_a_partial_hardware_failure(self):
        old={'brightness':dict(value=60,maximum=100),'contrast':dict(value=50,maximum=100)}
        calls=[]
        def set_raw(device,key,value):
            calls.append((key,value))
            if key=='contrast' and value==70:raise RuntimeError('monitor refused')
        with patch.object(monitor,'levels',return_value=old),patch.object(monitor,'set_raw',side_effect=set_raw):
            with self.assertRaisesRegex(RuntimeError,'refused'):monitor.apply({},dict(brightness=80,contrast=70))
        self.assertEqual(calls,[('brightness',80),('contrast',70),('contrast',50),('brightness',60)])

    def test_monitor_preview_eof_restores_and_does_not_save(self):
        from io import StringIO
        with tempfile.TemporaryDirectory() as folder,patch.object(monitor,'STATE',Path(folder)),patch.object(monitor,'FILE',Path(folder)/'saved.json'),patch.object(monitor,'probe',return_value={'identity':'safe'}),patch.object(monitor,'apply',return_value={'brightness':{'value':60}}),patch.object(monitor,'restore') as restore,patch.object(monitor.select,'select',return_value=([object()],[],[])),patch.object(monitor.sys,'stdin',StringIO('')),patch.object(monitor.sys,'stdout',StringIO()):
            monitor.preview('DP-1',{'brightness':70});restore.assert_called_once();self.assertFalse((Path(folder)/'saved.json').exists())

    def test_monitor_preview_keep_persists_identity_and_values(self):
        from io import StringIO
        with tempfile.TemporaryDirectory() as folder,patch.object(monitor,'STATE',Path(folder)),patch.object(monitor,'FILE',Path(folder)/'saved.json'),patch.object(monitor,'probe',return_value={'identity':'edid-hash'}),patch.object(monitor,'apply',return_value={}),patch.object(monitor,'restore') as restore,patch.object(monitor.select,'select',return_value=([object()],[],[])),patch.object(monitor.sys,'stdin',StringIO('keep\n')),patch.object(monitor.sys,'stdout',StringIO()):
            monitor.preview('DP-1',{'brightness':70});restore.assert_not_called()
            self.assertEqual(json.loads((Path(folder)/'saved.json').read_text())['displays']['edid-hash']['values'],{'brightness':70})
